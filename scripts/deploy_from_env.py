from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_FILE = REPO_ROOT / "azuredeploy.json"
ENV_FILE = REPO_ROOT / ".env.local"
AZ_EXECUTABLE = shutil.which("az.cmd") or shutil.which("az") or "az"
DEFAULT_CLOUD = "AzureCloud"
DEFAULT_LOCATION_BY_CLOUD = {
    "AzureCloud": "southeastasia",
    "AzureChinaCloud": "chinanorth3",
}
DELETE_WAIT_TIMEOUT_SECONDS = 900
DELETE_WAIT_POLL_SECONDS = 15
SENSITIVE_PARAMETER_KEYS = {
    "azureOpenAiApiKey",
    "feishuAppSecret",
    "msteamsAppPassword",
    "sshPublicKey",
}


@dataclass(frozen=True)
class DeploymentConfig:
    cloud_name: str
    subscription_id: str
    resource_group_name: str
    location: str
    deployment_name: str
    vm_name: str
    admin_username: str
    ssh_public_key: str
    vm_size: str
    data_disk_size_gb: int | None
    hostname: str
    azure_openai_endpoint: str
    azure_openai_deployment: str
    azure_openai_api_key: str
    feishu_app_id: str
    feishu_app_secret: str
    msteams_app_id: str
    msteams_app_password: str


def log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Environment file was not found: {path}")

    env: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = strip_matching_quotes(value.strip())
    return env


def strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def pick_env(env: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = env.get(key, "")
        if value != "":
            return value
    return default


def require_env(env: dict[str, str], *keys: str) -> str:
    value = pick_env(env, *keys)
    if value == "":
        joined = ", ".join(keys)
        raise ValueError(
            f"One of these environment variables is required in .env.local: {joined}"
        )
    return value


def sanitize_name(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9-]", "-", lowered)
    lowered = re.sub(r"-+", "-", lowered).strip("-")
    if not lowered:
        raise ValueError("Resolved resource name is empty after sanitization.")
    return lowered


def make_rg_unique_name(root_name: str, suffix: str, max_length: int = 64) -> str:
    clean_root = sanitize_name(root_name)
    clean_suffix = sanitize_name(suffix)
    reserved = len(clean_suffix) + 1
    if reserved >= max_length:
        raise ValueError(f"Suffix {suffix!r} is too long for max length {max_length}.")
    truncated_root = clean_root[: max_length - reserved].rstrip("-")
    return f"{truncated_root}-{clean_suffix}"


def ensure_grouped_values(label: str, values: dict[str, str]) -> None:
    provided = [key for key, value in values.items() if value != ""]
    if provided and len(provided) != len(values):
        missing = [key for key, value in values.items() if value == ""]
        raise ValueError(
            f"{label} must be provided together. Present: {', '.join(provided)}. Missing: {', '.join(missing)}."
        )


def resolve_subscription_id(env: dict[str, str], cloud_name: str) -> str:
    explicit = pick_env(env, "AZURE_SUBSCRIPTION_ID", "SUBSCRIPTION_ID")
    if explicit:
        return explicit
    if cloud_name == "AzureChinaCloud":
        return require_env(env, "TEST_CHINA_SUBSCRIPTION_ID")
    return require_env(env, "TEST_GLOBAL_SUBSCRIPTION_ID")


def resolve_config(env: dict[str, str]) -> DeploymentConfig:
    cloud_name = pick_env(env, "AZURE_CLOUD_NAME", "AZURE_CLOUD", default=DEFAULT_CLOUD)
    location = pick_env(
        env,
        "AZURE_LOCATION",
        "LOCATION",
        default=DEFAULT_LOCATION_BY_CLOUD.get(
            cloud_name, DEFAULT_LOCATION_BY_CLOUD[DEFAULT_CLOUD]
        ),
    )
    resource_group_name = require_env(env, "RESOURCE_GROUP_NAME")
    root_name = sanitize_name(require_env(env, "ROOT_NAME"))
    subscription_id = resolve_subscription_id(env, cloud_name)
    admin_username = pick_env(env, "ADMIN_USERNAME", default="azureuser")
    vm_size = pick_env(env, "VM_SIZE", default="Standard_B2as_v2")
    data_disk_raw = pick_env(env, "DATA_DISK_SIZE_GB")
    data_disk_size_gb = int(data_disk_raw) if data_disk_raw else None
    hostname = pick_env(env, "HOSTNAME")
    ssh_public_key = require_env(env, "SSH_PUBLIC_KEY", "TEST_SSH_PUBLIC_KEY")
    azure_openai_endpoint = pick_env(
        env, "AZURE_OPENAI_ENDPOINT", "TEST_AZURE_OPENAI_ENDPOINT"
    )
    azure_openai_deployment = pick_env(
        env, "AZURE_OPENAI_DEPLOYMENT", "TEST_AZURE_OPENAI_DEPLOYMENT"
    )
    azure_openai_api_key = pick_env(
        env, "AZURE_OPENAI_API_KEY", "TEST_AZURE_OPENAI_API_KEY"
    )
    feishu_app_id = pick_env(env, "FEISHU_APP_ID", "TEST_FEISHU_APP_ID")
    feishu_app_secret = pick_env(env, "FEISHU_APP_SECRET", "TEST_FEISHU_APP_SECRET")
    msteams_app_id = pick_env(env, "MSTEAMS_APP_ID", "TEST_MSTEAMS_APP_ID")
    msteams_app_password = pick_env(
        env, "MSTEAMS_APP_PASSWORD", "TEST_MSTEAMS_APP_PASSWORD"
    )

    ensure_grouped_values(
        "Azure OpenAI settings",
        {
            "AZURE_OPENAI_ENDPOINT": azure_openai_endpoint,
            "AZURE_OPENAI_DEPLOYMENT": azure_openai_deployment,
            "AZURE_OPENAI_API_KEY": azure_openai_api_key,
        },
    )
    ensure_grouped_values(
        "Feishu settings",
        {
            "FEISHU_APP_ID": feishu_app_id,
            "FEISHU_APP_SECRET": feishu_app_secret,
        },
    )
    ensure_grouped_values(
        "Microsoft Teams settings",
        {
            "MSTEAMS_APP_ID": msteams_app_id,
            "MSTEAMS_APP_PASSWORD": msteams_app_password,
        },
    )

    if cloud_name == "AzureChinaCloud" and msteams_app_id:
        raise ValueError(
            "Microsoft Teams standard mode is not supported in AzureChinaCloud."
        )

    vm_name = root_name

    deployment_name = pick_env(
        env,
        "DEPLOYMENT_NAME",
        default=make_rg_unique_name(root_name, "deploy", max_length=64),
    )

    return DeploymentConfig(
        cloud_name=cloud_name,
        subscription_id=subscription_id,
        resource_group_name=resource_group_name,
        location=location,
        deployment_name=deployment_name,
        vm_name=vm_name,
        admin_username=admin_username,
        ssh_public_key=ssh_public_key,
        vm_size=vm_size,
        data_disk_size_gb=data_disk_size_gb,
        hostname=hostname,
        azure_openai_endpoint=azure_openai_endpoint,
        azure_openai_deployment=azure_openai_deployment,
        azure_openai_api_key=azure_openai_api_key,
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
        msteams_app_id=msteams_app_id,
        msteams_app_password=msteams_app_password,
    )


def build_parameters(config: DeploymentConfig) -> list[str]:
    parameters = [
        f"vmName={config.vm_name}",
        f"adminUsername={config.admin_username}",
        f"sshPublicKey={config.ssh_public_key}",
        f"vmSize={config.vm_size}",
    ]

    if config.data_disk_size_gb is not None:
        parameters.append(f"dataDiskSizeGb={config.data_disk_size_gb}")
    if config.hostname:
        parameters.append(f"hostname={config.hostname}")
    if config.azure_openai_endpoint:
        parameters.extend(
            [
                f"azureOpenAiEndpoint={config.azure_openai_endpoint}",
                f"azureOpenAiDeployment={config.azure_openai_deployment}",
                f"azureOpenAiApiKey={config.azure_openai_api_key}",
            ]
        )
    if config.feishu_app_id:
        parameters.extend(
            [
                f"feishuAppId={config.feishu_app_id}",
                f"feishuAppSecret={config.feishu_app_secret}",
            ]
        )
    if config.msteams_app_id:
        parameters.extend(
            [
                f"msteamsAppId={config.msteams_app_id}",
                f"msteamsAppPassword={config.msteams_app_password}",
            ]
        )
    return parameters


def sanitize_az_args(args: list[str]) -> list[str]:
    sanitized: list[str] = []
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            if key in SENSITIVE_PARAMETER_KEYS and value:
                sanitized.append(f"{key}=***")
                continue
        sanitized.append(arg)
    return sanitized


def run_az(args: list[str]) -> str:
    command = [AZ_EXECUTABLE, *args]
    pretty_command = subprocess.list2cmdline(["az", *sanitize_az_args(args)])
    log(f"Running: {pretty_command}")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Azure CLI command failed: {pretty_command}")
    return result.stdout


def ensure_logged_in() -> None:
    result = subprocess.run(
        [AZ_EXECUTABLE, "account", "show", "--output", "json"],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Azure CLI is not logged in. Run 'az login' first, then re-run this script."
        )


def resource_group_exists(resource_group_name: str) -> bool:
    output = run_az(
        [
            "group",
            "exists",
            "--name",
            resource_group_name,
            "--output",
            "tsv",
        ]
    )
    return output.strip().lower() == "true"


def wait_for_resource_group_deletion(
    resource_group_name: str,
    timeout_seconds: int = DELETE_WAIT_TIMEOUT_SECONDS,
    poll_seconds: int = DELETE_WAIT_POLL_SECONDS,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if not resource_group_exists(resource_group_name):
            log(f"Resource group deletion completed: {resource_group_name}")
            return
        time.sleep(poll_seconds)
    raise RuntimeError(
        f"Timed out waiting for resource group deletion: {resource_group_name}"
    )


def reset_resource_group(config: DeploymentConfig) -> None:
    if not resource_group_exists(config.resource_group_name):
        log(f"Resource group does not exist yet: {config.resource_group_name}")
        return

    log(
        f"Resource group exists and will be deleted first: {config.resource_group_name}"
    )
    run_az(
        [
            "group",
            "delete",
            "--name",
            config.resource_group_name,
            "--yes",
            "--no-wait",
            "--output",
            "none",
        ]
    )
    wait_for_resource_group_deletion(config.resource_group_name)


def print_plan(config: DeploymentConfig) -> None:
    plan = {
        "cloud": config.cloud_name,
        "subscription": config.subscription_id,
        "resourceGroup": config.resource_group_name,
        "location": config.location,
        "deploymentName": config.deployment_name,
        "vmName": config.vm_name,
        "nameModel": "template-derived from vmName",
    }
    log("Resolved deployment plan:")
    print(json.dumps(plan, indent=2, ensure_ascii=True), flush=True)


def deploy(config: DeploymentConfig) -> None:
    print_plan(config)
    ensure_logged_in()
    run_az(["cloud", "set", "--name", config.cloud_name])
    run_az(["account", "set", "--subscription", config.subscription_id])
    reset_resource_group(config)
    run_az(
        [
            "group",
            "create",
            "--name",
            config.resource_group_name,
            "--location",
            config.location,
            "--output",
            "json",
        ]
    )

    deployment_args = [
        "deployment",
        "group",
        "create",
        "--name",
        config.deployment_name,
        "--resource-group",
        config.resource_group_name,
        "--template-file",
        str(TEMPLATE_FILE),
        "--parameters",
        *build_parameters(config),
        "--output",
        "json",
    ]
    run_az(deployment_args)


def main() -> int:
    try:
        env = parse_env_file(ENV_FILE)
        config = resolve_config(env)
        deploy(config)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
