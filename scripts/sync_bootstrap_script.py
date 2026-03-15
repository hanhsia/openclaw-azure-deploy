from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PATH = REPO_ROOT / "bootstrapScript.template.sh"
DEFAULT_ARM_STRING_PATH = REPO_ROOT / "generated" / "bootstrapScript.arm-string.txt"
DEFAULT_ARM_EXPRESSION_PATH = (
    REPO_ROOT / "generated" / "bootstrapScript.arm-expression.txt"
)
DEFAULT_AZUREDEPLOY_PATH = REPO_ROOT / "azuredeploy.json"


def _arm_format_arguments() -> str:
    return (
        ", string(variables('openclawPort')), parameters('azureOpenAiApiKey'),"
        " variables('openclawConfigBase64'), variables('caddyConfigBase64'),"
        " variables('publicControlUrl'), parameters('adminUsername'),"
        " parameters('feishuAppId'), parameters('feishuAppSecret'),"
        " parameters('msteamsAppId'), parameters('msteamsAppPassword'),"
        " variables('msteamsTenantId'))]"
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def validate_template_placeholders(template_text: str) -> None:
    for match in re.finditer(r"\{([^{}]+)\}", template_text):
        if not re.fullmatch(r"\d+", match.group(1)):
            raise ValueError(
                f"Unsupported ARM format placeholder {{{match.group(1)}}} in bootstrap template."
            )


def validate_shell_syntax(template_path: Path) -> None:
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("bash is required to validate bootstrapScript.template.sh")

    subprocess.run([bash, "-n", str(template_path)], check=True)


def strip_generation_preamble(template_text: str) -> str:
    shebang_index = template_text.find("#!/usr/bin/env bash\n")
    if shebang_index < 0:
        raise ValueError(
            "bootstrapScript.template.sh must contain a '#!/usr/bin/env bash' shebang."
        )
    return template_text[shebang_index:]


def render_arm_string_literal(template_text: str) -> str:
    return "'" + template_text.replace("'", "''") + "'"


def render_arm_format_expression(string_literal: str) -> str:
    return f"[format({string_literal}{_arm_format_arguments()}"


def build_bootstrap_expression(template_path: Path) -> tuple[str, str, str]:
    template_text = read_text(template_path)
    validate_template_placeholders(template_text)
    rendered_template_text = strip_generation_preamble(template_text)
    string_literal = render_arm_string_literal(rendered_template_text)
    expression = render_arm_format_expression(string_literal)
    return rendered_template_text, string_literal, expression


def sync_azuredeploy_bootstrap(azuredeploy_path: Path, expression: str) -> None:
    payload = json.loads(read_text(azuredeploy_path))
    payload["variables"]["bootstrapScript"] = expression
    write_text(
        azuredeploy_path, json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    )


def run_sync(
    template_path: Path,
    arm_string_path: Path,
    arm_expression_path: Path,
    azuredeploy_path: Path,
) -> None:
    validate_shell_syntax(template_path)
    _, string_literal, expression = build_bootstrap_expression(template_path)
    write_text(arm_string_path, string_literal + "\n")
    write_text(arm_expression_path, expression + "\n")
    sync_azuredeploy_bootstrap(azuredeploy_path, expression)


def write_arm_string(template_path: Path, output_path: Path) -> None:
    validate_shell_syntax(template_path)
    _, string_literal, _ = build_bootstrap_expression(template_path)
    write_text(output_path, string_literal + "\n")


def write_arm_expression(template_path: Path, output_path: Path) -> None:
    validate_shell_syntax(template_path)
    _, _, expression = build_bootstrap_expression(template_path)
    write_text(output_path, expression + "\n")


def add_template_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--template",
        type=Path,
        default=DEFAULT_TEMPLATE_PATH,
        help="Path to bootstrapScript.template.sh",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate ARM bootstrap artifacts from bootstrapScript.template.sh"
    )
    add_template_argument(parser)
    parser.add_argument(
        "--arm-string-output",
        type=Path,
        default=DEFAULT_ARM_STRING_PATH,
        help="Output path for the single-quoted ARM string literal",
    )
    parser.add_argument(
        "--arm-expression-output",
        type=Path,
        default=DEFAULT_ARM_EXPRESSION_PATH,
        help="Output path for the full [format(...)] ARM expression",
    )
    parser.add_argument(
        "--azuredeploy",
        type=Path,
        default=DEFAULT_AZUREDEPLOY_PATH,
        help="Path to azuredeploy.json to update",
    )
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser(
        "sync",
        help="Generate both bootstrap artifacts and sync azuredeploy.json",
    )
    add_template_argument(sync_parser)
    sync_parser.add_argument(
        "--arm-string-output",
        type=Path,
        default=DEFAULT_ARM_STRING_PATH,
        help="Output path for the single-quoted ARM string literal",
    )
    sync_parser.add_argument(
        "--arm-expression-output",
        type=Path,
        default=DEFAULT_ARM_EXPRESSION_PATH,
        help="Output path for the full [format(...)] ARM expression",
    )
    sync_parser.add_argument(
        "--azuredeploy",
        type=Path,
        default=DEFAULT_AZUREDEPLOY_PATH,
        help="Path to azuredeploy.json to update",
    )

    arm_string_parser = subparsers.add_parser(
        "arm-string",
        help="Render the single-quoted ARM string literal only",
    )
    add_template_argument(arm_string_parser)
    arm_string_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARM_STRING_PATH,
        help="Output path for the single-quoted ARM string literal",
    )

    arm_expression_parser = subparsers.add_parser(
        "arm-expression",
        help="Render the full [format(...)] ARM expression only",
    )
    add_template_argument(arm_expression_parser)
    arm_expression_parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_ARM_EXPRESSION_PATH,
        help="Output path for the full [format(...)] ARM expression",
    )

    args = parser.parse_args()

    if args.command in (None, "sync"):
        run_sync(
            template_path=args.template,
            arm_string_path=args.arm_string_output,
            arm_expression_path=args.arm_expression_output,
            azuredeploy_path=args.azuredeploy,
        )
        return

    if args.command == "arm-string":
        write_arm_string(template_path=args.template, output_path=args.output)
        return

    if args.command == "arm-expression":
        write_arm_expression(template_path=args.template, output_path=args.output)
        return

    parser.error(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
