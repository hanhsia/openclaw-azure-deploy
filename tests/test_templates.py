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
        self.assertIn("cloudapp.chinacloudapi.cn", variables["publicDnsSuffix"])
        self.assertIn("cloudapp.azure.com", variables["publicDnsSuffix"])
        self.assertIn("variables('publicDnsSuffix')", variables["publicFqdn"])

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

    def test_bootstrap_script_exports_feishu_credentials(self):
        self.assertIn("FEISHU_APP_ID={6}", self.bootstrap_script)
        self.assertIn("FEISHU_APP_SECRET={7}", self.bootstrap_script)
        self.assertIn('FEISHU_APP_ID="$FEISHU_APP_ID"', self.bootstrap_script)
        self.assertIn('FEISHU_APP_SECRET="$FEISHU_APP_SECRET"', self.bootstrap_script)

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

        steps = self.ui_definition["parameters"]["steps"]
        step_names = [step["name"] for step in steps]
        self.assertEqual(step_names, ["openai", "feishu"])

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

        feishu_secret = next(
            element
            for element in feishu_step["elements"]
            if element["name"] == "feishuAppSecret"
        )
        self.assertTrue(feishu_secret["options"]["hideConfirmation"])

        outputs = self.ui_definition["parameters"]["outputs"]
        self.assertEqual(outputs["vmName"], "[basics('vmName')]")
        self.assertEqual(
            outputs["feishuAppSecret"], "[steps('feishu').feishuAppSecret.password]"
        )

    def test_readme_mentions_create_ui_definition_and_test_command(self):
        self.assertIn("Deploy to Azure", self.readme)
        self.assertIn("feishuAppId", self.readme)
        self.assertIn("openclaw-browser-url", self.readme)
        self.assertIn("createUIDefinitionUri", self.readme)
        self.assertIn("createUiDefinition.json", self.readme)


if __name__ == "__main__":
    unittest.main()
