import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = REPO_ROOT / "azuredeploy.json"
TEAMS_APP_PACKAGE_SCRIPT = REPO_ROOT / "teams-app-package" / "build-app-package.ps1"
TEAMS_APP_PACKAGE_OUTPUT_DIR = REPO_ROOT / "teams-app-package" / "test-output"
DEPLOYMENT_METADATA_FILENAME = "deployment.json"

GLOBAL_CLOUD = "AzureCloud"
GLOBAL_LOCATION = "eastasia"
CHINA_CLOUD = "AzureChinaCloud"
CHINA_LOCATION = "chinanorth3"
DEFAULT_ADMIN_USERNAME = "azureuser"
DEFAULT_HOSTNAME = ""
DELETE_WAIT_TIMEOUT_SECONDS = 300
DELETE_WAIT_POLL_SECONDS = 15
SSH_EXECUTABLE = shutil.which("ssh.exe") or shutil.which("ssh") or "ssh"
DEFAULT_SSH_PRIVATE_KEY_PATH = Path.home() / ".ssh" / "id_ed25519"
SENSITIVE_PARAMETER_KEYS = {
    "azureOpenAiApiKey",
    "feishuAppSecret",
    "msteamsAppPassword",
    "sshPublicKey",
}
AZ_EXECUTABLE = shutil.which("az.cmd") or shutil.which("az") or "az"
POWERSHELL_EXECUTABLE = (
    shutil.which("pwsh.exe")
    or shutil.which("pwsh")
    or shutil.which("powershell.exe")
    or shutil.which("powershell")
    or "pwsh"
)


def log_message(cloud_name, message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{cloud_name}] {message}", flush=True)


def sanitize_az_args(args):
    sanitized = []
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            if key in SENSITIVE_PARAMETER_KEYS and value:
                sanitized.append(f"{key}=***")
                continue
        sanitized.append(arg)
    return sanitized


def stream_reader(pipe, sink, prefix, buffer):
    try:
        for line in iter(pipe.readline, ""):
            buffer.append(line)
            sink.write(f"{prefix}{line}")
            sink.flush()
    finally:
        pipe.close()


