import json
import re
import unittest
from pathlib import Path

from scripts.sync_bootstrap_script import (
    DEFAULT_ARM_EXPRESSION_PATH,
    DEFAULT_ARM_STRING_PATH,
    HELPER_TEMPLATE_PATHS,
    build_bootstrap_expression,
    extract_arm_format_string,
    extract_embedded_script,
    validate_arm_format_literal,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_CLOUD = "AzureCloud"
GLOBAL_LOCATION = "eastasia"
CHINA_CLOUD = "AzureChinaCloud"
CHINA_LOCATION = "chinanorth3"
DEFAULT_VM_NAME = "openclawtestvm"
DEFAULT_HOSTNAME = ""


def load_json(relative_path: str):
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def expected_public_dns_suffix(cloud_name: str) -> str:
    return (
        "cloudapp.chinacloudapi.cn"
        if cloud_name == CHINA_CLOUD
        else "cloudapp.azure.com"
    )


def expected_public_fqdn(vm_name: str, location: str, cloud_name: str) -> str:
    dns_label = vm_name.lower().replace("_", "-")
    return f"{dns_label}.{location}.{expected_public_dns_suffix(cloud_name)}"


def expected_public_control_url(
    vm_name: str, location: str, cloud_name: str, hostname: str
) -> str:
    if hostname:
        return f"https://{hostname}/"
    return f"https://{expected_public_fqdn(vm_name, location, cloud_name)}/"


class AzureDeployTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = load_json("azuredeploy.json")
        cls.ui_definition = load_json("createUiDefinition.json")
        cls.teams_manifest_template = (
            REPO_ROOT / "teams-app-package" / "manifest.template.json"
        ).read_text(encoding="utf-8")
        cls.teams_quickstart_manifest_template = (
            REPO_ROOT / "teams-app-package" / "manifest.quickstart.template.json"
        ).read_text(encoding="utf-8")
        cls.teams_import_test_manifest_template = (
            REPO_ROOT / "teams-app-package" / "manifest.import-test.template.json"
        ).read_text(encoding="utf-8")
        cls.env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        cls.readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        (
            cls.bootstrap_script,
            cls.expected_arm_string_literal,
            cls.expected_arm_expression,
        ) = build_bootstrap_expression(REPO_ROOT / "bootstrapScript.template.sh")

    def test_template_json_is_valid(self):
        self.assertIn("parameters", self.template)
        self.assertIn("variables", self.template)
        self.assertIn("resources", self.template)
        self.assertIn("metadata", self.template)
        self.assertIn(
            "OpenClaw Azure deployment template",
            self.template["metadata"]["description"],
        )

    def test_dns_suffix_is_cloud_aware(self):
        variables = self.template["variables"]
        self.assertEqual(
            variables["isAzureChinaCloud"],
            "[equals(environment().name, 'AzureChinaCloud')]",
        )
        self.assertEqual(
            self.template["parameters"]["location"]["defaultValue"],
            "southeastasia",
        )
        self.assertEqual(
            variables["deploymentLocation"],
            "[if(empty(parameters('location')), resourceGroup().location, parameters('location'))]",
        )
        self.assertIn("cloudapp.chinacloudapi.cn", variables["publicDnsSuffix"])
        self.assertIn("cloudapp.azure.com", variables["publicDnsSuffix"])
        self.assertIn("variables('publicDnsSuffix')", variables["publicFqdn"])
        self.assertIn("variables('deploymentLocation')", variables["publicFqdn"])

    def test_expected_global_azure_url_from_env(self):
        public_fqdn = expected_public_fqdn(
            DEFAULT_VM_NAME,
            GLOBAL_LOCATION,
            GLOBAL_CLOUD,
        )
        public_url = expected_public_control_url(
            DEFAULT_VM_NAME,
            GLOBAL_LOCATION,
            GLOBAL_CLOUD,
            DEFAULT_HOSTNAME,
        )
        self.assertTrue(public_fqdn.endswith(".cloudapp.azure.com"))
        self.assertEqual(public_url, f"https://{public_fqdn}/")

    def test_expected_china_azure_url_from_env(self):
        public_fqdn = expected_public_fqdn(
            DEFAULT_VM_NAME,
            CHINA_LOCATION,
            CHINA_CLOUD,
        )
        public_url = expected_public_control_url(
            DEFAULT_VM_NAME,
            CHINA_LOCATION,
            CHINA_CLOUD,
            DEFAULT_HOSTNAME,
        )
        self.assertTrue(public_fqdn.endswith(".cloudapp.chinacloudapi.cn"))
        self.assertEqual(public_url, f"https://{public_fqdn}/")

    def test_feishu_parameters_are_optional_but_paired(self):
        parameters = self.template["parameters"]
        self.assertIn("feishuAppId", parameters)
        self.assertIn("feishuAppSecret", parameters)
        self.assertEqual(parameters["feishuAppId"]["defaultValue"], "")
        self.assertEqual(parameters["feishuAppSecret"]["defaultValue"], "")

        variables = self.template["variables"]
        self.assertIn("feishuValidationMode", variables)
        self.assertIn("feishuAppId", variables["feishuValidationMode"])
        self.assertIn("feishuAppSecret", variables["feishuValidationMode"])
        self.assertIn(
            "must either both be provided or both be empty",
            variables["feishuValidationMode"],
        )

    def test_msteams_parameters_are_optional_but_paired(self):
        parameters = self.template["parameters"]
        self.assertIn("msteamsAppId", parameters)
        self.assertIn("msteamsAppPassword", parameters)
        self.assertEqual(parameters["msteamsAppId"]["defaultValue"], "")
        self.assertEqual(parameters["msteamsAppPassword"]["defaultValue"], "")

        variables = self.template["variables"]
        self.assertEqual(variables["msteamsTenantId"], "[subscription().tenantId]")
        self.assertIn("msteamsValidationMode", variables)
        self.assertIn("msteamsAppId", variables["msteamsValidationMode"])
        self.assertIn("msteamsAppPassword", variables["msteamsValidationMode"])
        self.assertNotIn("Azure Global", variables["msteamsValidationMode"])
        self.assertNotIn("isAzureChinaCloud", variables["msteamsValidationMode"])
        self.assertIn("take(parameters('vmName'), 51)", variables["botServiceName"])
        self.assertIn(
            "uniqueString(resourceGroup().id, parameters('msteamsAppId'))",
            variables["botServiceName"],
        )

    def test_msteams_parameters_do_not_restrict_azure_china(self):
        parameters = self.template["parameters"]
        self.assertNotIn(
            "Azure Global only",
            parameters["msteamsAppId"]["metadata"]["description"],
        )
        self.assertNotIn(
            "Azure Global only",
            parameters["msteamsAppPassword"]["metadata"]["description"],
        )

    def test_managed_identity_blocked_in_azure_china(self):
        variables = self.template["variables"]
        validation = variables["azureOpenAiValidationMode"]
        self.assertIn("isAzureChinaCloud", validation)
        self.assertIn(
            "Managed Identity authentication for Azure OpenAI is not supported in Azure China Cloud",
            validation,
        )

    def test_arm_template_no_longer_generates_openclaw_config(self):
        variables = self.template["variables"]
        self.assertNotIn("openclawDefaultModelJson", variables)
        self.assertNotIn("openclawModelsJson", variables)
        self.assertNotIn("openclawFeishuJson", variables)
        self.assertNotIn("openclawMsTeamsJson", variables)
        self.assertNotIn("openclawChannelsOpen", variables)
        self.assertNotIn("openclawChannelSeparator", variables)
        self.assertNotIn("openclawChannelsClose", variables)
        self.assertNotIn("openclawConfig", variables)
        self.assertNotIn("openclawConfigBase64", variables)

    def test_bootstrap_script_exports_feishu_credentials(self):
        self.assertIn("OPENCLAW_FEISHU_APP_ID='{6}'", self.bootstrap_script)
        self.assertIn("OPENCLAW_FEISHU_APP_SECRET='{7}'", self.bootstrap_script)
        self.assertIn("OPENCLAW_STATE_DIR=/home/{5}/.openclaw", self.bootstrap_script)
        self.assertIn(
            "OPENCLAW_CONFIG_PATH=/home/{5}/.openclaw/openclaw.json",
            self.bootstrap_script,
        )
        self.assertNotIn("OPENCLAW_HOME=/home/{5}", self.bootstrap_script)
        self.assertIn(
            'OPENCLAW_ORIGINAL_PATH="$PATH"\n  unset OPENCLAW_GATEWAY_URL\n  set -a\n  . /etc/openclaw/openclaw.env\n  if [ -r /etc/openclaw/openclaw-shell-override.env ]; then\n    . /etc/openclaw/openclaw-shell-override.env\n  fi\n  set +a\n  PATH="/home/{5}/.openclaw/tools/node/bin:/home/{5}/.openclaw/bin:$OPENCLAW_ORIGINAL_PATH"\n  export PATH\n  unset OPENCLAW_ORIGINAL_PATH',
            self.bootstrap_script,
        )
        self.assertNotIn(
            "cat > /etc/openclaw/openclaw-shell.env <<EOF", self.bootstrap_script
        )
        self.assertNotIn(".openclaw-env.sh", self.bootstrap_script)
        self.assertIn(
            ": > /etc/openclaw/openclaw-shell-override.env",
            self.bootstrap_script,
        )
        self.assertIn(
            "chmod 660 /etc/openclaw/openclaw-shell-override.env",
            self.bootstrap_script,
        )
        self.assertNotIn("OPENCLAW_GATEWAY_URL={4}", self.bootstrap_script)

    def test_bootstrap_script_trusts_loopback_reverse_proxy(self):
        self.assertIn(
            'run_openclaw_config_json gateway.trustedProxies \'["127.0.0.1","::1"]\'',
            self.bootstrap_script,
        )

    def test_bootstrap_script_exports_msteams_credentials_and_installs_bundled_dependencies(
        self,
    ):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]

        self.assertIn("set -eux\n", self.bootstrap_script)
        self.assertNotIn("set -euxo pipefail", self.bootstrap_script)

        self.assertIn("OPENCLAW_MSTEAMS_APP_ID='{8}'", self.bootstrap_script)
        self.assertIn("OPENCLAW_MSTEAMS_APP_PASSWORD='{9}'", self.bootstrap_script)
        self.assertIn("OPENCLAW_MSTEAMS_TENANT_ID='{10}'", self.bootstrap_script)
        self.assertIn("openclaw-approve-teams-pairing", self.bootstrap_script)
        self.assertIn("openclaw-gateway-mode", self.bootstrap_script)
        self.assertIn("openclaw-use-public-gateway", self.bootstrap_script)
        self.assertIn("openclaw-use-loopback-gateway", self.bootstrap_script)
        self.assertIn(
            'openclaw gateway call device.pair.list --json --params "{}"',
            self.bootstrap_script,
        )
        self.assertIn(
            "openclaw gateway call device.pair.approve --json --params",
            self.bootstrap_script,
        )
        self.assertIn(
            "payload.get('pending') or []",
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_GATEWAY_URL="$public_gateway_url" /usr/local/bin/openclaw health --verbose --timeout "$timeout_ms"',
            self.bootstrap_script,
        )
        self.assertIn(
            'git config --global --add url."https://github.com/".insteadOf ssh://git@github.com/',
            self.bootstrap_script,
        )
        self.assertIn(
            'git config --global --add url."https://github.com/".insteadOf git@github.com:',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_INSTALL_PREFIX="/home/{5}/.openclaw"',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_NODE_VERSION="24.14.0"',
            self.bootstrap_script,
        )
        self.assertIn(
            "PATH=/home/{5}/.openclaw/tools/node/bin:/home/{5}/.openclaw/bin:/usr/local/bin:/usr/bin:/bin",
            self.bootstrap_script,
        )
        self.assertIn(
            "apt-get install -y ca-certificates curl git gnupg caddy build-essential procps file",
            self.bootstrap_script,
        )
        self.assertIn(
            "cat > /etc/sudoers.d/90-{5}-nopasswd <<EOF",
            self.bootstrap_script,
        )
        self.assertIn("{5} ALL=(ALL:ALL) NOPASSWD:ALL", self.bootstrap_script)
        self.assertIn(
            "visudo -cf /etc/sudoers.d/90-{5}-nopasswd",
            self.bootstrap_script,
        )
        self.assertIn(
            "cat > /etc/profile.d/linuxbrew.sh <<'EOF'",
            self.bootstrap_script,
        )
        self.assertIn(
            'eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"',
            self.bootstrap_script,
        )
        self.assertIn(
            "NODE_COMPILE_CACHE=/home/{5}/.openclaw/cache/node-compile",
            self.bootstrap_script,
        )
        self.assertIn("OPENCLAW_NO_RESPAWN=1", self.bootstrap_script)
        self.assertIn(
            "install -d -o {5} -g {5} /home/{5}/.openclaw/cache/node-compile",
            self.bootstrap_script,
        )
        self.assertIn(
            "install -d -o {5} -g {5} /home/linuxbrew /home/linuxbrew/.linuxbrew /home/{5}/.cache/Homebrew",
            self.bootstrap_script,
        )
        self.assertIn(
            'HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew"',
            self.bootstrap_script,
        )
        self.assertIn(
            'HOMEBREW_INSTALL_REPO="/tmp/homebrew-install"',
            self.bootstrap_script,
        )
        self.assertIn(
            'git clone --depth 1 https://github.com/Homebrew/install "$HOMEBREW_INSTALL_REPO"',
            self.bootstrap_script,
        )
        self.assertIn(
            'sudo -u {5} env HOME="/home/{5}" NONINTERACTIVE=1 CI=1 bash -lc \'cd "$1" && /bin/bash ./install.sh\' _ "$HOMEBREW_INSTALL_REPO"',
            self.bootstrap_script,
        )
        self.assertIn(
            "run_admin_bash() {",
            self.bootstrap_script,
        )
        self.assertIn(
            "bash -c 'set -a; . /etc/openclaw/openclaw.env; set +a; \"$@\"' _ bash -c",
            self.bootstrap_script,
        )
        self.assertIn(
            "run_admin_bus_bash() {",
            self.bootstrap_script,
        )
        self.assertIn(
            'run_admin_bash \'cd "$HOME" && curl -fsSL --proto "=https" --tlsv1.2 https://openclaw.ai/install-cli.sh | bash -s -- --prefix "$HOME/.openclaw" --node-version "$1" --no-onboard --json\' "$OPENCLAW_NODE_VERSION"',
            self.bootstrap_script,
        )
        self.assertIn(
            'run_admin_bash \'export PATH="$HOME/.openclaw/tools/node/bin:$PATH" && "$HOME/.openclaw/tools/node/bin/npm" config set prefix "$HOME/.openclaw"\'',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_BIN="$OPENCLAW_INSTALL_PREFIX/bin/openclaw"',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_NPM_BIN="$OPENCLAW_INSTALL_PREFIX/tools/node/bin/npm"',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_INSTALL_PACKAGE_DIR="$OPENCLAW_INSTALL_PREFIX/lib/node_modules/openclaw"',
            self.bootstrap_script,
        )
        self.assertIn(
            "OpenClaw install package directory was not found after install-cli.sh completed: $OPENCLAW_INSTALL_PACKAGE_DIR",
            self.bootstrap_script,
        )
        self.assertNotIn(
            'OPENCLAW_MSTEAMS_DIR="$OPENCLAW_INSTALL_PACKAGE_DIR/extensions/msteams"',
            self.bootstrap_script,
        )
        self.assertNotIn(
            "OpenClaw MSTeams plugin package was not found at $OPENCLAW_MSTEAMS_DIR",
            self.bootstrap_script,
        )
        self.assertIn(
            "OpenClaw npm binary was not found after install-cli.sh completed: $OPENCLAW_NPM_BIN",
            self.bootstrap_script,
        )
        self.assertIn(
            'ln -sf "$OPENCLAW_BIN" /usr/local/bin/openclaw',
            self.bootstrap_script,
        )
        self.assertIn('OPENCLAW_UID="$(id -u {5})"', self.bootstrap_script)
        self.assertIn("loginctl enable-linger {5}", self.bootstrap_script)
        self.assertIn(
            'systemctl start "user@$OPENCLAW_UID.service"',
            self.bootstrap_script,
        )
        self.assertIn(
            'if [ ! -S "/run/user/$OPENCLAW_UID/bus" ]; then',
            self.bootstrap_script,
        )
        self.assertIn(
            'XDG_RUNTIME_DIR="/run/user/$OPENCLAW_UID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$OPENCLAW_UID/bus"',
            self.bootstrap_script,
        )
        self.assertIn(
            "run_admin_bus_bash '. /etc/openclaw/openclaw.env && systemctl --user import-environment HOME OPENCLAW_STATE_DIR OPENCLAW_CONFIG_PATH OPENCLAW_GATEWAY_PORT OPENCLAW_GATEWAY_TOKEN OPENCLAW_PUBLIC_URL PATH NODE_COMPILE_CACHE OPENCLAW_NO_RESPAWN'",
            self.bootstrap_script,
        )
        self.assertNotIn(
            "systemctl --user import-environment HOME OPENCLAW_STATE_DIR OPENCLAW_CONFIG_PATH OPENCLAW_GATEWAY_PORT OPENCLAW_GATEWAY_TOKEN OPENCLAW_PUBLIC_URL OPENCLAW_GATEWAY_URL PATH NODE_COMPILE_CACHE OPENCLAW_NO_RESPAWN",
            self.bootstrap_script,
        )
        self.assertIn(
            'run_admin_bus_bash \'. /etc/openclaw/openclaw.env && cd "$HOME" && exec /usr/local/bin/openclaw onboard --non-interactive --accept-risk --mode local --workspace /data/workspace --auth-choice skip --gateway-port "$OPENCLAW_GATEWAY_PORT" --gateway-bind loopback --gateway-auth token --gateway-token "$OPENCLAW_GATEWAY_TOKEN" --install-daemon --daemon-runtime node --skip-channels --skip-skills --json\'',
            self.bootstrap_script,
        )
        self.assertNotIn(
            "--gateway-token-ref-env OPENCLAW_GATEWAY_TOKEN", self.bootstrap_script
        )
        self.assertIn(
            "run_openclaw_config_json gateway.controlUi.enabled true",
            self.bootstrap_script,
        )
        self.assertIn(
            'run_openclaw_config_json gateway.controlUi.allowedOrigins "$OPENCLAW_ALLOWED_ORIGINS_JSON"',
            self.bootstrap_script,
        )
        self.assertIn(
            'run_admin_bus_bash \'./etc/openclaw/openclaw.env && cd "$HOME" && exec /usr/local/bin/openclaw config set --strict-json -- "$1" "$2"\''.replace(
                "'./", "'. /"
            ),
            self.bootstrap_script,
        )
        self.assertIn(
            'run_admin_bus_bash \'./etc/openclaw/openclaw.env && cd "$HOME" && exec /usr/local/bin/openclaw config set -- "$1" "$2"\''.replace(
                "'./", "'. /"
            ),
            self.bootstrap_script,
        )
        self.assertIn(
            'chmod 600 "/home/{5}/.openclaw/openclaw.json"',
            self.bootstrap_script,
        )
        self.assertIn(
            'run_openclaw_config_string channels.feishu.accounts.main.appId "$OPENCLAW_FEISHU_APP_ID"',
            self.bootstrap_script,
        )
        self.assertIn(
            'run_openclaw_config_string channels.msteams.appId "$OPENCLAW_MSTEAMS_APP_ID"',
            self.bootstrap_script,
        )
        self.assertIn(
            "OPENCLAW_AZURE_OPENAI_PROVIDER_JSON=$(cat <<EOF",
            self.bootstrap_script,
        )
        self.assertIn(
            'run_openclaw_config_json models.providers.openai "$OPENCLAW_AZURE_OPENAI_PROVIDER_JSON"',
            self.bootstrap_script,
        )
        self.assertNotIn(".openclaw-env.sh", arm_bootstrap_script)
        self.assertIn(
            "systemctl --user is-active openclaw-gateway",
            self.bootstrap_script,
        )
        self.assertIn("command -v openclaw >/dev/null 2>&1", self.bootstrap_script)
        self.assertIn("list_browser_request_id()", self.bootstrap_script)
        self.assertIn("approve_browser_request()", self.bootstrap_script)
        self.assertIn("text.find(chr(123))", self.bootstrap_script)
        self.assertIn("payload.get('device') or {}", self.bootstrap_script)
        self.assertNotIn('PAIRING_LIST_JS_B64="', self.bootstrap_script)
        self.assertNotIn('PAIRING_APPROVE_JS_B64="', self.bootstrap_script)
        self.assertIn(
            "OpenClaw CLI was not found in PATH",
            self.bootstrap_script,
        )
        self.assertIn(
            "No pending browser pairing requests. Keep the dashboard page open on the pairing screen, wait a few seconds, and try again.",
            self.bootstrap_script,
        )
        self.assertIn("2>&1", self.bootstrap_script)
        self.assertIn('OPENCLAW_UID="$(id -u {5})"', arm_bootstrap_script)
        self.assertIn(
            'systemctl start "user@$OPENCLAW_UID.service"', arm_bootstrap_script
        )
        self.assertIn(
            'if [ ! -S "/run/user/$OPENCLAW_UID/bus" ]; then', arm_bootstrap_script
        )
        self.assertIn(
            "systemctl --user is-active openclaw-gateway", arm_bootstrap_script
        )
        self.assertIn(
            "Approving browser pairing request: $request_id", self.bootstrap_script
        )
        self.assertIn("attempt=$((attempt + 1))", self.bootstrap_script)
        self.assertNotIn("openclaw devices approve --latest", self.bootstrap_script)
        self.assertNotIn(
            'gateway_url="ws://127.0.0.1:$OPENCLAW_GATEWAY_PORT"', self.bootstrap_script
        )
        self.assertNotIn("sudo -u {5} env HOME=/home/{5}", self.bootstrap_script)
        self.assertIn("openclaw pairing list msteams --json", self.bootstrap_script)
        self.assertIn('code="$pairing_code"', self.bootstrap_script)
        self.assertIn(
            "text = sys.stdin.read(); start = text.find(chr(123))",
            self.bootstrap_script,
        )
        self.assertIn('pairing approve msteams "$1" --notify', self.bootstrap_script)
        self.assertNotIn(
            "python3 is required for automatic public CLI pairing",
            self.bootstrap_script,
        )
        self.assertIn(
            "text = sys.stdin.read(); start = text.find(chr(123))",
            arm_bootstrap_script,
        )
        self.assertIn("command -v openclaw >/dev/null 2>&1", arm_bootstrap_script)
        self.assertIn(
            "openclaw gateway call device.pair.list --json --params",
            arm_bootstrap_script,
        )
        self.assertIn(
            "openclaw gateway call device.pair.approve --json --params",
            arm_bootstrap_script,
        )
        self.assertIn("list_browser_request_id()", arm_bootstrap_script)
        self.assertIn("approve_browser_request()", arm_bootstrap_script)
        self.assertIn("text.find(chr(123))", arm_bootstrap_script)
        self.assertIn("payload.get(''device'') or {{}}", arm_bootstrap_script)
        self.assertNotIn('PAIRING_LIST_JS_B64="', arm_bootstrap_script)
        self.assertNotIn('PAIRING_APPROVE_JS_B64="', arm_bootstrap_script)
        self.assertIn("set -eux\n", arm_bootstrap_script)
        self.assertNotIn("set -euxo pipefail", arm_bootstrap_script)
        self.assertIn(
            "No pending browser pairing requests. Keep the dashboard page open on the pairing screen, wait a few seconds, and try again.",
            arm_bootstrap_script,
        )
        self.assertIn("2>&1", arm_bootstrap_script)
        self.assertIn(
            "Approving browser pairing request: $request_id", arm_bootstrap_script
        )
        self.assertNotIn("openclaw devices approve --latest", arm_bootstrap_script)
        self.assertNotIn(
            'gateway_url="ws://127.0.0.1:$OPENCLAW_GATEWAY_PORT"', arm_bootstrap_script
        )
        self.assertNotIn("sudo -u {5} env HOME=/home/{5}", arm_bootstrap_script)
        self.assertNotIn(
            "openclaw plugins install @openclaw/msteams", self.bootstrap_script
        )
        self.assertNotIn("/data/extensions/msteams", arm_bootstrap_script)
        self.assertNotIn(
            "printf '%s' '{2}' | base64 -d > /home/{5}/.openclaw/openclaw.json",
            self.bootstrap_script,
        )
        self.assertIn("OPENCLAW_ALLOWED_ORIGINS_JSON='{13}'", self.bootstrap_script)
        self.assertIn(
            "Environment=PATH=/home/{5}/.openclaw/tools/node/bin:/home/{5}/.openclaw/bin:/usr/local/bin:/usr/bin:/bin",
            self.bootstrap_script,
        )
        self.assertNotIn(
            "cat > /etc/systemd/system/openclaw-gateway.service",
            self.bootstrap_script,
        )
        self.assertNotIn(
            "systemctl enable openclaw-gateway caddy", self.bootstrap_script
        )

    def test_readme_documents_manual_browser_pairing_fallback(self):
        self.assertIn("openclaw-approve-browser", self.readme)
        self.assertIn("uses the official OpenClaw CLI gateway call", self.readme)
        self.assertIn(
            "OpenClaw 上游 `2026.3.12` 到 `2026.3.13` 期间存在已知的 loopback WebSocket 握手回归",
            self.readme,
        )
        self.assertIn(
            "Known upstream note: OpenClaw `2026.3.12` through `2026.3.13` has a reported loopback WebSocket handshake regression",
            self.readme,
        )
        self.assertNotIn("reads the local browser pairing queue directly", self.readme)
        self.assertNotIn(
            "If you need to temporarily restore that wrapper path on an already deployed VM",
            self.readme,
        )
        self.assertNotIn(
            "This workaround is an emergency literal replacement against the current upstream dist bundles.",
            self.readme,
        )

    def test_readme_documents_gateway_mode_switching(self):
        self.assertIn("openclaw-use-public-gateway", self.readme)
        self.assertIn("openclaw-use-loopback-gateway", self.readme)
        self.assertIn("openclaw-gateway-mode current", self.readme)
        self.assertIn("reconnect SSH", self.readme)
        self.assertIn("current local device identity", self.readme)
        self.assertIn("openclaw health --verbose", self.readme)

    def test_readme_documents_homebrew_and_passwordless_sudo(self):
        self.assertIn("Homebrew", self.readme)
        self.assertIn("passwordless sudo", self.readme)
        self.assertIn("/home/linuxbrew/.linuxbrew", self.readme)

    def test_bootstrap_script_arm_format_expression_is_well_formed(self):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]
        format_string = extract_arm_format_string(arm_bootstrap_script)

        self.assertIn(
            'openclaw gateway call device.pair.list --json --params "{{}}"',
            format_string,
        )
        self.assertIn("OPENCLAW_ALLOWED_ORIGINS_JSON='{13}'", format_string)
        self.assertIn("run_openclaw_config_string() {{", format_string)

        validate_arm_format_literal(format_string)

        for match in re.finditer(r"(?<!\{)\{([^{}]+)\}(?!\})", format_string):
            self.assertRegex(match.group(1), r"^\d+$")
            self.assertLessEqual(int(match.group(1)), 13)

    def test_generated_bootstrap_artifacts_are_in_sync(self):
        self.assertTrue(DEFAULT_ARM_STRING_PATH.exists())
        self.assertTrue(DEFAULT_ARM_EXPRESSION_PATH.exists())
        self.assertNotIn(
            "# Extracted from azuredeploy.json variables.bootstrapScript for easier review.",
            self.expected_arm_expression,
        )
        self.assertNotIn("# ARM format placeholders:", self.expected_arm_expression)
        self.assertTrue(
            self.expected_arm_expression.startswith("[format('#!/usr/bin/env bash")
        )
        self.assertEqual(
            DEFAULT_ARM_EXPRESSION_PATH.read_text(encoding="utf-8").strip(),
            self.expected_arm_expression,
        )
        self.assertEqual(
            self.template["variables"]["bootstrapScript"],
            self.expected_arm_expression,
        )

    def test_extracted_helper_templates_are_in_sync(self):
        for script_name, path in HELPER_TEMPLATE_PATHS.items():
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                extract_embedded_script(self.bootstrap_script, script_name),
            )

    def test_readme_documents_user_prefix_update_path(self):
        self.assertIn("官方 `install-cli.sh` 安装器", self.readme)
        self.assertIn("24.14.0", self.readme)
        self.assertIn("openclaw update", self.readme)
        self.assertIn("install-cli.sh", self.readme)
        self.assertIn("official `install-cli.sh` installer", self.readme)
        self.assertIn("onboard --non-interactive", self.readme)
        self.assertIn("--install-daemon", self.readme)
        self.assertIn("openclaw config", self.readme)

    def test_local_teams_app_package_template_exists(self):
        build_script = REPO_ROOT / "teams-app-package" / "build-app-package.ps1"
        readme = REPO_ROOT / "teams-app-package" / "README.md"
        quickstart_manifest = (
            REPO_ROOT / "teams-app-package" / "manifest.quickstart.template.json"
        )
        import_test_manifest = (
            REPO_ROOT / "teams-app-package" / "manifest.import-test.template.json"
        )

        self.assertTrue(build_script.exists())
        self.assertTrue(readme.exists())
        self.assertTrue(quickstart_manifest.exists())
        self.assertTrue(import_test_manifest.exists())
        self.assertIn("MicrosoftTeams.schema.json", self.teams_manifest_template)
        self.assertIn('"__APP_ID__"', self.teams_manifest_template)
        self.assertIn('"__PACKAGE_ID__"', self.teams_manifest_template)
        self.assertIn('"validDomains"', self.teams_manifest_template)
        self.assertIn('"OpenClaw"', self.teams_quickstart_manifest_template)
        self.assertIn('"__APP_ID__"', self.teams_quickstart_manifest_template)
        self.assertIn('"personal"', self.teams_import_test_manifest_template)
        self.assertNotIn('"team"', self.teams_import_test_manifest_template)
        self.assertNotIn('"groupChat"', self.teams_import_test_manifest_template)
        self.assertNotIn('"authorization"', self.teams_import_test_manifest_template)

    def test_env_example_contains_teams_e2e_variables(self):
        self.assertIn("TEST_RUN_INTEGRATION=0", self.env_example)
        self.assertIn("TEST_MSTEAMS_APP_ID=", self.env_example)
        self.assertIn("TEST_MSTEAMS_APP_PASSWORD=", self.env_example)
        self.assertIn("TEST_MSTEAMS_BOT_DOMAIN=", self.env_example)
        self.assertIn("TEST_OPENCLAW_PUBLIC_URL=", self.env_example)

    def test_ui_definition_contains_core_metadata(self):
        self.assertEqual(
            self.ui_definition["$schema"],
            "https://schema.management.azure.com/schemas/0.1.2-preview/CreateUIDefinition.MultiVm.json#",
        )
        self.assertEqual(self.ui_definition["handler"], "Microsoft.Azure.CreateUIDef")
        self.assertEqual(self.ui_definition["version"], "0.1.2-preview")

    def test_ui_definition_contains_expected_steps_and_outputs(self):
        parameters = self.ui_definition["parameters"]
        basics = parameters["basics"]
        vm_size_element = next(
            element for element in basics if element["name"] == "vmSize"
        )
        self.assertEqual(vm_size_element["type"], "Microsoft.Compute.SizeSelector")
        self.assertEqual(vm_size_element["osPlatform"], "Linux")
        self.assertEqual(vm_size_element["count"], 1)
        self.assertEqual(
            vm_size_element["recommendedSizes"],
            ["Standard_B2as_v2", "Standard_D2as_v5", "Standard_D4as_v5"],
        )
        self.assertNotIn("constraints", vm_size_element)

        steps = parameters["steps"]
        step_names = [step["name"] for step in steps]
        self.assertEqual(step_names, ["openai", "feishu", "teams"])

        feishu_step = next(step for step in steps if step["name"] == "feishu")
        teams_step = next(step for step in steps if step["name"] == "teams")
        feishu_element_names = [element["name"] for element in feishu_step["elements"]]
        teams_element_names = [element["name"] for element in teams_step["elements"]]
        self.assertIn("feishuAppId", feishu_element_names)
        self.assertIn("feishuAppSecret", feishu_element_names)
        self.assertIn("msteamsAppId", teams_element_names)
        self.assertIn("msteamsAppPassword", teams_element_names)

        outputs = parameters["outputs"]
        self.assertEqual(outputs["vmSize"], "[basics('vmSize')]")
        self.assertEqual(outputs["location"], "[location()]")
        self.assertEqual(outputs["feishuAppId"], "[steps('feishu').feishuAppId]")
        self.assertEqual(
            outputs["msteamsAppPassword"],
            "[steps('teams').msteamsAppPassword.password]",
        )

    def test_template_outputs_include_teams_bot_name(self):
        outputs = self.template["outputs"]
        self.assertIn("teamsBotName", outputs)
        self.assertEqual(outputs["teamsBotName"]["type"], "string")
        self.assertEqual(
            outputs["teamsBotName"]["value"],
            "[if(variables('hasMsTeamsConfig'), variables('botServiceName'), '')]",
        )

    def test_azure_openai_auth_mode_parameter_exists(self):
        parameters = self.template["parameters"]
        self.assertIn("azureOpenAiAuthMode", parameters)
        self.assertEqual(parameters["azureOpenAiAuthMode"]["type"], "string")
        self.assertEqual(parameters["azureOpenAiAuthMode"]["defaultValue"], "none")
        self.assertEqual(
            sorted(parameters["azureOpenAiAuthMode"]["allowedValues"]),
            ["key", "managedIdentity", "none"],
        )

    def test_azure_openai_effective_auth_mode_variable_exists(self):
        variables = self.template["variables"]
        self.assertIn("azureOpenAiEffectiveAuthMode", variables)
        self.assertIn(
            "parameters('azureOpenAiAuthMode')",
            variables["azureOpenAiEffectiveAuthMode"],
        )
        self.assertIn("isManagedIdentityAuth", variables)
        self.assertIn("managedIdentity", variables["isManagedIdentityAuth"])
        self.assertIn("azureOpenAiResourceName", variables)
        self.assertIn("resolvedAzureOpenAiResourceGroup", variables)
        self.assertIn("cognitiveServicesOpenAiUserRoleId", variables)
        self.assertEqual(
            variables["cognitiveServicesOpenAiUserRoleId"],
            "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
        )
        self.assertIn("roleAssignmentName", variables)

    def test_azure_openai_validation_supports_managed_identity(self):
        variables = self.template["variables"]
        validation = variables["azureOpenAiValidationMode"]
        self.assertIn("azureOpenAiAuthMode", validation)
        self.assertIn("managedIdentity", validation)
        self.assertIn(
            "azureOpenAiEndpoint",
            validation,
        )

    def test_template_outputs_include_vm_principal_id_and_auth_mode(self):
        outputs = self.template["outputs"]
        self.assertIn("vmPrincipalId", outputs)
        self.assertEqual(outputs["vmPrincipalId"]["type"], "string")
        self.assertIn("identity.principalId", outputs["vmPrincipalId"]["value"])
        self.assertIn("azureOpenAiAuthMode", outputs)
        self.assertEqual(outputs["azureOpenAiAuthMode"]["type"], "string")
        self.assertIn("azureOpenAiRoleAssignmentHint", outputs)
        self.assertEqual(outputs["azureOpenAiRoleAssignmentHint"]["type"], "string")
        self.assertIn(
            "Cognitive Services OpenAI User",
            outputs["azureOpenAiRoleAssignmentHint"]["value"],
        )

    def test_vm_has_system_assigned_identity(self):
        vm_resources = [
            r
            for r in self.template["resources"]
            if r["type"] == "Microsoft.Compute/virtualMachines"
        ]
        self.assertEqual(len(vm_resources), 1)
        self.assertEqual(vm_resources[0]["identity"]["type"], "SystemAssigned")

    def test_role_assignment_resource_is_non_blocking(self):
        role_assignment_deployments = [
            r
            for r in self.template["resources"]
            if r["type"] == "Microsoft.Resources/deployments"
            and r.get("name") == "azureOpenAiRoleAssignment"
        ]
        self.assertEqual(len(role_assignment_deployments), 1)
        deployment = role_assignment_deployments[0]
        self.assertEqual(
            deployment["condition"], "[variables('isManagedIdentityAuth')]"
        )
        # Verify no other resource depends on the role assignment
        role_assignment_resource_id = "azureOpenAiRoleAssignment"
        for resource in self.template["resources"]:
            depends_on = resource.get("dependsOn", [])
            for dep in depends_on:
                self.assertNotIn(
                    role_assignment_resource_id,
                    dep,
                    f"Resource {resource.get('name', resource['type'])} must not depend on role assignment",
                )
        # Verify the bootstrap extension only depends on the VM, not the role assignment
        bootstrap_extensions = [
            r
            for r in self.template["resources"]
            if r["type"] == "Microsoft.Compute/virtualMachines/extensions"
        ]
        self.assertEqual(len(bootstrap_extensions), 1)
        bootstrap_deps = bootstrap_extensions[0].get("dependsOn", [])
        for dep in bootstrap_deps:
            self.assertNotIn(
                "azureOpenAiRoleAssignment",
                dep,
                "Bootstrap extension must not depend on role assignment",
            )

    def test_azure_openai_resource_group_parameter_exists(self):
        parameters = self.template["parameters"]
        self.assertIn("azureOpenAiResourceGroup", parameters)
        self.assertEqual(parameters["azureOpenAiResourceGroup"]["defaultValue"], "")

    def test_bootstrap_script_contains_managed_identity_proxy(self):
        self.assertIn("OPENCLAW_AZURE_OPENAI_AUTH_MODE='{2}'", self.bootstrap_script)
        self.assertIn("azure-openai-mi-proxy", self.bootstrap_script)
        self.assertIn("TokenManager", self.bootstrap_script)
        self.assertIn(
            "169.254.169.254/metadata/identity/oauth2/token",
            self.bootstrap_script,
        )
        self.assertIn("cognitiveservices.azure.com", self.bootstrap_script)
        self.assertIn("azure-openai-mi-proxy.service", self.bootstrap_script)
        self.assertIn(
            'if [ "$OPENCLAW_AZURE_OPENAI_AUTH_MODE" = "managedIdentity" ]',
            self.bootstrap_script,
        )
        self.assertIn('"apiKey": "managed-identity"', self.bootstrap_script)
        self.assertIn(
            '"apiKey": "$OPENCLAW_AZURE_OPENAI_API_KEY"', self.bootstrap_script
        )

    def test_bootstrap_script_sets_model_allowlist(self):
        self.assertIn(
            'run_openclaw_config_json agents.defaults.models "{\\"openai/$OPENCLAW_AZURE_OPENAI_DEPLOYMENT\\":{}}"',
            self.bootstrap_script,
        )

    def test_ui_definition_contains_auth_mode_dropdown(self):
        steps = self.ui_definition["parameters"]["steps"]
        openai_step = next(step for step in steps if step["name"] == "openai")
        element_names = [e["name"] for e in openai_step["elements"]]
        self.assertIn("azureOpenAiAuthMode", element_names)
        self.assertIn("azureOpenAiAuthModeChina", element_names)
        self.assertIn("managedIdentityInfo", element_names)
        self.assertIn("azureOpenAiResourceGroup", element_names)

        auth_mode_element = next(
            e for e in openai_step["elements"] if e["name"] == "azureOpenAiAuthMode"
        )
        self.assertEqual(auth_mode_element["type"], "Microsoft.Common.DropDown")
        allowed_values = [
            v["value"] for v in auth_mode_element["constraints"]["allowedValues"]
        ]
        self.assertEqual(sorted(allowed_values), ["key", "managedIdentity", "none"])

        auth_mode_china = next(
            e
            for e in openai_step["elements"]
            if e["name"] == "azureOpenAiAuthModeChina"
        )
        self.assertEqual(auth_mode_china["type"], "Microsoft.Common.DropDown")
        china_values = [
            v["value"] for v in auth_mode_china["constraints"]["allowedValues"]
        ]
        self.assertEqual(sorted(china_values), ["key", "none"])
        self.assertNotIn("managedIdentity", china_values)

        rg_element = next(
            e
            for e in openai_step["elements"]
            if e["name"] == "azureOpenAiResourceGroup"
        )
        self.assertEqual(rg_element["type"], "Microsoft.Common.TextBox")

        outputs = self.ui_definition["parameters"]["outputs"]
        self.assertIn("azureOpenAiAuthMode", outputs)
        self.assertIn("azureOpenAiResourceGroup", outputs)

    def test_ui_definition_hides_managed_identity_in_china(self):
        steps = self.ui_definition["parameters"]["steps"]
        openai_step = next(step for step in steps if step["name"] == "openai")

        global_dropdown = next(
            e for e in openai_step["elements"] if e["name"] == "azureOpenAiAuthMode"
        )
        china_dropdown = next(
            e
            for e in openai_step["elements"]
            if e["name"] == "azureOpenAiAuthModeChina"
        )

        # Global dropdown visible only in non-China
        self.assertIn("not(startsWith(location()", global_dropdown["visible"])
        # China dropdown visible only in China
        self.assertIn("startsWith(location()", china_dropdown["visible"])

        # Output conditionally picks the correct dropdown
        outputs = self.ui_definition["parameters"]["outputs"]
        auth_mode_output = outputs["azureOpenAiAuthMode"]
        self.assertIn("startsWith(location()", auth_mode_output)
        self.assertIn("azureOpenAiAuthModeChina", auth_mode_output)
        self.assertIn("azureOpenAiAuthMode", auth_mode_output)

    def test_readme_documents_managed_identity_option(self):
        self.assertIn("Managed Identity", self.readme)
        self.assertIn("Cognitive Services OpenAI User", self.readme)
        self.assertIn("vmPrincipalId", self.readme)

    def test_readme_documents_teams_setup_steps(self):
        self.assertIn("Microsoft Entra ID", self.readme)
        self.assertIn("openclaw-teams-bot", self.readme)
        self.assertIn("Teams Bot App ID", self.readme)
        self.assertIn("Teams Bot App Password", self.readme)
        self.assertIn("openclaw-approve-teams-pairing", self.readme)
        self.assertIn("build-app-package.ps1", self.readme)
        self.assertIn("Upload a custom app", self.readme)
        self.assertIn("pairing code", self.readme)


if __name__ == "__main__":
    unittest.main()
