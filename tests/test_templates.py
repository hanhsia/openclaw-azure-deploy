import json
import re
import unittest
from pathlib import Path

from scripts.sync_bootstrap_script import (
    DEFAULT_ARM_EXPRESSION_PATH,
    DEFAULT_ARM_STRING_PATH,
    HELPER_TEMPLATE_PATHS,
    build_bootstrap_expression,
    build_openclaw_config_review,
    extract_arm_format_string,
    extract_embedded_script,
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
        cls.openclaw_config_template = load_json("openclawConfig.template.json")
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

    def test_msteams_parameters_are_optional_but_paired_and_global_only(self):
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
        self.assertIn("Azure Global", variables["msteamsValidationMode"])
        self.assertIn("take(parameters('vmName'), 51)", variables["botServiceName"])
        self.assertIn(
            "uniqueString(resourceGroup().id, parameters('msteamsAppId'))",
            variables["botServiceName"],
        )

    def test_openclaw_config_template_contains_channel_placeholders_and_trusted_proxies(
        self,
    ):
        channels = self.openclaw_config_template["channels"]
        self.assertIn("feishu", channels)
        self.assertEqual(channels["feishu"]["accounts"]["default"]["dmPolicy"], "open")
        self.assertEqual(
            channels["feishu"]["accounts"]["default"]["groupPolicy"], "open"
        )
        self.assertEqual(channels["feishu"]["accounts"]["default"]["allowFrom"], ["*"])
        self.assertEqual(
            channels["feishu"]["accounts"]["main"]["appId"], "${FEISHU_APP_ID}"
        )
        self.assertEqual(
            channels["feishu"]["accounts"]["main"]["appSecret"],
            "${FEISHU_APP_SECRET}",
        )
        self.assertIn("msteams", channels)
        self.assertEqual(channels["msteams"]["appId"], "${MSTEAMS_APP_ID}")
        self.assertEqual(channels["msteams"]["appPassword"], "${MSTEAMS_APP_PASSWORD}")
        self.assertEqual(channels["msteams"]["dmPolicy"], "pairing")
        self.assertEqual(channels["msteams"]["groupPolicy"], "open")
        self.assertEqual(channels["msteams"]["tenantId"], "[subscription().tenantId]")
        gateway = self.openclaw_config_template["gateway"]
        self.assertNotIn("trustedProxies", gateway)

    def test_openclaw_config_review_file_is_in_sync(self):
        self.assertEqual(
            self.openclaw_config_template,
            build_openclaw_config_review(self.template),
        )

    def test_feishu_channel_defaults_to_open_dm(self):
        feishu_json = self.template["variables"]["openclawFeishuJson"]
        self.assertIn('"main": {', feishu_json)
        self.assertIn('"default": {', feishu_json)
        self.assertIn('"dmPolicy": "open"', feishu_json)
        self.assertIn('"groupPolicy": "open"', feishu_json)
        self.assertIn('"allowFrom": ["*"]', feishu_json)
        self.assertNotIn('"dmPolicy": "pairing"', feishu_json)

    def test_msteams_channel_defaults_to_open_group_policy(self):
        msteams_json = self.template["variables"]["openclawMsTeamsJson"]
        self.assertIn('"dmPolicy": "pairing"', msteams_json)
        self.assertIn('"groupPolicy": "open"', msteams_json)
        self.assertNotIn('"groupPolicy": "allowlist"', msteams_json)

    def test_channel_fragments_do_not_duplicate_channels_wrapper(self):
        variables = self.template["variables"]
        self.assertNotIn('  "channels": {', variables["openclawFeishuJson"])
        self.assertNotIn('  "channels": {', variables["openclawMsTeamsJson"])
        self.assertIn('    "feishu": {', variables["openclawFeishuJson"])
        self.assertIn('    "msteams": {', variables["openclawMsTeamsJson"])

    def test_bootstrap_script_exports_feishu_credentials(self):
        self.assertIn("FEISHU_APP_ID={6}", self.bootstrap_script)
        self.assertIn("FEISHU_APP_SECRET={7}", self.bootstrap_script)
        self.assertIn("OPENCLAW_STATE_DIR=/home/{5}/.openclaw", self.bootstrap_script)
        self.assertIn(
            "OPENCLAW_CONFIG_PATH=/home/{5}/.openclaw/openclaw.json",
            self.bootstrap_script,
        )
        self.assertNotIn("OPENCLAW_HOME=/home/{5}", self.bootstrap_script)
        self.assertIn(
            "set -a\n  . /etc/openclaw/openclaw.env\n  set +a", self.bootstrap_script
        )
        self.assertIn(
            ". /home/{5}/.openclaw-env.sh && exec /usr/local/bin/openclaw",
            self.bootstrap_script,
        )

    def test_bootstrap_script_exports_msteams_credentials_and_installs_bundled_dependencies(
        self,
    ):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]

        self.assertIn("set -eux\n", self.bootstrap_script)
        self.assertNotIn("set -euxo pipefail", self.bootstrap_script)

        self.assertIn("MSTEAMS_APP_ID={8}", self.bootstrap_script)
        self.assertIn("MSTEAMS_APP_PASSWORD={9}", self.bootstrap_script)
        self.assertIn("MSTEAMS_TENANT_ID={10}", self.bootstrap_script)
        self.assertIn("openclaw-approve-teams-pairing", self.bootstrap_script)
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
            "NODE_COMPILE_CACHE=/home/{5}/.openclaw/cache/node-compile",
            self.bootstrap_script,
        )
        self.assertIn("OPENCLAW_NO_RESPAWN=1", self.bootstrap_script)
        self.assertIn(
            "install -d -o {5} -g {5} /home/{5}/.openclaw/cache/node-compile",
            self.bootstrap_script,
        )
        self.assertIn(
            'sudo -u {5} bash -lc \'cd "$HOME" && curl -fsSL --proto "=https" --tlsv1.2 https://openclaw.ai/install-cli.sh | bash -s -- --prefix "$HOME/.openclaw" --node-version "$1" --no-onboard --json\' _ "$OPENCLAW_NODE_VERSION"',
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
            'OPENCLAW_RUNTIME_NODE_MODULES_DIR="$(sudo -u {5} bash -lc \'export PATH="$(dirname "$1"):$PATH" && "$1" root -g\' _ "$OPENCLAW_NPM_BIN")"',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_RUNTIME_PACKAGE_DIR="$OPENCLAW_RUNTIME_NODE_MODULES_DIR/openclaw"',
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_MSTEAMS_DIR="$OPENCLAW_RUNTIME_PACKAGE_DIR/extensions/msteams"',
            self.bootstrap_script,
        )
        self.assertIn(
            'sudo -u {5} bash -lc \'export PATH="$(dirname "$1"):$PATH" && "$1" install --omit=dev --prefix "$2"\' _ "$OPENCLAW_NPM_BIN" "$OPENCLAW_MSTEAMS_DIR"',
            self.bootstrap_script,
        )
        self.assertIn(
            "OpenClaw MSTeams plugin package was not found at $OPENCLAW_MSTEAMS_DIR",
            self.bootstrap_script,
        )
        self.assertIn(
            "OpenClaw npm binary was not found after install-cli.sh completed: $OPENCLAW_NPM_BIN",
            self.bootstrap_script,
        )
        self.assertIn(
            "OpenClaw runtime package directory was not found after install-cli.sh completed: $OPENCLAW_RUNTIME_PACKAGE_DIR",
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
            ". /home/{5}/.openclaw-env.sh && exec /usr/local/bin/openclaw gateway install --runtime node --force --json",
            self.bootstrap_script,
        )
        self.assertIn(
            "systemctl --user is-active openclaw-gateway",
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_NODE_BIN="/home/{5}/.openclaw/tools/node/bin/node"',
            self.bootstrap_script,
        )
        self.assertIn('PAIRING_LIST_JS_B64="', self.bootstrap_script)
        self.assertIn('PAIRING_APPROVE_JS_B64="', self.bootstrap_script)
        self.assertIn(
            "OpenClaw device pairing module was not found under $OPENCLAW_DIST_DIR",
            self.bootstrap_script,
        )
        self.assertIn(
            "No pending browser pairing requests. Keep the dashboard page open on the pairing screen, wait a few seconds, and try again.",
            self.bootstrap_script,
        )
        self.assertIn(
            "printf '%s' \"$PAIRING_LIST_JS_B64\" | base64 -d", self.bootstrap_script
        )
        self.assertIn("2>&1", self.bootstrap_script)
        self.assertIn(
            "printf '%s' \"$PAIRING_APPROVE_JS_B64\" | base64 -d", self.bootstrap_script
        )
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
        self.assertIn("OPENCLAW_REQUEST_ID:", self.bootstrap_script)
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
        self.assertNotIn("python3 -c '", self.bootstrap_script)
        self.assertIn(
            "text = sys.stdin.read(); start = text.find(chr(123))",
            arm_bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_NODE_BIN="/home/{5}/.openclaw/tools/node/bin/node"',
            arm_bootstrap_script,
        )
        self.assertIn('PAIRING_LIST_JS_B64="', arm_bootstrap_script)
        self.assertIn('PAIRING_APPROVE_JS_B64="', arm_bootstrap_script)
        self.assertIn("set -eux\n", arm_bootstrap_script)
        self.assertNotIn("set -euxo pipefail", arm_bootstrap_script)
        self.assertIn(
            "No pending browser pairing requests. Keep the dashboard page open on the pairing screen, wait a few seconds, and try again.",
            arm_bootstrap_script,
        )
        self.assertIn('PAIRING_LIST_JS_B64="', arm_bootstrap_script)
        self.assertIn(
            'base64 -d | "$OPENCLAW_NODE_BIN" --input-type=module - "$OPENCLAW_PAIRING_MODULE"',
            arm_bootstrap_script,
        )
        self.assertIn("2>&1", arm_bootstrap_script)
        self.assertIn('PAIRING_APPROVE_JS_B64="', arm_bootstrap_script)
        self.assertIn("OPENCLAW_REQUEST_ID:", arm_bootstrap_script)
        self.assertIn(
            "Approving browser pairing request: $request_id", arm_bootstrap_script
        )
        self.assertNotIn("openclaw devices approve --latest", arm_bootstrap_script)
        self.assertNotIn(
            'gateway_url="ws://127.0.0.1:$OPENCLAW_GATEWAY_PORT"', arm_bootstrap_script
        )
        self.assertNotIn("sudo -u {5} env HOME=/home/{5}", arm_bootstrap_script)
        self.assertIn("device-pairing-*.js", arm_bootstrap_script)
        self.assertNotIn(
            "openclaw plugins install @openclaw/msteams", self.bootstrap_script
        )
        self.assertNotIn("/data/extensions/msteams", arm_bootstrap_script)
        self.assertIn(
            "printf '%s' '{2}' | base64 -d > /home/{5}/.openclaw/openclaw.json",
            self.bootstrap_script,
        )
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
        self.assertIn("reads the local browser pairing queue directly", self.readme)

    def test_bootstrap_script_arm_format_expression_is_well_formed(self):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]
        format_string = extract_arm_format_string(arm_bootstrap_script)

        self.assertIn(
            "PAIRING_LIST_JS_B64=",
            format_string,
        )
        self.assertIn(
            "printf '%s' '{2}' | base64 -d > /home/{5}/.openclaw/openclaw.json",
            format_string,
        )

        for match in re.finditer(r"\{([^{}]+)\}", format_string):
            self.assertRegex(match.group(1), r"^\d+$")

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
            DEFAULT_ARM_STRING_PATH.read_text(encoding="utf-8").strip(),
            self.expected_arm_string_literal,
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
        arm_bootstrap_script = extract_arm_format_string(
            self.template["variables"]["bootstrapScript"]
        )

        for script_name, path in HELPER_TEMPLATE_PATHS.items():
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                extract_embedded_script(arm_bootstrap_script, script_name),
            )

    def test_readme_documents_user_prefix_update_path(self):
        self.assertIn("官方 `install-cli.sh` 安装器", self.readme)
        self.assertIn("24.14.0", self.readme)
        self.assertIn("openclaw update", self.readme)
        self.assertIn("install-cli.sh", self.readme)
        self.assertIn("official `install-cli.sh` installer", self.readme)

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


if __name__ == "__main__":
    unittest.main()