def load_env(relative_path: str):
    env = {}
    for raw_line in (
        (REPO_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    for key, value in os.environ.items():
        if key.startswith("TEST_"):
            env[key] = value
    return env


def run_az(args, cloud_name):
    command = [AZ_EXECUTABLE, *args]
    pretty_command = subprocess.list2cmdline(["az", *sanitize_az_args(args)])
    log_message(cloud_name, f"Running az command: {pretty_command}")

    process = subprocess.Popen(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "AZURE_CORE_CLOUD": cloud_name},
    )

    stdout_buffer = []
    stderr_buffer = []
    stdout_thread = threading.Thread(
        target=stream_reader,
        args=(process.stdout, sys.stdout, f"[{cloud_name}][stdout] ", stdout_buffer),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stream_reader,
        args=(process.stderr, sys.stderr, f"[{cloud_name}][stderr] ", stderr_buffer),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    return_code = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    stdout_text = "".join(stdout_buffer)
    stderr_text = "".join(stderr_buffer)
    if return_code != 0:
        raise RuntimeError(
            f"az {' '.join(sanitize_az_args(args))} failed for {cloud_name}\nstdout:\n{stdout_text}\nstderr:\n{stderr_text}"
        )
    log_message(cloud_name, f"Completed az command: {pretty_command}")
    return stdout_text


def run_az_capture(args, cloud_name):
    command = [AZ_EXECUTABLE, *args]
    pretty_command = subprocess.list2cmdline(["az", *sanitize_az_args(args)])
    log_message(cloud_name, f"Running az command: {pretty_command}")

    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env={**os.environ, "AZURE_CORE_CLOUD": cloud_name},
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"az {' '.join(sanitize_az_args(args))} failed for {cloud_name}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    log_message(cloud_name, f"Completed az command: {pretty_command}")
    return result.stdout


def ensure_cloud(cloud_name):
    run_az(["cloud", "set", "--name", cloud_name], cloud_name)


def is_logged_in(cloud_name):
    try:
        ensure_cloud(cloud_name)
        run_az(["account", "show", "--output", "json"], cloud_name)
        return True
    except RuntimeError:
        return False


class AzureIntegrationDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = load_env(".env")

    def _log(self, cloud_name, message):
        log_message(cloud_name, message)

    def _keep_resource_group(self):
        return self.env.get("TEST_KEEP_RESOURCE_GROUP", "0").strip() == "1"

    def _should_validate_browser_pairing(self):
        return self.env.get("TEST_VALIDATE_BROWSER_PAIRING", "0").strip() == "1"

    def _get_browser_pairing_timeout_seconds(self):
        raw_value = self.env.get("TEST_BROWSER_PAIRING_TIMEOUT_SECONDS", "90").strip()
        try:
            return max(15, int(raw_value or "90"))
        except ValueError as exc:
            raise ValueError(
                "TEST_BROWSER_PAIRING_TIMEOUT_SECONDS must be an integer."
            ) from exc

    def _use_headless_browser(self):
        return self.env.get("TEST_BROWSER_PAIRING_HEADLESS", "1").strip() != "0"

    def _ensure_playwright_available(self):
        if not self._should_validate_browser_pairing():
            return

        try:
            importlib.import_module("playwright.sync_api")
        except ImportError:
            self.skipTest(
                "Set TEST_VALIDATE_BROWSER_PAIRING=1 requires the Python 'playwright' package. "
                "Install it with 'python -m pip install playwright' and install a browser with "
                "'python -m playwright install chromium'."
            )

    def _get_playwright_sync_api(self):
        try:
            return importlib.import_module("playwright.sync_api")
        except ImportError:
            self.skipTest(
                "Set TEST_VALIDATE_BROWSER_PAIRING=1 requires the Python 'playwright' package. "
                "Install it with 'python -m pip install playwright' and install a browser with "
                "'python -m playwright install chromium'."
            )

    def _get_ssh_private_key_path(self):
        configured = self.env.get("TEST_SSH_PRIVATE_KEY_PATH", "").strip()
        return (
            Path(configured).expanduser()
            if configured
            else DEFAULT_SSH_PRIVATE_KEY_PATH
        )

    def _run_ssh(self, cloud_name, vm_public_fqdn, remote_command):
        ssh_private_key = self._get_ssh_private_key_path()
        if not ssh_private_key.exists():
            self.skipTest(
                f"SSH private key not found at {ssh_private_key}. Set TEST_SSH_PRIVATE_KEY_PATH or place the key there before running integration tests."
            )

        command = [
            SSH_EXECUTABLE,
            "-i",
            str(ssh_private_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{DEFAULT_ADMIN_USERNAME}@{vm_public_fqdn}",
            remote_command,
        ]
        self._log(
            cloud_name, f"Running SSH command on {vm_public_fqdn}: {remote_command}"
        )
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=True,
        )
        if result.stdout.strip():
            self._log(cloud_name, result.stdout.strip())
        if result.stderr.strip():
            self._log(cloud_name, result.stderr.strip())
        return result.stdout, result.stderr

    def _validate_runtime_helper_script(self, cloud_name, vm_public_fqdn):
        script_stdout, _ = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "sed -n '1,120p' /usr/local/bin/openclaw-approve-browser",
        )
        self.assertNotIn(
            'gateway_url="ws://127.0.0.1:${OPENCLAW_GATEWAY_PORT}"', script_stdout
        )
        self.assertIn("device-pairing-*.js", script_stdout)
        self.assertIn("PAIRING_LIST_JS_B64=", script_stdout)
        self.assertIn("PAIRING_APPROVE_JS_B64=", script_stdout)
        self.assertIn("OPENCLAW_REQUEST_ID:", script_stdout)
        self.assertIn("printf '%s' \"$PAIRING_LIST_JS_B64\" | base64 -d", script_stdout)
        self.assertIn(
            "printf '%s' \"$PAIRING_APPROVE_JS_B64\" | base64 -d", script_stdout
        )
        self.assertNotIn("openclaw devices approve --latest", script_stdout)

    def _validate_runtime_install_state(
        self, cloud_name, vm_public_fqdn, expect_msteams_runtime=False
    ):
        runtime_stdout, _ = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            (
                "bash -lc '"
                'printf "openclaw_path=%s\\n" "$(command -v openclaw)" '
                '&& printf "npm_path=%s\\n" "$(command -v npm)" '
                '&& printf "openclaw_version=%s\\n" "$(/usr/local/bin/openclaw --version | head -n 1)" '
                '&& printf "node_version=%s\\n" "$(/home/{user}/.openclaw/tools/node/bin/node -v)" '
                '&& printf "state_dir=%s\\n" "$OPENCLAW_STATE_DIR" '
                '&& printf "config_path=%s\\n" "$OPENCLAW_CONFIG_PATH" '
                '&& printf "compile_cache=%s\\n" "$NODE_COMPILE_CACHE" '
                '&& printf "no_respawn=%s\\n" "$OPENCLAW_NO_RESPAWN" '
                '&& config_token_kind="$(python3 - <<'
                "PY"
                '\nimport json\nfrom pathlib import Path\nconfig = json.loads(Path.home().joinpath(".openclaw", "openclaw.json").read_text(encoding="utf-8"))\ntoken = (((config.get("gateway") or dict()).get("auth") or dict()).get("token"))\nprint("string" if isinstance(token, str) and token else type(token).__name__)\nPY\n)" '
                '&& printf "config_token_kind=%s\\n" "$config_token_kind" '
                '&& install_package_dir="/home/{user}/.openclaw/lib/node_modules/openclaw" '
                '&& printf "install_package_dir=%s\\n" "$install_package_dir" '
                '&& gateway_entrypoint="$(sed -n "s/^ExecStart=//p" "$HOME/.config/systemd/user/openclaw-gateway.service" | head -n 1 | cut -d " " -f 2)" '
                '&& printf "gateway_entrypoint=%s\\n" "$gateway_entrypoint" '
                '&& gateway_package_dir="$(dirname "$(dirname "$gateway_entrypoint")")" '
                '&& printf "gateway_package_dir=%s\\n" "$gateway_package_dir" '
                '&& plugin_context_engine="$(python3 - <<'
                "PY"
                '\nimport json\nfrom pathlib import Path\nconfig = json.loads(Path.home().joinpath(".openclaw", "openclaw.json").read_text(encoding="utf-8"))\nprint((((config.get("plugins") or dict()).get("slots") or dict()).get("contextEngine")) or "")\nPY\n)" '
                '&& printf "plugin_context_engine=%s\\n" "$plugin_context_engine" '
                '&& if test -d "$HOME/.openclaw/extensions/lossless-claw"; then echo runtime_lossless_claw_dir=present; else echo runtime_lossless_claw_dir=missing; fi '
                '&& if test -f "$install_package_dir/extensions/msteams/package.json"; then echo runtime_msteams_package_json=present; else echo runtime_msteams_package_json=missing; fi '
                '&& if test -d "$install_package_dir/extensions/msteams/node_modules/@microsoft/agents-hosting"; then echo runtime_msteams_agents_hosting=present; else echo runtime_msteams_agents_hosting=missing; fi '
                '&& if test -d "$gateway_package_dir/extensions/msteams/node_modules/@microsoft/agents-hosting"; then echo gateway_msteams_agents_hosting=present; else echo gateway_msteams_agents_hosting=missing; fi '
                '&& if test -d "$gateway_package_dir/extensions/feishu/node_modules/@larksuiteoapi/node-sdk"; then echo gateway_feishu_node_sdk=present; else echo gateway_feishu_node_sdk=missing; fi '
                '&& printf "gateway_state=%s\\n" "$(systemctl --user is-active openclaw-gateway)" '
                "'"
            ).format(user=DEFAULT_ADMIN_USERNAME),
        )
        values = {}
        for line in runtime_stdout.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        self.assertEqual(
            values.get("openclaw_path"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw/bin/openclaw",
        )
        self.assertEqual(
            values.get("npm_path"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw/tools/node/bin/npm",
        )
        self.assertTrue(values.get("openclaw_version", "").startswith("OpenClaw "))
        self.assertEqual(values.get("node_version"), "v24.14.0")
        self.assertEqual(
            values.get("state_dir"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw",
        )
        self.assertEqual(
            values.get("config_path"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw/openclaw.json",
        )
        self.assertEqual(
            values.get("compile_cache"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw/cache/node-compile",
        )
        self.assertEqual(values.get("no_respawn"), "1")
        self.assertEqual(values.get("config_token_kind"), "string")
        self.assertEqual(
            values.get("install_package_dir"),
            f"/home/{DEFAULT_ADMIN_USERNAME}/.openclaw/lib/node_modules/openclaw",
        )
        self.assertTrue(values.get("gateway_entrypoint", "").endswith("/dist/entry.js"))
        self.assertTrue(values.get("gateway_package_dir", "").endswith("/openclaw"))
        self.assertEqual(values.get("plugin_context_engine"), "lossless-claw")
        self.assertEqual(values.get("runtime_lossless_claw_dir"), "present")
        self.assertEqual(values.get("gateway_state"), "active")
        if self.env.get("TEST_FEISHU_APP_ID") and self.env.get(
            "TEST_FEISHU_APP_SECRET"
        ):
            self.assertEqual(values.get("gateway_feishu_node_sdk"), "present")
        if expect_msteams_runtime:
            self.assertEqual(values.get("runtime_msteams_package_json"), "present")
            self.assertEqual(
                values.get("runtime_msteams_agents_hosting"),
                "present",
            )
            self.assertEqual(values.get("gateway_msteams_agents_hosting"), "present")

    def _validate_runtime_doctor_and_update_state(
        self, cloud_name, vm_public_fqdn, expect_msteams_runtime=False
    ):
        doctor_stdout, doctor_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc '/usr/local/bin/openclaw doctor | cat'",
        )
        doctor_output = f"{doctor_stdout}\n{doctor_stderr}"
        self.assertNotIn("NODE_COMPILE_CACHE is not set", doctor_output)
        self.assertNotIn("OPENCLAW_NO_RESPAWN is not set to 1", doctor_output)
        self.assertNotIn("Multiple state directories detected", doctor_output)
        if expect_msteams_runtime:
            self.assertNotIn("AADSTS7000229", doctor_output)
            self.assertNotIn("missing service principal", doctor_output.lower())

        update_stdout, update_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc '/usr/local/bin/openclaw update --dry-run --yes --no-restart'",
        )
        update_output = f"{update_stdout}\n{update_stderr}"
        self.assertNotIn("spawn npm ENOENT", update_output)

    def _validate_runtime_local_admin_cli_state(
        self, cloud_name, vm_public_fqdn, openclaw_public_url
    ):
        stdout, _ = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            (
                "bash -lc '"
                'printf "gateway_url=%s\\n" "${OPENCLAW_GATEWAY_URL:-}" '
                '&& printf "public_url=%s\\n" "$OPENCLAW_PUBLIC_URL" '
                '&& printf "gateway_token_len=%s\\n" "${#OPENCLAW_GATEWAY_TOKEN}" '
                '&& printf "gateway_auth_mode=%s\\n" "$(/usr/local/bin/openclaw config get gateway.auth.mode)" '
                "&& echo --- health --- "
                '&& /usr/local/bin/openclaw health --verbose | grep -v "^\\[plugins\\]" | sed -n "1,20p" '
                "'"
            ),
        )
        values = {}
        status_lines = []
        parsing_values = True
        for line in stdout.splitlines():
            if parsing_values and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
                continue
            parsing_values = False
            status_lines.append(line)

        self.assertEqual(values.get("public_url"), openclaw_public_url)
        self.assertEqual(values.get("gateway_url"), "")
        self.assertGreater(int(values.get("gateway_token_len", "0")), 0)
        self.assertEqual(values.get("gateway_auth_mode"), "token")

        health_output = "\n".join(status_lines)
        self.assertIn("Gateway target: ws://127.0.0.1:18789", health_output)
        self.assertIn("Source: local loopback", health_output)
        self.assertNotIn("pairing required", health_output.lower())

    def _validate_runtime_browser_helper_output(
        self, cloud_name, vm_public_fqdn, openclaw_public_url
    ):
        browser_url_stdout, browser_url_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc 'openclaw-browser-url'",
        )
        dashboard_url = self._extract_dashboard_url(
            f"{browser_url_stdout}\n{browser_url_stderr}"
        )
        self.assertEqual(dashboard_url.split("#", 1)[0], openclaw_public_url)
        self.assertIn("#token=", dashboard_url)

    def _should_apply_devices_list_workaround(self):
        return self.env.get("TEST_APPLY_DEVICES_LIST_WORKAROUND", "1").strip() != "0"

    def _apply_devices_list_workaround(self, cloud_name, vm_public_fqdn):
        if not self._should_apply_devices_list_workaround():
            self._log(
                cloud_name,
                "Skipping test-only devices list workaround because TEST_APPLY_DEVICES_LIST_WORKAROUND=0",
            )
            return

        workaround_command = (
            'bash -lc "'
            "set -euo pipefail; "
            'dist="$HOME/.openclaw/lib/node_modules/openclaw/dist"; '
            'gateway_file="$(find "$dist" -maxdepth 1 -name "gateway-cli-*.js" | head -n 1)"; '
            'model_file="$(find "$dist" -maxdepth 1 -name "model-selection-*.js" | head -n 1)"; '
            'test -n "$gateway_file" && test -f "$gateway_file"; '
            'test -n "$model_file" && test -f "$model_file"; '
            'if grep -q "const DEFAULT_HANDSHAKE_TIMEOUT_MS = 1e4;" "$gateway_file"; then '
            "  echo gateway_patch=already; "
            "else "
            "  perl -0pi -e 's/const DEFAULT_HANDSHAKE_TIMEOUT_MS = 3e3;/const DEFAULT_HANDSHAKE_TIMEOUT_MS = 1e4;/g' \"$gateway_file\"; "
            "  echo gateway_patch=applied; "
            "fi; "
            'if grep -q "Math.max(250, Math.min(1e4, rawConnectDelayMs)) : 1e4;" "$model_file"; then '
            "  echo model_patch=already; "
            "else "
            "  perl -0pi -e 's/Math\\.max\\(250, Math\\.min\\(1e4, rawConnectDelayMs\\)\\) : 2e3;/Math.max(250, Math.min(1e4, rawConnectDelayMs)) : 1e4;/g' \"$model_file\"; "
            "  echo model_patch=applied; "
            "fi; "
            "systemctl --user restart openclaw-gateway; "
            'printf "gateway_state=%s\\n" "$(systemctl --user is-active openclaw-gateway)"; '
            'grep -n "DEFAULT_HANDSHAKE_TIMEOUT_MS = 1e4;" "$gateway_file" | head -n 1; '
            'grep -n "Math.max(250, Math.min(1e4, rawConnectDelayMs)) : 1e4;" "$model_file" | head -n 1'
            '"'
        )

        stdout, _ = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            workaround_command,
        )
        self.assertIn("gateway_state=active", stdout)
        self.assertIn("DEFAULT_HANDSHAKE_TIMEOUT_MS = 1e4;", stdout)
        self.assertIn(
            "Math.max(250, Math.min(1e4, rawConnectDelayMs)) : 1e4;",
            stdout,
        )

    def _assert_pairing_rpc_stable(self, cloud_name, vm_public_fqdn, attempts=5):
        command = (
            "bash -lc '"
            "ok=0; fail=0; "
            "for i in $(seq 1 {attempts}); do "
            "if /usr/local/bin/openclaw devices list --json >/tmp/device-pair-list-$i.out 2>&1; then ok=$((ok+1)); else fail=$((fail+1)); fi; "
            'done; printf "ok=%s fail=%s\\n" "$ok" "$fail"; '
            "for i in $(seq 1 {attempts}); do echo --- run $i ---; tail -n 12 /tmp/device-pair-list-$i.out; done'"
        ).format(attempts=attempts)
        stdout, stderr = self._run_ssh(cloud_name, vm_public_fqdn, command)
        combined_output = f"{stdout}\n{stderr}"
        match = re.search(r"ok=(\d+) fail=(\d+)", combined_output)
        if match is None:
            self.fail(f"Missing stability counters in output: {combined_output}")
        self.assertEqual(int(match.group(2)), 0, combined_output)

    def _assert_no_pending_browser_pairing_request(self, cloud_name, vm_public_fqdn):
        helper_stdout, helper_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc 'openclaw-approve-browser'",
        )
        combined_output = f"{helper_stdout}\n{helper_stderr}"
        self.assertIn(
            "No pending browser pairing requests. Keep the dashboard page open on the pairing screen, wait a few seconds, and try again.",
            combined_output,
        )

    def _extract_dashboard_url(self, command_output):
        match = re.search(r"https://\S+#token=\S+", command_output)
        if not match:
            self.fail(f"Could not find a dashboard URL in output: {command_output}")
        return match.group(0)

    def _extract_json_payload(self, text, description):
        start = text.find("{")
        if start < 0:
            self.fail(f"Could not find JSON payload in {description}: {text}")
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
        return payload

    def _list_pairing_payload(self, cloud_name, vm_public_fqdn):
        devices_stdout, devices_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc '/usr/local/bin/openclaw gateway call device.pair.list --json --params \"{}\"'",
        )
        return self._extract_json_payload(
            f"{devices_stdout}\n{devices_stderr}",
            "openclaw gateway call device.pair.list --json output",
        )

    def _matching_browser_devices(self, payload, state):
        return [
            item
            for item in (payload.get(state) or [])
            if (
                str(item.get("clientId") or "") == "openclaw-control-ui"
                or str(item.get("clientMode") or "") in ("webchat", "browser")
            )
        ]

    def _validate_browser_pairing(self, cloud_name, vm_public_fqdn):
        browser_url_stdout, browser_url_stderr = self._run_ssh(
            cloud_name,
            vm_public_fqdn,
            "bash -lc 'openclaw-browser-url'",
        )
        dashboard_url = self._extract_dashboard_url(
            f"{browser_url_stdout}\n{browser_url_stderr}"
        )
        self._log(
            cloud_name,
            f"Opening dashboard URL for browser pairing validation: {dashboard_url.split('#', 1)[0]}#token=***",
        )

        playwright_sync_api = self._get_playwright_sync_api()
        playwright_error = playwright_sync_api.Error
        sync_playwright = playwright_sync_api.sync_playwright

        timeout_seconds = self._get_browser_pairing_timeout_seconds()
        deadline = time.time() + timeout_seconds

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=self._use_headless_browser()
                )
                context = browser.new_context(ignore_https_errors=True)
                page = context.new_page()
                page.goto(dashboard_url, wait_until="domcontentloaded", timeout=30000)

                pending_request_seen = False
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    devices_payload = self._list_pairing_payload(
                        cloud_name, vm_public_fqdn
                    )
                    if self._matching_browser_devices(devices_payload, "pending"):
                        pending_request_seen = True
                        break

                self.assertTrue(
                    pending_request_seen,
                    "Timed out waiting for the browser page to create a pending pairing request.",
                )

                helper_stdout, helper_stderr = self._run_ssh(
                    cloud_name,
                    vm_public_fqdn,
                    "bash -lc 'openclaw-approve-browser'",
                )
                combined_output = f"{helper_stdout}\n{helper_stderr}"
                self.assertIn(
                    "Approving browser pairing request:",
                    combined_output,
                )

                paired_device_seen = False
                while time.time() < deadline:
                    page.wait_for_timeout(2000)
                    devices_payload = self._list_pairing_payload(
                        cloud_name, vm_public_fqdn
                    )
                    if self._matching_browser_devices(devices_payload, "paired"):
                        paired_device_seen = True
                        break

                self.assertTrue(
                    paired_device_seen,
                    "Timed out waiting for the approved browser device to enter the paired state.",
                )

                context.close()
                browser.close()
        except playwright_error as exc:
            self.fail(
                f"Browser pairing validation failed to drive the dashboard page: {exc}"
            )

    def _write_deployment_metadata(self, cloud_name, metadata):
        persistent_output_dir = TEAMS_APP_PACKAGE_OUTPUT_DIR / cloud_name
        persistent_output_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = persistent_output_dir / DEPLOYMENT_METADATA_FILENAME
        metadata_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        self._log(cloud_name, f"Wrote deployment metadata: {metadata_path}")
        return metadata_path

    def _cloud_output_dir(self, cloud_name):
        return TEAMS_APP_PACKAGE_OUTPUT_DIR / cloud_name

    def _reset_cloud_output_dir(self, cloud_name):
        persistent_output_dir = self._cloud_output_dir(cloud_name)
        if persistent_output_dir.exists():
            self._log(
                cloud_name,
                f"Removing stale persistent test output before new run: {persistent_output_dir}",
            )
            shutil.rmtree(persistent_output_dir)
        persistent_output_dir.mkdir(parents=True, exist_ok=True)
        return persistent_output_dir

    def _should_auto_create_msteams_app_registration(self, cloud_name):
        if cloud_name != GLOBAL_CLOUD:
            return False
        return (
            self.env.get("TEST_AUTO_CREATE_MSTEAMS_APP_REGISTRATION", "1").strip()
            != "0"
        )

    def _resolve_msteams_credentials(self, cloud_name, suffix):
        if cloud_name != GLOBAL_CLOUD:
            return None

        if self._should_auto_create_msteams_app_registration(cloud_name):
            return self._create_temporary_msteams_app_registration(cloud_name, suffix)

        app_id = self.env.get("TEST_MSTEAMS_APP_ID", "").strip()
        app_password = self.env.get("TEST_MSTEAMS_APP_PASSWORD", "").strip()
        if bool(app_id) != bool(app_password):
            raise ValueError(
                "TEST_MSTEAMS_APP_ID and TEST_MSTEAMS_APP_PASSWORD must either both be set or both be empty."
            )
        if not app_id:
            return None
        return {
            "appId": app_id,
            "clientSecret": app_password,
            "displayName": "static-test-credentials",
            "temporary": False,
        }

    def _create_temporary_msteams_app_registration(self, cloud_name, suffix):
        display_name = f"openclaw-integration-{suffix}"
        self._log(
            cloud_name,
            f"Creating temporary Microsoft Entra app registration {display_name} for this test run",
        )
        created_app = json.loads(
            run_az_capture(
                [
                    "ad",
                    "app",
                    "create",
                    "--display-name",
                    display_name,
                    "--sign-in-audience",
                    "AzureADMyOrg",
                    "--output",
                    "json",
                ],
                cloud_name,
            )
        )
        app_id = str(created_app.get("appId") or "").strip()
        object_id = str(created_app.get("id") or "").strip()
        self.assertTrue(app_id, "Temporary Teams app registration did not return appId")
        self.assertTrue(
            object_id,
            "Temporary Teams app registration did not return object id",
        )

        client_secret = run_az_capture(
            [
                "ad",
                "app",
                "credential",
                "reset",
                "--id",
                app_id,
                "--append",
                "--display-name",
                f"openclaw-integration-secret-{suffix}",
                "--years",
                "1",
                "--query",
                "password",
                "--output",
                "tsv",
            ],
            cloud_name,
        ).strip()
        self.assertTrue(
            client_secret,
            "Temporary Teams app registration did not return a client secret",
        )
        service_principal = self._ensure_temporary_msteams_service_principal(
            cloud_name,
            app_id,
            display_name,
        )
        self._log(
            cloud_name,
            f"Created temporary Microsoft Entra app registration {display_name} with appId {app_id}",
        )
        return {
            "appId": app_id,
            "clientSecret": client_secret,
            "displayName": display_name,
            "objectId": object_id,
            "servicePrincipalObjectId": service_principal["objectId"],
            "temporary": True,
        }

    def _ensure_temporary_msteams_service_principal(
        self, cloud_name, app_id, display_name
    ):
        self._log(
            cloud_name,
            f"Ensuring temporary Microsoft Entra service principal exists for {display_name}",
        )
        try:
            existing = json.loads(
                run_az_capture(
                    ["ad", "sp", "show", "--id", app_id, "--output", "json"],
                    cloud_name,
                )
            )
            object_id = str(existing.get("id") or "").strip()
            if object_id:
                self._log(
                    cloud_name,
                    f"Temporary Microsoft Entra service principal already exists for {display_name}: {object_id}",
                )
                return {"objectId": object_id}
        except RuntimeError:
            pass

        created = json.loads(
            run_az_capture(
                ["ad", "sp", "create", "--id", app_id, "--output", "json"],
                cloud_name,
            )
        )
        created_object_id = str(created.get("id") or "").strip()

        deadline = time.time() + 90
        last_error = None
        while time.time() < deadline:
            try:
                current = json.loads(
                    run_az_capture(
                        ["ad", "sp", "show", "--id", app_id, "--output", "json"],
                        cloud_name,
                    )
                )
                object_id = str(current.get("id") or created_object_id).strip()
                if object_id:
                    self._log(
                        cloud_name,
                        f"Temporary Microsoft Entra service principal is ready for {display_name}: {object_id}",
                    )
                    return {"objectId": object_id}
            except RuntimeError as exc:
                last_error = exc
            time.sleep(5)

        if last_error is not None:
            raise AssertionError(
                f"Temporary Microsoft Entra service principal for {display_name} was not visible before timeout: {last_error}"
            ) from last_error
        raise AssertionError(
            f"Temporary Microsoft Entra service principal for {display_name} was not visible before timeout."
        )

    def _delete_temporary_msteams_app_registration(self, cloud_name, credentials):
        if not credentials or not credentials.get("temporary"):
            return
        app_id = str(credentials.get("appId") or "").strip()
        if not app_id:
            return
        self._delete_temporary_msteams_service_principal(cloud_name, app_id)
        self._log(
            cloud_name,
            f"Deleting temporary Microsoft Entra app registration {credentials.get('displayName') or app_id}",
        )
        run_az_capture(["ad", "app", "delete", "--id", app_id], cloud_name)
        self._log(
            cloud_name,
            f"Deleted temporary Microsoft Entra app registration {credentials.get('displayName') or app_id}",
        )

    def _delete_temporary_msteams_service_principal(self, cloud_name, app_id):
        try:
            existing = json.loads(
                run_az_capture(
                    ["ad", "sp", "show", "--id", app_id, "--output", "json"],
                    cloud_name,
                )
            )
        except RuntimeError:
            self._log(
                cloud_name,
                f"Temporary Microsoft Entra service principal already absent for appId {app_id}",
            )
            return

        object_id = str(existing.get("id") or app_id).strip()
        self._log(
            cloud_name,
            f"Deleting temporary Microsoft Entra service principal {object_id}",
        )
        run_az_capture(["ad", "sp", "delete", "--id", app_id], cloud_name)
        self._log(
            cloud_name,
            f"Deleted temporary Microsoft Entra service principal {object_id}",
        )

    def _generate_teams_app_package(
        self, cloud_name, openclaw_public_url, msteams_app_id
    ):
        bot_domain = urlparse(openclaw_public_url).hostname
        self.assertTrue(
            bot_domain, f"Could not derive hostname from {openclaw_public_url}"
        )

        persistent_output_dir = self._cloud_output_dir(cloud_name)
        persistent_output_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="openclaw-teams-app-") as temp_dir:
            package_command = [
                POWERSHELL_EXECUTABLE,
                "-NoLogo",
                "-NoProfile",
                "-File",
                str(TEAMS_APP_PACKAGE_SCRIPT),
                "-TemplateName",
                "import-test",
                "-AppId",
                msteams_app_id,
                "-BotDomain",
                bot_domain,
                "-OutputDir",
                temp_dir,
            ]
            self._log(
                cloud_name,
                f"Generating Teams app package from deployment output using host {bot_domain}",
            )
            result = subprocess.run(
                package_command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            zip_path = Path(temp_dir) / "OpenClaw.zip"
            manifest_path = Path(temp_dir) / "OpenClaw" / "manifest.json"
            self.assertTrue(
                zip_path.exists(), f"Expected generated package at {zip_path}"
            )
            self.assertTrue(
                manifest_path.exists(),
                f"Expected generated manifest at {manifest_path}",
            )

            persistent_zip_path = persistent_output_dir / "OpenClaw.zip"
            persistent_manifest_dir = persistent_output_dir / "OpenClaw"
            shutil.copy2(zip_path, persistent_zip_path)
            shutil.copytree(
                manifest_path.parent, persistent_manifest_dir, dirs_exist_ok=True
            )

            self._log(
                cloud_name,
                f"Teams app package generated successfully: {persistent_zip_path}",
            )
            self._log(
                cloud_name,
                f"Generated Teams manifest directory: {persistent_manifest_dir}",
            )
            if result.stdout.strip():
                self._log(cloud_name, result.stdout.strip())
            return {
                "zipPath": str(persistent_zip_path),
                "manifestDirectory": str(persistent_manifest_dir),
                "botDomain": bot_domain,
            }

    def _wait_for_resource_group_deletion(self, cloud_name, resource_group_name):
        deadline = time.time() + DELETE_WAIT_TIMEOUT_SECONDS
        while True:
            exists_output = run_az(
                ["group", "exists", "--name", resource_group_name],
                cloud_name,
            )
            exists = exists_output.strip().lower() == "true"
            if not exists:
                self._log(cloud_name, f"Resource group {resource_group_name} deleted")
                return

            remaining_seconds = max(0, int(deadline - time.time()))
            if remaining_seconds == 0:
                self.fail(
                    f"Timed out waiting {DELETE_WAIT_TIMEOUT_SECONDS}s for resource group {resource_group_name} deletion in {cloud_name}."
                )

            self._log(
                cloud_name,
                f"Resource group {resource_group_name} still exists; waiting {DELETE_WAIT_POLL_SECONDS}s more ({remaining_seconds}s remaining)",
            )
            time.sleep(DELETE_WAIT_POLL_SECONDS)

    def _resource_group_has_resources(self, cloud_name, resource_group_name):
        resources_output = run_az(
            [
                "resource",
                "list",
                "--resource-group",
                resource_group_name,
                "--output",
                "json",
            ],
            cloud_name,
        )
        return len(json.loads(resources_output)) > 0

    def _resource_group_prefix(self):
        return (
            self.env.get("TEST_RESOURCE_GROUP_PREFIX", "openclawtest").strip()
            or "openclawtest"
        )

    def _list_stale_resource_groups(self, cloud_name):
        prefix = self._resource_group_prefix()
        current_cloud_prefix = f"{prefix}-{cloud_name.lower()}-"
        validate_prefix = f"{prefix}-validate-"
        groups_output = run_az(["group", "list", "--output", "json"], cloud_name)
        groups = json.loads(groups_output)
        return sorted(
            group["name"]
            for group in groups
            if group.get("name", "").startswith(current_cloud_prefix)
            or group.get("name", "").startswith(validate_prefix)
        )

    def _delete_stale_resource_groups(self, cloud_name):
        stale_groups = self._list_stale_resource_groups(cloud_name)
        if not stale_groups:
            self._log(cloud_name, "No stale integration-test resource groups found")
            return []

        self._log(
            cloud_name,
            "Deleting stale integration-test resource groups before starting a new run: "
            + ", ".join(stale_groups),
        )
        for group_name in stale_groups:
            run_az(
                [
                    "group",
                    "delete",
                    "--name",
                    group_name,
                    "--yes",
                    "--no-wait",
                ],
                cloud_name,
            )
        self._log(
            cloud_name,
            "Stale resource group deletion started in background; continuing without waiting.",
        )
        return stale_groups

    def _log_resource_group_delete_statuses(self, cloud_name, resource_group_names):
        if not resource_group_names:
            return

        for group_name in resource_group_names:
            exists_output = run_az(
                ["group", "exists", "--name", group_name],
                cloud_name,
            )
            exists = exists_output.strip().lower() == "true"
            if exists:
                self._log(
                    cloud_name,
                    f"Background deletion is still in progress for stale resource group {group_name}",
                )
            else:
                self._log(
                    cloud_name,
                    f"Background deletion completed for stale resource group {group_name}",
                )

    def setUp(self):
        if self.env.get("TEST_RUN_INTEGRATION", "0") != "1":
            self.skipTest(
                "Set TEST_RUN_INTEGRATION=1 in .env to enable real Azure integration tests."
            )
        if not self.env.get("TEST_SSH_PUBLIC_KEY", "").strip():
            self.skipTest(
                "Set TEST_SSH_PUBLIC_KEY in .env before running integration tests."
            )
        self._ensure_playwright_available()

    def _deploy_and_cleanup(self, cloud_name, location, subscription_id_env_key):
        self._log(cloud_name, "Checking Azure CLI login state")
        if not is_logged_in(cloud_name):
            self.skipTest(f"Azure CLI is not logged in for {cloud_name}.")
        self._log(cloud_name, "Azure CLI login verified")

        subscription_id = self.env.get(subscription_id_env_key, "").strip()
        if subscription_id:
            self._log(cloud_name, f"Selecting subscription {subscription_id}")
            run_az(["account", "set", "--subscription", subscription_id], cloud_name)
            self._log(cloud_name, "Subscription selected")

        stale_groups_pending_delete = self._delete_stale_resource_groups(cloud_name)

        suffix = uuid.uuid4().hex[:8]
        resource_group_prefix = self._resource_group_prefix()
        resource_group_name = f"{resource_group_prefix}-{cloud_name.lower()}-{suffix}"
        vm_name = f"openclaw{suffix}"
        rg_created = False
        teams_credentials = None
        deployment_error = None
        deployment_metadata = {
            "cloud": cloud_name,
            "location": location,
            "resourceGroup": resource_group_name,
            "vmName": vm_name,
            "keptResourceGroup": self._keep_resource_group(),
        }
        self._reset_cloud_output_dir(cloud_name)
        teams_credentials = self._resolve_msteams_credentials(cloud_name, suffix)
        if teams_credentials:
            deployment_metadata["teamsAppRegistration"] = {
                "appId": teams_credentials["appId"],
                "displayName": teams_credentials["displayName"],
                "temporary": bool(teams_credentials.get("temporary")),
            }

        parameters = [
            f"vmName={vm_name}",
            f"adminUsername={DEFAULT_ADMIN_USERNAME}",
            f"sshPublicKey={self.env['TEST_SSH_PUBLIC_KEY']}",
            f"location={location}",
            f"hostname={DEFAULT_HOSTNAME}",
        ]

        if self.env.get("TEST_FEISHU_APP_ID") and self.env.get(
            "TEST_FEISHU_APP_SECRET"
        ):
            parameters.extend(
                [
                    f"feishuAppId={self.env['TEST_FEISHU_APP_ID']}",
                    f"feishuAppSecret={self.env['TEST_FEISHU_APP_SECRET']}",
                ]
            )

        if teams_credentials:
            parameters.extend(
                [
                    f"msteamsAppId={teams_credentials['appId']}",
                    f"msteamsAppPassword={teams_credentials['clientSecret']}",
                ]
            )

        openai_values = [
            self.env.get("TEST_AZURE_OPENAI_ENDPOINT", "").strip(),
            self.env.get("TEST_AZURE_OPENAI_DEPLOYMENT", "").strip(),
            self.env.get("TEST_AZURE_OPENAI_API_KEY", "").strip(),
        ]
        if all(openai_values):
            parameters.extend(
                [
                    f"azureOpenAiEndpoint={openai_values[0]}",
                    f"azureOpenAiDeployment={openai_values[1]}",
                    f"azureOpenAiApiKey={openai_values[2]}",
                ]
            )

        try:
            self._log(
                cloud_name,
                f"Creating resource group {resource_group_name} in {location}",
            )
            ensure_cloud(cloud_name)
            run_az(
                [
                    "group",
                    "create",
                    "--name",
                    resource_group_name,
                    "--location",
                    location,
                    "--output",
                    "json",
                ],
                cloud_name,
            )
            rg_created = True
            self._log(cloud_name, f"Resource group {resource_group_name} created")

            deployment_name = f"deploy-{suffix}"
            self._log(
                cloud_name,
                f"Starting deployment {deployment_name} for VM {vm_name}",
            )
            deployment_output = run_az(
                [
                    "deployment",
                    "group",
                    "create",
                    "--name",
                    deployment_name,
                    "--resource-group",
                    resource_group_name,
                    "--template-file",
                    str(TEMPLATE_FILE),
                    "--parameters",
                    *parameters,
                    "--output",
                    "json",
                ],
                cloud_name,
            )
            self._log(cloud_name, f"Deployment {deployment_name} completed")

            payload = json.loads(deployment_output)
            outputs = payload["properties"]["outputs"]
            vm_public_fqdn = outputs["vmPublicFqdn"]["value"]
            openclaw_public_url = outputs["openclawPublicUrl"]["value"]
            deployment_metadata.update(
                {
                    "vmPublicFqdn": vm_public_fqdn,
                    "openclawPublicUrl": openclaw_public_url,
                    "deploymentName": deployment_name,
                }
            )
            self._log(
                cloud_name,
                f"Validating outputs for {vm_public_fqdn} and {openclaw_public_url}",
            )

            expected_suffix = (
                ".cloudapp.chinacloudapi.cn"
                if cloud_name == CHINA_CLOUD
                else ".cloudapp.azure.com"
            )
            self.assertTrue(vm_public_fqdn.endswith(expected_suffix))
            self.assertTrue(openclaw_public_url.startswith("https://"))
            self.assertIn(vm_name, vm_public_fqdn)
            self._validate_runtime_helper_script(cloud_name, vm_public_fqdn)
            self._validate_runtime_install_state(
                cloud_name,
                vm_public_fqdn,
                expect_msteams_runtime=bool(teams_credentials),
            )
            self._validate_runtime_doctor_and_update_state(
                cloud_name,
                vm_public_fqdn,
                expect_msteams_runtime=bool(teams_credentials),
            )
            self._validate_runtime_local_admin_cli_state(
                cloud_name, vm_public_fqdn, openclaw_public_url
            )
            self._validate_runtime_browser_helper_output(
                cloud_name, vm_public_fqdn, openclaw_public_url
            )
            self._apply_devices_list_workaround(cloud_name, vm_public_fqdn)
            self._assert_pairing_rpc_stable(cloud_name, vm_public_fqdn)
            if self._should_validate_browser_pairing():
                self._validate_browser_pairing(cloud_name, vm_public_fqdn)
            else:
                self._assert_no_pending_browser_pairing_request(
                    cloud_name, vm_public_fqdn
                )

            extension_name = f"{vm_name}/openclaw-bootstrap"
            self._log(
                cloud_name,
                f"Checking VM extension resource {extension_name}",
            )
            extension_show = json.loads(
                run_az(
                    [
                        "vm",
                        "extension",
                        "show",
                        "--resource-group",
                        resource_group_name,
                        "--vm-name",
                        vm_name,
                        "--name",
                        "openclaw-bootstrap",
                        "--output",
                        "json",
                    ],
                    cloud_name,
                )
            )
            extension_provisioning_state = extension_show.get("provisioningState", "")
            deployment_metadata["bootstrapExtensionName"] = extension_name
            deployment_metadata["bootstrapExtensionProvisioningState"] = (
                extension_provisioning_state
            )
            self.assertEqual(extension_show["name"], "openclaw-bootstrap")
            self.assertEqual(extension_provisioning_state, "Succeeded")
            self._log(
                cloud_name,
                f"VM extension {extension_name} provisioningState={extension_provisioning_state}",
            )

            if teams_credentials:
                bot_name = outputs.get("teamsBotName", {}).get("value", "")
                self.assertTrue(bot_name)
                deployment_metadata["teamsBotName"] = bot_name
                self._log(cloud_name, f"Checking Teams bot resource {bot_name}")
                bot_show = json.loads(
                    run_az(
                        [
                            "resource",
                            "show",
                            "--resource-group",
                            resource_group_name,
                            "--resource-type",
                            "Microsoft.BotService/botServices",
                            "--name",
                            bot_name,
                            "--output",
                            "json",
                        ],
                        cloud_name,
                    )
                )
                self.assertEqual(bot_show["name"], bot_name)
                self._log(cloud_name, f"Teams bot resource {bot_name} verified")
                deployment_metadata["teamsBotResourceId"] = bot_show.get("id", "")
                deployment_metadata["teamsBotEndpoint"] = bot_show.get(
                    "properties", {}
                ).get("endpoint", "")
                deployment_metadata["teamsAppPackage"] = (
                    self._generate_teams_app_package(
                        cloud_name,
                        openclaw_public_url,
                        teams_credentials["appId"],
                    )
                )

            self._write_deployment_metadata(cloud_name, deployment_metadata)

            self._log(cloud_name, "Deployment validation finished")
        except Exception as exc:
            deployment_error = exc
            raise
        finally:
            cleanup_error = None
            keep_resource_group = False
            if teams_credentials and teams_credentials.get("temporary"):
                try:
                    ensure_cloud(cloud_name)
                    self._delete_temporary_msteams_app_registration(
                        cloud_name, teams_credentials
                    )
                except Exception as exc:
                    cleanup_error = exc
                    if deployment_error is None:
                        raise
                    self._log(
                        cloud_name,
                        f"Temporary Teams app registration cleanup failed after deployment error: {exc}",
                    )

            if rg_created:
                if self._keep_resource_group():
                    ensure_cloud(cloud_name)
                    if self._resource_group_has_resources(
                        cloud_name, resource_group_name
                    ):
                        keep_resource_group = True
                        self._log(
                            cloud_name,
                            f"Keeping resource group {resource_group_name} because TEST_KEEP_RESOURCE_GROUP=1 and it contains deployed resources",
                        )
                    else:
                        self._log(
                            cloud_name,
                            f"Deleting empty resource group {resource_group_name} even though TEST_KEEP_RESOURCE_GROUP=1",
                        )
                if not keep_resource_group:
                    self._log(
                        cloud_name, f"Deleting resource group {resource_group_name}"
                    )
                    ensure_cloud(cloud_name)
                    run_az(
                        [
                            "group",
                            "delete",
                            "--name",
                            resource_group_name,
                            "--yes",
                            "--no-wait",
                        ],
                        cloud_name,
                    )
                    self._log(
                        cloud_name,
                        f"Waiting for resource group {resource_group_name} deletion",
                    )
                    self._wait_for_resource_group_deletion(
                        cloud_name, resource_group_name
                    )

            if cleanup_error is not None and deployment_error is None:
                raise cleanup_error

            self._log_resource_group_delete_statuses(
                cloud_name, stale_groups_pending_delete
            )

    def test_real_deploy_global_azure(self):
        self._deploy_and_cleanup(
            GLOBAL_CLOUD, GLOBAL_LOCATION, "TEST_GLOBAL_SUBSCRIPTION_ID"
        )

    def test_real_deploy_china_azure(self):
        self._deploy_and_cleanup(
            CHINA_CLOUD, CHINA_LOCATION, "TEST_CHINA_SUBSCRIPTION_ID"
        )


if __name__ == "__main__":
    unittest.main()
