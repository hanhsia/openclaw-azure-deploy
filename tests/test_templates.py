import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_CLOUD = "AzureCloud"
GLOBAL_LOCATION = "eastasia"
CHINA_CLOUD = "AzureChinaCloud"
CHINA_LOCATION = "chinanorth3"
DEFAULT_VM_NAME = "openclawtestvm"
DEFAULT_HOSTNAME = ""


def load_json(relative_path: str):
    return json.loads((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def extract_arm_format_string(expression: str) -> str:
    prefix = "[format('"
    suffix = ")]"
    if not expression.startswith(prefix) or not expression.endswith(suffix):
        raise ValueError("Expression is not an ARM format() call.")

    body = expression[len("[format(") : -2]
    if not body or body[0] != "'":
        raise ValueError(
            "ARM format() expression does not start with a string literal."
        )

    chars = []
    index = 1
    while index < len(body):
        char = body[index]
        if char == "'":
            if index + 1 < len(body) and body[index + 1] == "'":
                chars.append("'")
                index += 2
                continue

            remainder = body[index + 1 :]
            if not remainder.startswith(", string(variables('openclawPort')),"):
                raise ValueError(
                    "ARM format() string literal does not terminate before the expected argument list."
                )
            return "".join(chars)

        chars.append(char)
        index += 1

    raise ValueError("ARM format() string literal was not terminated.")


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
        cls.bootstrap_script = (REPO_ROOT / "bootstrapScript.template.sh").read_text(
            encoding="utf-8"
        )
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
        self.assertEqual(channels["feishu"]["dmPolicy"], "open")
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
        self.assertEqual(channels["msteams"]["tenantId"], "[subscription().tenantId]")
        gateway = self.openclaw_config_template["gateway"]
        self.assertEqual(gateway["trustedProxies"], ["127.0.0.1", "::1"])

    def test_feishu_channel_defaults_to_open_dm(self):
        feishu_json = self.template["variables"]["openclawFeishuJson"]
        self.assertIn('"dmPolicy": "open"', feishu_json)
        self.assertIn('"groupPolicy": "open"', feishu_json)
        self.assertNotIn('"dmPolicy": "pairing"', feishu_json)

    def test_channel_fragments_do_not_duplicate_channels_wrapper(self):
        variables = self.template["variables"]
        self.assertNotIn('  "channels": {', variables["openclawFeishuJson"])
        self.assertNotIn('  "channels": {', variables["openclawMsTeamsJson"])
        self.assertIn('    "feishu": {', variables["openclawFeishuJson"])
        self.assertIn('    "msteams": {', variables["openclawMsTeamsJson"])

    def test_bootstrap_script_exports_feishu_credentials(self):
        self.assertIn("FEISHU_APP_ID={6}", self.bootstrap_script)
        self.assertIn("FEISHU_APP_SECRET={7}", self.bootstrap_script)
        self.assertIn('FEISHU_APP_ID="$FEISHU_APP_ID"', self.bootstrap_script)
        self.assertIn('FEISHU_APP_SECRET="$FEISHU_APP_SECRET"', self.bootstrap_script)

    def test_bootstrap_script_exports_msteams_credentials_and_installs_bundled_dependencies(
        self,
    ):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]

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
            "https://deb.nodesource.com/node_24.x nodistro main",
            self.bootstrap_script,
        )
        self.assertIn("npm install -g openclaw@latest", self.bootstrap_script)
        self.assertIn(
            'OPENCLAW_BIN="$(command -v openclaw || true)"', self.bootstrap_script
        )
        self.assertIn(
            'OPENCLAW_PACKAGE_DIR="$(npm root -g)/openclaw"', self.bootstrap_script
        )
        self.assertIn(
            'OPENCLAW_MSTEAMS_DIR="$OPENCLAW_PACKAGE_DIR/extensions/msteams"',
            self.bootstrap_script,
        )
        self.assertIn(
            'npm install --omit=dev --prefix "$OPENCLAW_MSTEAMS_DIR"',
            self.bootstrap_script,
        )
        self.assertIn(
            "Bundled MSTeams plugin package was not found at $OPENCLAW_MSTEAMS_DIR",
            self.bootstrap_script,
        )
        self.assertIn(
            'ln -sf "$OPENCLAW_BIN" /usr/local/bin/openclaw',
            self.bootstrap_script,
        )
        self.assertIn('MSTEAMS_APP_ID="$MSTEAMS_APP_ID"', self.bootstrap_script)
        self.assertIn(
            'MSTEAMS_APP_PASSWORD="$MSTEAMS_APP_PASSWORD"', self.bootstrap_script
        )
        self.assertIn("openclaw pairing list msteams --json", self.bootstrap_script)
        self.assertIn(
            "text = sys.stdin.read(); start = text.find(chr(123))",
            self.bootstrap_script,
        )
        self.assertIn(
            'openclaw pairing approve msteams "$code" --notify',
            self.bootstrap_script,
        )
        self.assertIn("sudo bash -lc '", self.bootstrap_script)
        self.assertNotIn("python3 -c '", self.bootstrap_script)
        self.assertIn("sudo bash -lc", arm_bootstrap_script)
        self.assertIn(
            "text = sys.stdin.read(); start = text.find(chr(123))",
            arm_bootstrap_script,
        )
        self.assertIn('python3 -c "import json, sys;', arm_bootstrap_script)
        self.assertNotIn("python3 -c ''", arm_bootstrap_script)
        self.assertNotIn(
            "openclaw plugins install @openclaw/msteams", self.bootstrap_script
        )
        self.assertNotIn("/data/extensions/msteams", arm_bootstrap_script)

    def test_bootstrap_script_arm_format_expression_is_well_formed(self):
        arm_bootstrap_script = self.template["variables"]["bootstrapScript"]
        format_string = extract_arm_format_string(arm_bootstrap_script)

        self.assertIn("sudo bash -lc '\n", format_string)
        self.assertIn(
            "printf '%s' '{2}' | base64 -d > /data/openclaw.json", format_string
        )

        for match in re.finditer(r"\{([^{}]+)\}", format_string):
            self.assertRegex(match.group(1), r"^\d+$")

    def test_readme_documents_global_npm_update_path(self):
        self.assertIn("系统 Node.js + npm 全局安装", self.readme)
        self.assertIn("sudo npm i -g openclaw@latest", self.readme)
        self.assertIn("system Node.js + global npm install", self.readme)

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
