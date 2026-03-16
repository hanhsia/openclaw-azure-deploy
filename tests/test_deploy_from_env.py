import unittest
from unittest.mock import call
from unittest.mock import patch

from scripts.deploy_from_env import build_parameters
from scripts.deploy_from_env import make_rg_unique_name
from scripts.deploy_from_env import reset_resource_group
from scripts.deploy_from_env import resolve_config
from scripts.deploy_from_env import wait_for_resource_group_deletion


class DeployFromEnvTests(unittest.TestCase):
    def test_resolve_config_uses_root_based_names(self):
        config = resolve_config(
            {
                "RESOURCE_GROUP_NAME": "openclaw-316-RG",
                "ROOT_NAME": "openclaw",
                "TEST_GLOBAL_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
                "TEST_SSH_PUBLIC_KEY": "ssh-ed25519 AAAA test",
            }
        )

        self.assertEqual(config.vm_name, "openclaw")

    def test_build_parameters_includes_optional_values(self):
        config = resolve_config(
            {
                "RESOURCE_GROUP_NAME": "openclaw-316-RG",
                "ROOT_NAME": "openclaw",
                "TEST_GLOBAL_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
                "TEST_SSH_PUBLIC_KEY": "ssh-ed25519 AAAA test",
                "TEST_AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                "TEST_AZURE_OPENAI_DEPLOYMENT": "gpt-5.4",
                "TEST_AZURE_OPENAI_API_KEY": "secret",
                "TEST_FEISHU_APP_ID": "cli_xxx",
                "TEST_FEISHU_APP_SECRET": "feishu-secret",
                "TEST_MSTEAMS_APP_ID": "teams-app-id",
                "TEST_MSTEAMS_APP_PASSWORD": "teams-secret",
            }
        )

        parameters = build_parameters(config)

        self.assertIn("vmName=openclaw", parameters)
        self.assertIn(
            "azureOpenAiEndpoint=https://example.openai.azure.com", parameters
        )
        self.assertIn("feishuAppId=cli_xxx", parameters)
        self.assertIn("msteamsAppId=teams-app-id", parameters)

    def test_make_rg_unique_name_uses_suffix(self):
        self.assertEqual(make_rg_unique_name("openclaw", "pip"), "openclaw-pip")

    def test_resolve_config_requires_grouped_values(self):
        with self.assertRaises(ValueError):
            resolve_config(
                {
                    "RESOURCE_GROUP_NAME": "openclaw-316-RG",
                    "ROOT_NAME": "openclaw",
                    "TEST_GLOBAL_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
                    "TEST_SSH_PUBLIC_KEY": "ssh-ed25519 AAAA test",
                    "TEST_AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com",
                }
            )

    @patch("scripts.deploy_from_env.time.sleep")
    @patch("scripts.deploy_from_env.run_az")
    def test_wait_for_resource_group_deletion_polls_until_missing(
        self, run_az_mock, sleep_mock
    ):
        run_az_mock.side_effect = ["true\n", "true\n", "false\n"]

        wait_for_resource_group_deletion(
            "openclaw-316-RG",
            timeout_seconds=60,
            poll_seconds=1,
        )

        self.assertEqual(run_az_mock.call_count, 3)
        sleep_mock.assert_has_calls([call(1), call(1)])

    @patch("scripts.deploy_from_env.wait_for_resource_group_deletion")
    @patch("scripts.deploy_from_env.run_az")
    def test_reset_resource_group_deletes_existing_group(self, run_az_mock, wait_mock):
        run_az_mock.side_effect = ["true\n", ""]
        config = resolve_config(
            {
                "RESOURCE_GROUP_NAME": "openclaw-316-RG",
                "ROOT_NAME": "openclaw",
                "TEST_GLOBAL_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
                "TEST_SSH_PUBLIC_KEY": "ssh-ed25519 AAAA test",
            }
        )

        reset_resource_group(config)

        self.assertEqual(
            run_az_mock.mock_calls,
            [
                call(
                    [
                        "group",
                        "exists",
                        "--name",
                        "openclaw-316-RG",
                        "--output",
                        "tsv",
                    ]
                ),
                call(
                    [
                        "group",
                        "delete",
                        "--name",
                        "openclaw-316-RG",
                        "--yes",
                        "--no-wait",
                        "--output",
                        "none",
                    ]
                ),
            ],
        )
        wait_mock.assert_called_once_with("openclaw-316-RG")

    @patch("scripts.deploy_from_env.run_az")
    def test_reset_resource_group_skips_delete_when_group_missing(self, run_az_mock):
        run_az_mock.return_value = "false\n"
        config = resolve_config(
            {
                "RESOURCE_GROUP_NAME": "openclaw-316-RG",
                "ROOT_NAME": "openclaw",
                "TEST_GLOBAL_SUBSCRIPTION_ID": "00000000-0000-0000-0000-000000000000",
                "TEST_SSH_PUBLIC_KEY": "ssh-ed25519 AAAA test",
            }
        )

        reset_resource_group(config)

        run_az_mock.assert_called_once_with(
            [
                "group",
                "exists",
                "--name",
                "openclaw-316-RG",
                "--output",
                "tsv",
            ]
        )


if __name__ == "__main__":
    unittest.main()
