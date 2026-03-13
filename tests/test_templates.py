import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GLOBAL_CLOUD = "AzureCloud"
GLOBAL_LOCATION = "eastasia"
CHINA_CLOUD = "AzureChinaCloud"
CHINA_LOCATION = "chinanorth3"
DEFAULT_VM_NAME = "openclawtestvm"
DEFAULT_HOSTNAME = ""


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
    return env


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

    def test_openclaw_config_template_contains_msteams_placeholders(self):
        channels = self.openclaw_config_template["channels"]
        self.assertIn("msteams", channels)
        self.assertEqual(channels["msteams"]["appId"], "${MSTEAMS_APP_ID}")
        self.assertEqual(channels["msteams"]["appPassword"], "${MSTEAMS_APP_PASSWORD}")
        self.assertEqual(channels["msteams"]["tenantId"], "[subscription().tenantId]")

    def test_feishu_channel_defaults_to_open_dm(self):
        feishu_json = self.template["variables"]["openclawFeishuJson"]
        self.assertIn('"dmPolicy": "open"', feishu_json)
        self.assertIn('"groupPolicy": "open"', feishu_json)
        self.assertNotIn('"dmPolicy": "pairing"', feishu_json)

    def test_openclaw_config_template_contains_feishu_placeholders(self):
        channels = self.openclaw_config_template["channels"]
        self.assertIn("feishu", channels)
        self.assertEqual(channels["feishu"]["dmPolicy"], "open")
        self.assertEqual(
            channels["feishu"]["accounts"]["main"]["appId"], "${FEISHU_APP_ID}"
        )
        self.assertEqual(
            channels["feishu"]["accounts"]["main"]["appSecret"], "${FEISHU_APP_SECRET}"
        )

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

    def test_bootstrap_script_exports_msteams_credentials_and_installs_plugin(self):
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
        self.assertIn(
            "npm install -g openclaw@latest",
            self.bootstrap_script,
        )
        self.assertIn(
            'OPENCLAW_BIN="$(command -v openclaw || true)"', self.bootstrap_script
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
        self.assertIn(
            "openclaw plugins install @openclaw/msteams", self.bootstrap_script
        )
        self.assertIn(". /etc/openclaw/openclaw.env", self.bootstrap_script)
        self.assertIn(
            'sudo -u {5} env HOME=/home/{5} OPENCLAW_HOME=/home/{5} OPENCLAW_STATE_DIR=/data OPENCLAW_CONFIG_PATH=/data/openclaw.json OPENCLAW_GATEWAY_TOKEN="$OPENCLAW_GATEWAY_TOKEN" OPENAI_API_KEY="$OPENAI_API_KEY" FEISHU_APP_ID="$FEISHU_APP_ID" FEISHU_APP_SECRET="$FEISHU_APP_SECRET" MSTEAMS_APP_ID="$MSTEAMS_APP_ID" MSTEAMS_APP_PASSWORD="$MSTEAMS_APP_PASSWORD" MSTEAMS_TENANT_ID="$MSTEAMS_TENANT_ID" /usr/local/bin/openclaw plugins install @openclaw/msteams',
            self.bootstrap_script,
        )

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

    def test_custom_ui_contains_dedicated_feishu_step(self):
        self.assertEqual(
            self.ui_definition["$schema"],
            "https://schema.management.azure.com/schemas/0.1.2-preview/CreateUIDefinition.MultiVm.json#",
        )
        self.assertEqual(self.ui_definition["handler"], "Microsoft.Azure.CreateUIDef")
        self.assertEqual(self.ui_definition["version"], "0.1.2-preview")
        self.assertTrue(self.ui_definition["parameters"]["config"]["isWizard"])

        basics = self.ui_definition["parameters"]["basics"]
        basic_names = [element["name"] for element in basics]
        self.assertIn("vmName", basic_names)
        self.assertIn("sshPublicKey", basic_names)
        self.assertNotIn("resourceLocation", basic_names)

        location_control = self.ui_definition["parameters"]["config"]["basics"][
            "location"
        ]
        self.assertEqual(location_control["label"], "Region")

        steps = self.ui_definition["parameters"]["steps"]
        step_names = [step["name"] for step in steps]
        self.assertEqual(step_names, ["openai", "feishu", "teams"])

        feishu_step = next(step for step in steps if step["name"] == "feishu")
        element_names = [element["name"] for element in feishu_step["elements"]]
        self.assertIn("feishuAppId", element_names)
        self.assertIn("feishuAppSecret", element_names)

        openai_step = next(step for step in steps if step["name"] == "openai")
        openai_api_key = next(
            element
            for element in openai_step["elements"]
            if element["name"] == "azureOpenAiApiKey"
        )
        self.assertTrue(openai_api_key["options"]["hideConfirmation"])
        self.assertEqual(openai_api_key["label"]["password"], "API Key")

        feishu_secret = next(
            element
            for element in feishu_step["elements"]
            if element["name"] == "feishuAppSecret"
        )
        self.assertTrue(feishu_secret["options"]["hideConfirmation"])
        self.assertEqual(feishu_secret["label"]["password"], "Feishu App Secret")

        teams_step = next(step for step in steps if step["name"] == "teams")
        teams_names = [element["name"] for element in teams_step["elements"]]
        self.assertEqual(teams_names, ["msteamsAppId", "msteamsAppPassword"])

        teams_password = next(
            element
            for element in teams_step["elements"]
            if element["name"] == "msteamsAppPassword"
        )
        self.assertTrue(teams_password["options"]["hideConfirmation"])
        self.assertEqual(teams_password["label"]["password"], "Bot App Password")

        outputs = self.ui_definition["parameters"]["outputs"]
        self.assertEqual(outputs["vmName"], "[basics('vmName')]")
        self.assertEqual(outputs["location"], "[location()]")
        self.assertEqual(
            outputs["feishuAppSecret"], "[steps('feishu').feishuAppSecret.password]"
        )
        self.assertEqual(outputs["msteamsAppId"], "[steps('teams').msteamsAppId]")
        self.assertEqual(
            outputs["msteamsAppPassword"],
            "[steps('teams').msteamsAppPassword.password]",
        )

    def test_readme_mentions_create_ui_definition_and_test_command(self):
        self.assertIn("Deploy to Azure", self.readme)
        self.assertIn("feishuAppId", self.readme)
        self.assertIn("msteamsAppId", self.readme)
        self.assertIn("openclaw-browser-url", self.readme)
        self.assertIn("createUIDefinitionUri", self.readme)
        self.assertIn("createUiDefinition.json", self.readme)


if __name__ == "__main__":
    unittest.main()
