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

HELPER_TEMPLATE_PATHS = {
    "openclaw-browser-url": REPO_ROOT / "openclaw-browser-url.template.sh",
    "openclaw-approve-browser": REPO_ROOT / "openclaw-approve-browser.template.sh",
    "openclaw-approve-teams-pairing": REPO_ROOT
    / "openclaw-approve-teams-pairing.template.sh",
}

HELPER_TEMPLATE_MARKERS = {
    "openclaw-browser-url": "__OPENCLAW_BROWSER_URL_TEMPLATE__",
    "openclaw-approve-browser": "__OPENCLAW_APPROVE_BROWSER_TEMPLATE__",
    "openclaw-approve-teams-pairing": "__OPENCLAW_APPROVE_TEAMS_PAIRING_TEMPLATE__",
}

ARM_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")


def _arm_format_arguments() -> str:
    return (
        ", string(variables('openclawPort')), parameters('azureOpenAiApiKey'), ''"
        ", variables('caddyConfigBase64'), variables('publicControlUrl')"
        ", parameters('adminUsername'), parameters('feishuAppId')"
        ", parameters('feishuAppSecret'), parameters('msteamsAppId')"
        ", parameters('msteamsAppPassword'), variables('msteamsTenantId')"
        ", parameters('azureOpenAiEndpoint'), parameters('azureOpenAiDeployment')"
        ", variables('allowedOriginsJson'))]"
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def read_json(path: Path) -> dict:
    return json.loads(read_text(path))


def validate_template_placeholders(template_text: str) -> None:
    for match in re.finditer(r"\{([^{}]+)\}", template_text):
        if not re.fullmatch(r"\d+", match.group(1)):
            raise ValueError(
                f"Unsupported ARM format placeholder {{{match.group(1)}}} in bootstrap template."
            )


def escape_arm_format_literal(template_text: str) -> str:
    chars: list[str] = []
    index = 0
    while index < len(template_text):
        if match := ARM_PLACEHOLDER_RE.match(template_text, index):
            chars.append(match.group(0))
            index = match.end()
            continue

        char = template_text[index]
        if char == "{":
            chars.append("{{")
        elif char == "}":
            chars.append("}}")
        else:
            chars.append(char)
        index += 1

    return "".join(chars)


def validate_arm_format_literal(format_text: str) -> None:
    index = 0
    while index < len(format_text):
        if match := ARM_PLACEHOLDER_RE.match(format_text, index):
            index = match.end()
            continue

        char = format_text[index]
        if char == "{":
            if index + 1 < len(format_text) and format_text[index + 1] == "{":
                index += 2
                continue
            raise ValueError(
                f"Invalid ARM format literal '{{' at offset {index}; literal braces must be escaped."
            )
        if char == "}":
            if index + 1 < len(format_text) and format_text[index + 1] == "}":
                index += 2
                continue
            raise ValueError(
                f"Invalid ARM format literal '}}' at offset {index}; literal braces must be escaped."
            )
        index += 1


def validate_shell_syntax(template_path: Path) -> None:
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("bash is required to validate bootstrapScript.template.sh")

    subprocess.run([bash, "-n", str(template_path)], check=True)


def validate_shell_text(label: str, content: str) -> None:
    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError(f"bash is required to validate {label}")

    subprocess.run([bash, "-n"], input=content, text=True, check=True)


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


def load_helper_templates() -> dict[str, str]:
    templates: dict[str, str] = {}
    for script_name, path in HELPER_TEMPLATE_PATHS.items():
        template_text = read_text(path)
        validate_shell_text(path.name, template_text)
        templates[script_name] = template_text.rstrip("\n")
    return templates


def render_bootstrap_template(template_text: str) -> str:
    rendered = template_text
    helper_templates = load_helper_templates()
    for script_name, marker in HELPER_TEMPLATE_MARKERS.items():
        if marker not in rendered:
            raise ValueError(
                f"Bootstrap template is missing helper marker {marker} for {script_name}."
            )
        rendered = rendered.replace(marker, helper_templates[script_name])
    return rendered


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


def extract_embedded_script(bootstrap_text: str, script_name: str) -> str:
    marker = f"cat > /usr/local/bin/{script_name} <<'EOF'\n"
    start = bootstrap_text.find(marker)
    if start < 0:
        raise ValueError(f"Could not find embedded script marker for {script_name}.")
    start += len(marker)

    end_marker = f"\nEOF\nchmod 755 /usr/local/bin/{script_name}"
    end = bootstrap_text.find(end_marker, start)
    if end < 0:
        raise ValueError(
            f"Could not find embedded script terminator for {script_name}."
        )

    return bootstrap_text[start:end] + "\n"


def build_bootstrap_expression(template_path: Path) -> tuple[str, str, str]:
    template_text = read_text(template_path)
    rendered_template_text = render_bootstrap_template(template_text)
    validate_shell_text("rendered bootstrap template", rendered_template_text)
    rendered_template_text = strip_generation_preamble(rendered_template_text)
    arm_format_literal = escape_arm_format_literal(rendered_template_text)
    validate_arm_format_literal(arm_format_literal)
    string_literal = render_arm_string_literal(arm_format_literal)
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
    _, string_literal, expression = build_bootstrap_expression(template_path)
    write_text(arm_string_path, string_literal + "\n")
    write_text(arm_expression_path, expression + "\n")
    sync_azuredeploy_bootstrap(azuredeploy_path, expression)


def write_arm_string(template_path: Path, output_path: Path) -> None:
    _, string_literal, _ = build_bootstrap_expression(template_path)
    write_text(output_path, string_literal + "\n")


def write_arm_expression(template_path: Path, output_path: Path) -> None:
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
