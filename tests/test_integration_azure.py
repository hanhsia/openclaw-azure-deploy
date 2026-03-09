import json
import os
import subprocess
import unittest
import uuid
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = REPO_ROOT / "azuredeploy.json"

GLOBAL_CLOUD = "AzureCloud"
GLOBAL_LOCATION = "eastasia"
CHINA_CLOUD = "AzureChinaCloud"
CHINA_LOCATION = "chinanorth3"
DEFAULT_ADMIN_USERNAME = "azureuser"
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


def run_az(args, cloud_name):
    command = subprocess.list2cmdline(["az", *args])
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        shell=True,
        env={**os.environ, "AZURE_CORE_CLOUD": cloud_name},
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"az {' '.join(args)} failed for {cloud_name}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed.stdout


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

    def setUp(self):
        if self.env.get("TEST_RUN_INTEGRATION", "0") != "1":
            self.skipTest(
                "Set TEST_RUN_INTEGRATION=1 in .env to enable real Azure integration tests."
            )
        if not self.env.get("TEST_SSH_PUBLIC_KEY", "").strip():
            self.skipTest(
                "Set TEST_SSH_PUBLIC_KEY in .env before running integration tests."
            )

    def _deploy_and_cleanup(self, cloud_name, location, subscription_id_env_key):
        if not is_logged_in(cloud_name):
            self.skipTest(f"Azure CLI is not logged in for {cloud_name}.")

        subscription_id = self.env.get(subscription_id_env_key, "").strip()
        if subscription_id:
            run_az(["account", "set", "--subscription", subscription_id], cloud_name)

        suffix = uuid.uuid4().hex[:8]
        resource_group_prefix = (
            self.env.get("TEST_RESOURCE_GROUP_PREFIX", "openclawtest").strip()
            or "openclawtest"
        )
        resource_group_name = f"{resource_group_prefix}-{cloud_name.lower()}-{suffix}"
        vm_name = f"openclaw{suffix}"
        rg_created = False

        parameters = [
            f"vmName={vm_name}",
            f"adminUsername={DEFAULT_ADMIN_USERNAME}",
            f"sshPublicKey={self.env['TEST_SSH_PUBLIC_KEY']}",
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

            deployment_name = f"deploy-{suffix}"
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

            payload = json.loads(deployment_output)
            outputs = payload["properties"]["outputs"]
            vm_public_fqdn = outputs["vmPublicFqdn"]["value"]
            openclaw_public_url = outputs["openclawPublicUrl"]["value"]

            expected_suffix = (
                ".cloudapp.chinacloudapi.cn"
                if cloud_name == CHINA_CLOUD
                else ".cloudapp.azure.com"
            )
            self.assertTrue(vm_public_fqdn.endswith(expected_suffix))
            self.assertTrue(openclaw_public_url.startswith("https://"))
            self.assertIn(vm_name, vm_public_fqdn)
        finally:
            if rg_created:
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
                run_az(
                    [
                        "group",
                        "wait",
                        "--deleted",
                        "--name",
                        resource_group_name,
                        "--timeout",
                        "1800",
                    ],
                    cloud_name,
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
