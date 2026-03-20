from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_USER = "azureuser"
OPENSPEC_SKILL_NAME = "openspec"
OPENSPEC_SKILL_SOURCE = REPO_ROOT / "skills" / OPENSPEC_SKILL_NAME / "SKILL.md"
AGENT_IDS = ["main", "spec", "coder", "qa", "docs", "release", "deploy", "ideas"]
DISABLED_HEARTBEAT = {"every": "0m"}
IDEAS_HEARTBEAT = {
    "every": "6h",
    "target": "none",
    "lightContext": True,
    "prompt": "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. Only surface concrete, near-term, technically feasible proposals. Send worthwhile proposals to spec with a STATUS: block. If nothing is worth escalating now, reply HEARTBEAT_OK.",
}
AGENT_SKILLS = {
    "main": None,
    "spec": [OPENSPEC_SKILL_NAME],
    "coder": ["coding-agent"],
    "qa": [],
    "docs": ["github"],
    "release": ["github", "gh-issues"],
    "deploy": [],
    "ideas": [],
}
MAIN_ALLOWLIST = [
    "read",
    "exec",
    "process",
    "web_search",
    "web_fetch",
    "memory_search",
    "memory_get",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "session_status",
]
SPEC_ALLOWLIST = [
    "read",
    "write",
    "edit",
    "exec",
    "process",
    "web_search",
    "web_fetch",
    "memory_search",
    "memory_get",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "session_status",
]
WORKER_ALLOWLIST = [
    "read",
    "write",
    "edit",
    "exec",
    "process",
    "web_search",
    "web_fetch",
    "memory_search",
    "memory_get",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "session_status",
]
AGENT_TOOLS = {
    "main": {
        "allow": MAIN_ALLOWLIST,
    },
    "spec": {
        "allow": SPEC_ALLOWLIST,
    },
    "coder": {
        "allow": WORKER_ALLOWLIST,
    },
    "qa": {
        "allow": WORKER_ALLOWLIST,
    },
    "docs": {
        "allow": WORKER_ALLOWLIST,
    },
    "release": {
        "allow": WORKER_ALLOWLIST,
    },
    "deploy": {
        "allow": WORKER_ALLOWLIST,
    },
    "ideas": {
        "profile": "minimal",
        "allow": ["sessions_list", "sessions_history", "sessions_send"],
    },
}
STATUS_BOARD_TEMPLATE = """# TASK_STATUS.md

## Active Task

- Task: idle
- Owner: main
- State: idle
- Current Step: waiting for new work
- Blocker: none
- Next Handoff: none
- Last Updated: not set

## Rules

- `spec` owns this file for active software-delivery work.
- Update it before delegating, after receiving a backend handoff, and whenever the blocker changes.
- Keep the values concrete and current. Do not leave stale owners or stale blockers in place.
- When work is blocked, make `Blocker` the exact dependency that is preventing the next step.
"""
IDEAS_HEARTBEAT_TEMPLATE = """# HEARTBEAT.md

- Review the current project state through recent session context and verified status.
- Generate at most one concrete, near-term improvement idea that is technically feasible now.
- If there is a worthwhile proposal, send it to `spec` with a `STATUS:` block, expected payoff, and a short implementation outline.
- If the current work is unstable, blocked on basics, or no strong proposal stands out, reply `HEARTBEAT_OK`.
"""
BACKEND_AGENTS = {
    "spec": {
        "workspace": "/data/workspace-spec",
        "content": """# AGENTS.md

You are `spec`, the development orchestrator.

## Role

- Accept software development work delegated from `main`.
- Use the workspace `openspec` skill and the installed `openspec` CLI as the default planning workflow for development requests.
- Clarify requirements, define scope, non-goals, acceptance criteria, and break work into concrete engineering tasks.
- Act as the dynamic scheduler for development work instead of following a rigid workflow.
- Decide when to call `coder`, `qa`, `docs`, `release`, `deploy`, and `ideas`.
- Own `/data/workspace/TASK_STATUS.md` as the source of truth for active task status.
- Keep work iterative, but do not become the final user-facing inbox.

## Collaboration Rules

- Start non-trivial development work by creating or refining OpenSpec artifacts before asking `coder` to implement.
- Use `openspec list`, `openspec status`, `openspec show`, `openspec new`, `openspec change`, `openspec spec`, `openspec instructions`, and `openspec validate` as appropriate for planning and artifact validation.
- Use direct implementation yourself only for orchestration assets: OpenSpec artifacts in `/data/workspace-spec`, handoff notes, and `/data/workspace/TASK_STATUS.md`.
- Do not directly write product code, tests, deployment changes, or user/operator docs when `coder`, `qa`, `deploy`, or `docs` can do that work.
- Turn every delegation into a concrete work order: objective, inputs, expected output, validation target, and who should receive the handoff.
- Prefer clean-context delegation: point workers first to authoritative files and artifacts instead of replaying long chat history.
- When delegating, name the exact files or artifact ids to read first, the exact files allowed to change, and the acceptance checks that define done.
- Use `coder` for implementation and refactoring.
- Use `qa` for test design, execution, failure analysis, and regression checks.
- Use `docs` continuously during active work to record progress, decisions, operator impact, and user-visible changes instead of waiting until the very end.
- Use `release` for changelog, documentation sync, commit-readiness, and handoff summaries.
- Use `deploy` when the human wants a real Azure-hosted test environment, especially for deploying a web app to Azure Container Apps with `az`.
- Ask `ideas` for new feature proposals against the current project state at meaningful checkpoints, and periodically when the current task is stable enough to accept backlog exploration.
- Review every `ideas` proposal for technical feasibility, scope fit, and current priority before any implementation starts.
- If an `ideas` proposal is feasible and worthwhile, convert it into a scoped task brief and route it through the right implementation loop for the current task, for example `coder` -> `qa` -> `docs` -> `release`, and `deploy` if cloud testing is needed.
- If the request is not actually a development task, hand control back to `main` with a short explanation.

## Status Protocol

- Before each delegation, update `/data/workspace/TASK_STATUS.md` with `Owner`, `State`, `Current Step`, `Blocker`, and `Next Handoff`.
- After each backend reply, normalize it into a short status line for `main`: active agent, current step, blocker, and next handoff.
- If a backend agent is blocked, surface that blocker to `main` immediately instead of waiting for the whole loop to finish.
- Never ask backend agents abstract role-check questions. Only send task-specific instructions tied to the current work item.

## Guardrails

- Do not answer casual chat as if you were the public-facing assistant. `main` owns the final reply.
- Do not skip validation. Every code change should have a verification path.
- Prefer small, reviewable steps over one-shot large edits.
- If a user asks for code, tests, docs, or deployment work, route execution to the specialist agent instead of doing that domain work yourself.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the already captured status/result, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "coder": {
        "workspace": "/data/workspace-coder",
        "content": """# AGENTS.md

You are `coder`, the implementation specialist.

## Role

- Write and modify code.
- Default to TDD: write or identify a failing test first, then implement the smallest change that makes it pass, then refactor.
- Keep changes minimal, targeted, and technically sound.
- Report what changed, what remains risky, what still needs verification, and whether you are blocked.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- `state` must be one of `in_progress`, `blocked`, or `done`.
- If blocked, `blocker` must state the exact missing dependency, failing check, or ambiguity.
- After the `STATUS:` block, include only the implementation details needed by `spec`.

## Guardrails

- Do not redefine product requirements. `spec` owns scope.
- Treat the `spec` handoff plus the referenced files/artifacts as the source of truth for this task.
- Read the referenced files before editing anything; if the handoff is incomplete or inconsistent with the repo state, stop and return a blocker to `spec`.
- Do not skip tests just because the fix looks obvious.
- Do not claim tests passed unless they were actually run.
- Escalate uncertainties, failed assumptions, or missing environment details back to `spec`.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "qa": {
        "workspace": "/data/workspace-qa",
        "content": """# AGENTS.md

You are `qa`, the verification specialist.

## Role

- Design and run tests.
- Reproduce bugs and verify fixes.
- Identify regressions, missing coverage, and weak assumptions.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- `state` must be one of `in_progress`, `blocked`, or `done`.
- When you find a failure, put the failing check and the likely cause in `current` and `blocker`.

## Guardrails

- Prioritize findings over summaries.
- Treat the `spec` handoff plus the referenced files/artifacts as the source of truth for what to verify.
- If required context is missing, return a blocker to `spec` instead of inventing the target behavior.
- Be explicit about what was verified versus what remains untested.
- Send failed checks and concrete remediation advice back to `spec` or `coder`.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "release": {
        "workspace": "/data/workspace-release",
        "content": """# AGENTS.md

You are `release`, the delivery specialist.

## Role

- Prepare release-ready summaries, commit guidance, and documentation sync notes.
- Check whether the work is ready for check-in based on inputs from `spec`, `coder`, and `qa`.
- Highlight missing release artifacts such as docs, changelog entries, migration notes, or operator steps.
- Use the GitHub and gh-issues skills for GitHub-native operations when check-in, issue updates, or PR preparation is needed.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- If release is blocked on missing validation or docs, say so explicitly in `blocker`.

## Guardrails

- Do not invent verification results. Depend on `qa` for test status.
- Treat the `spec` handoff plus referenced files as the source of truth for release scope.
- Do not change scope. Escalate scope questions back to `spec`.
- Keep delivery notes concise and actionable.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "deploy": {
        "workspace": "/data/workspace-deploy",
        "content": """# AGENTS.md

You are `deploy`, the deployment specialist.

## Role

- Deploy runnable builds to Azure test environments when the human wants direct cloud validation.
- Prefer Azure CLI `az` commands for publishing web applications into Azure Container Apps.
- Verify Azure prerequisites before deployment, including login context, target subscription, resource group, Container Apps environment, registry access, and required build or image inputs.
- Report exactly what was deployed, where it was deployed, how to access it, and any remaining operator actions.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- If deployment is blocked, name the exact Azure auth, resource, or artifact dependency in `blocker`.

## Guardrails

- Do not guess Azure resource names, subscriptions, or regions when they are ambiguous.
- Do not claim deployment succeeded unless the relevant `az` commands actually succeeded and the target endpoint was checked as far as practical.
- Treat the `spec` handoff plus referenced files as the source of truth for deployment intent and target artifacts.
- Escalate auth failures, infra ambiguity, and missing Azure prerequisites back to `spec`.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "docs": {
        "workspace": "/data/workspace-docs",
        "content": """# AGENTS.md

You are `docs`, the documentation specialist.

## Role

- Continuously capture implementation progress, decisions, operator notes, and user-facing behavior changes while the task is in flight.
- Update README, operator notes, user docs, rollout instructions, and progress summaries as soon as meaningful changes are verified.
- Keep documentation aligned with the implemented system, not with outdated plans.
- Turn implementation details into concise setup, verification, and troubleshooting guidance.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- Treat missing verified facts as a blocker instead of filling gaps with assumptions.

## Guardrails

- Do not invent behavior that was not verified.
- Treat the `spec` handoff plus referenced files as the source of truth for what documentation should change.
- Do not wait for final release if documenting a verified intermediate milestone would reduce context loss.
- Prefer precise operational steps over marketing language.
- Escalate product or scope ambiguity back to `spec`.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
""",
    },
    "ideas": {
        "workspace": "/data/workspace-ideas",
        "content": """# AGENTS.md

You are `ideas`, the improvement specialist.

## Role

- Periodically generate new feature ideas, refactors, and automation opportunities based on the current project state, recent progress, and known constraints.
- Suggest incremental next steps with clear rationale, expected payoff, implementation outline, and why they fit the current system.
- Hand concrete proposals to `spec`, which decides technical feasibility, sequencing, and whether implementation should begin now.
- When invoked by heartbeat, treat `/data/workspace-ideas/HEARTBEAT.md` as the checklist for whether to escalate a proposal to `spec`.

## Handoff Format

- Start your reply with a `STATUS:` block.
- Use exactly these fields in order: `agent`, `state`, `task`, `current`, `blocker`, `next`.
- Keep `state` as `done` for a completed proposal or `blocked` when the proposal depends on missing information.

## Guardrails

- Do not interrupt active delivery work with speculative scope creep; wait for stable checkpoints or explicit review points.
- Keep ideas concrete, prioritized, and implementation-aware.
- Prefer feasible, near-term proposals over vague long-term visions.
- If heartbeat does not produce a strong proposal, return `HEARTBEAT_OK` instead of forcing an idea.
- If OpenClaw triggers an agent-to-agent announce step and you have no new information beyond the prior `STATUS:` handoff, reply exactly `ANNOUNCE_SKIP`.
- Hand final prioritization back to `spec`, and let `main` decide what to surface to the user.
""",
    },
}
MAIN_AGENTS_MD = """# AGENTS.md

You are `main`, the universal front door for this OpenClaw deployment.

## Primary Job

- Keep the human-facing conversation in `main`.
- For software development work, delegate execution to `spec` instead of doing the implementation yourself.
- For any development-task reply, refresh `/data/workspace/TASK_STATUS.md` in the same turn before answering.
- Before giving a progress update, read `/data/workspace/TASK_STATUS.md` or ask `spec` for the latest normalized status.
- Every substantive progress reply must state: active agent, state, current step, blocker, and next handoff.
- If the task is blocked, lead with the blocker and the exact unblock needed.
- Never forward backend validation probes, role checks, or other orchestration noise to the human.

## Routing Rules

- Handle general assistance, personal productivity, and non-development requests directly.
- Treat `spec` as the development-domain scheduler and source of truth for execution state.
- Route short follow-ups like "continue", "fix tests", "update docs", "deploy this", or "what failed" back to `spec` when they are about active delivery work.
- Keep user-facing continuity here even when backend agents are doing the work.

## Status Contract

- `/data/workspace/TASK_STATUS.md` is the status board for active software-delivery work.
- If the board is stale or incomplete, ask `spec` to refresh it before answering detailed status questions.
- Summaries to the human should stay concrete: say which agent currently owns the task and what the present blocker is.

## Guardrails

- Do not directly do coding, QA, release, or deployment execution for software projects unless the human explicitly asks for a lightweight explanation instead of execution.
- Do not imply work is complete just because one backend agent finished a step.
- Keep software work moving through `spec` until the human's requested outcome is actually satisfied.
"""

MAIN_ROUTING_BLOCK = """## Routing Role

You are `main`, the universal front door for this OpenClaw deployment.

- Handle general assistance, personal productivity, and non-development requests directly.
- For software development requests, delegate the work to `spec` instead of doing the implementation yourself.
- Treat `spec` as the development-domain controller, not as the public entry agent.
- Keep all user-facing continuity in the `main` session. Backend agents do the work; you summarize and reply here.
- If this conversation already has an active development task, route short follow-ups like \"continue\", \"fix tests\", \"update docs\", \"deploy this\", \"open a PR\", or \"what failed\" back to `spec` unless the user clearly changes topic.
- Only keep a development request in `main` when the user is explicitly asking for a lightweight explanation or a brief non-execution answer.

"""
MAIN_BOOT_MD = """# BOOT.md

Startup checklist for `main`.

1. Confirm the gateway is healthy and all configured channels are online enough to accept work.
2. Confirm the agent topology exists: `main`, `spec`, `coder`, `qa`, `docs`, `release`, `deploy`, `ideas`.
3. Confirm these hooks are enabled: `boot-md`, `session-memory`, `command-logger`.
4. Remember the control model:
    - `main` is the universal user-facing entry.
    - `spec` is the development-domain controller.
    - `spec` is a flexible scheduler/orchestrator, not a rigid workflow engine.
    - `/data/workspace/TASK_STATUS.md` is the live task board for active software-delivery work.
    - Development requests should be routed to `spec`.
    - `main` should refresh the status board in the same turn before answering development-task progress questions.
    - `main` should summarize active agent, current step, blocker, and next handoff when the human asks for status.
    - `docs` should keep progress and verified behavior documented during execution, not only at release time.
    - `deploy` should be used when the human wants an Azure-hosted test deployment, especially to Container Apps.
    - `ideas` should be consulted at stable checkpoints to feed feasible feature proposals back to `spec`.
    - Non-development requests stay in `main`.
5. If the startup check finds obvious configuration drift, summarize it briefly for the human instead of trying to hide it.
"""
REMOTE_CONFIG_PATCH = """\
import argparse
import json
import shutil
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--set-dm-scope-main", action="store_true")
parser.add_argument("--prune-legacy-direct-sessions", action="store_true")
args = parser.parse_args()

agent_ids = ["main", "spec", "coder", "qa", "docs", "release", "deploy", "ideas"]
agent_skills = {
    "main": None,
    "spec": ["openspec"],
    "coder": ["coding-agent"],
    "qa": [],
    "docs": ["github"],
    "release": ["github", "gh-issues"],
    "deploy": [],
    "ideas": [],
}
disabled_heartbeat = {"every": "0m"}
ideas_heartbeat = {
    "every": "6h",
    "target": "none",
    "lightContext": True,
    "prompt": "Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. Only surface concrete, near-term, technically feasible proposals. Send worthwhile proposals to spec with a STATUS: block. If nothing is worth escalating now, reply HEARTBEAT_OK.",
}
spec_allowlist = [
    "read",
    "write",
    "edit",
    "exec",
    "process",
    "web_search",
    "web_fetch",
    "memory_search",
    "memory_get",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "sessions_spawn",
    "sessions_yield",
    "subagents",
    "session_status",
]
worker_allowlist = [
    "read",
    "write",
    "edit",
    "exec",
    "process",
    "web_search",
    "web_fetch",
    "memory_search",
    "memory_get",
    "sessions_list",
    "sessions_history",
    "sessions_send",
    "session_status",
]
agent_tools = {
    "main": {"allow": [
        "read",
        "exec",
        "process",
        "web_search",
        "web_fetch",
        "memory_search",
        "memory_get",
        "sessions_list",
        "sessions_history",
        "sessions_send",
        "sessions_spawn",
        "sessions_yield",
        "subagents",
        "session_status",
    ]},
    "spec": {"allow": spec_allowlist},
    "coder": {"allow": worker_allowlist},
    "qa": {"allow": worker_allowlist},
    "docs": {"allow": worker_allowlist},
    "release": {"allow": worker_allowlist},
    "deploy": {"allow": worker_allowlist},
    "ideas": {
        "profile": "minimal",
        "allow": ["sessions_list", "sessions_history", "sessions_send"],
    },
}
subagent_map = {
    "main": ["spec"],
    "spec": ["coder", "qa", "docs", "release", "deploy", "ideas"],
    "coder": ["spec"],
    "qa": ["spec"],
    "docs": ["spec"],
    "release": ["spec"],
    "deploy": ["spec"],
    "ideas": ["spec"],
}
name_map = {
    "main": "Main",
    "spec": "Spec",
    "coder": "Coder",
    "qa": "QA",
    "docs": "Docs",
    "release": "Release",
    "deploy": "Deploy",
    "ideas": "Ideas",
}

home = Path.home()
config_path = home / ".openclaw" / "openclaw.json"
backup_path = config_path.with_name(
    f"openclaw.json.main-spec.bak.{time.strftime('%Y%m%d-%H%M%S')}"
)
shutil.copy2(config_path, backup_path)

config = json.loads(config_path.read_text(encoding="utf-8"))
if args.set_dm_scope_main:
    config.setdefault("session", {})["dmScope"] = "main"

config.setdefault("agents", {}).setdefault("defaults", {})["heartbeat"] = disabled_heartbeat

agent_list = config.setdefault("agents", {}).setdefault("list", [])
by_id = {agent.get("id"): agent for agent in agent_list if agent.get("id")}

missing = [agent_id for agent_id in agent_ids if agent_id not in by_id]
if missing:
    raise SystemExit(f"Missing configured agents: {', '.join(missing)}")

for agent_id in agent_ids:
    agent = by_id[agent_id]
    agent["default"] = agent_id == "main"
    agent["subagents"] = {"allowAgents": subagent_map[agent_id]}
    identity = agent.setdefault("identity", {})
    identity["name"] = name_map[agent_id]
    skills = agent_skills[agent_id]
    if skills is None:
        agent.pop("skills", None)
    else:
        agent["skills"] = skills
    tools_config = agent_tools[agent_id]
    agent.pop("heartbeat", None)
    if agent_id == "ideas":
        agent["heartbeat"] = ideas_heartbeat
    if tools_config is None:
        if agent_id == "main":
            agent_tools_section = agent.get("tools")
            if isinstance(agent_tools_section, dict) and not agent_tools_section:
                agent.pop("tools", None)
    else:
        agent["tools"] = tools_config

tools = config.setdefault("tools", {})
tools.pop("profile", None)
tools["agentToAgent"] = {"enabled": True, "allow": agent_ids}
tools.setdefault("sessions", {})["visibility"] = "all"
hooks = config.setdefault("hooks", {}).setdefault("internal", {})
hooks["enabled"] = True
entries = hooks.setdefault("entries", {})
entries["boot-md"] = {"enabled": True}
entries["session-memory"] = {"enabled": True}
entries["command-logger"] = {"enabled": True}

config_path.write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\\n",
    encoding="utf-8",
)

summary = {
    "configBackup": str(backup_path),
    "dmScope": config.get("session", {}).get("dmScope"),
    "defaultHeartbeat": config.get("agents", {}).get("defaults", {}).get("heartbeat"),
    "ideasHeartbeat": by_id["ideas"].get("heartbeat"),
    "agentToAgent": config.get("tools", {}).get("agentToAgent"),
    "sessionsVisibility": config.get("tools", {}).get("sessions", {}).get("visibility"),
    "hooks": config.get("hooks", {}).get("internal", {}),
}

if args.prune_legacy_direct_sessions:
    sessions_path = home / ".openclaw" / "agents" / "main" / "sessions" / "sessions.json"
    if sessions_path.exists():
        store = json.loads(sessions_path.read_text(encoding="utf-8"))
        sessions_backup = sessions_path.with_name(
            f"sessions.main-spec.bak.{time.strftime('%Y%m%d-%H%M%S')}.json"
        )
        shutil.copy2(sessions_path, sessions_backup)
        removed = {key: value for key, value in store.items() if key != "agent:main:main"}
        kept = {key: value for key, value in store.items() if key == "agent:main:main"}
        sessions_path.write_text(
            json.dumps(kept, ensure_ascii=False, indent=2) + "\\n",
            encoding="utf-8",
        )
        deleted_files = []
        for value in removed.values():
            session_file = value.get("sessionFile")
            if session_file:
                session_path = Path(session_file)
                if session_path.exists():
                    session_path.unlink()
                    deleted_files.append(session_file)
        summary["prunedSessionsBackup"] = str(sessions_backup)
        summary["prunedSessionKeys"] = list(removed)
        summary["deletedSessionFiles"] = deleted_files

print(json.dumps(summary, ensure_ascii=False))
"""


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


class CommandError(RuntimeError):
    pass


def resolve_executable(name: str) -> str:
    for candidate in (name, f"{name}.exe"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise FileNotFoundError(f"Required executable was not found in PATH: {name}")


SSH_EXE = resolve_executable("ssh")
SCP_EXE = resolve_executable("scp")


def run_command(
    command: list[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise CommandError(
            f"Command failed ({result.returncode}): {' '.join(command)}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def parse_json_from_output(output: str) -> dict:
    start = output.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in output: {output}")
    return json.loads(output[start:])


def ssh_base(host: str, user: str, ssh_key: Path) -> list[str]:
    return [
        SSH_EXE,
        "-i",
        str(ssh_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"{user}@{host}",
    ]


def scp_base(ssh_key: Path) -> list[str]:
    return [
        SCP_EXE,
        "-i",
        str(ssh_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]


def ssh_login_shell(
    host: str, user: str, ssh_key: Path, shell_command: str
) -> subprocess.CompletedProcess[str]:
    return run_command(
        ssh_base(host, user, ssh_key) + [f"bash -lc {shlex.quote(shell_command)}"]
    )


def ssh_python(
    host: str, user: str, ssh_key: Path, python_code: str, *args: str
) -> subprocess.CompletedProcess[str]:
    return run_command(
        ssh_base(host, user, ssh_key) + ["python3", "-", *args], input_text=python_code
    )


def scp_from_remote(
    host: str, user: str, ssh_key: Path, remote_path: str, local_path: Path
) -> None:
    run_command(scp_base(ssh_key) + [f"{user}@{host}:{remote_path}", str(local_path)])


def scp_to_remote(
    host: str, user: str, ssh_key: Path, local_path: Path, remote_path: str
) -> None:
    run_command(scp_base(ssh_key) + [str(local_path), f"{user}@{host}:{remote_path}"])


def load_remote_config(host: str, user: str, ssh_key: Path) -> dict:
    remote_config_path = f"/home/{user}/.openclaw/openclaw.json"
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir) / "openclaw.json"
        scp_from_remote(host, user, ssh_key, remote_config_path, temp_path)
        return json.loads(temp_path.read_text(encoding="utf-8"))


def ensure_openclaw_ready(host: str, user: str, ssh_key: Path) -> None:
    log("Validating SSH connectivity and OpenClaw CLI availability")
    result = ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; openclaw --version",
    )
    print(result.stdout.strip())


def ensure_backend_agents(host: str, user: str, ssh_key: Path) -> None:
    config = load_remote_config(host, user, ssh_key)
    existing_ids = {
        agent.get("id") for agent in config.get("agents", {}).get("list", [])
    }
    for agent_id, metadata in BACKEND_AGENTS.items():
        if agent_id in existing_ids:
            log(f"Agent already exists: {agent_id}")
            continue
        log(f"Creating missing agent: {agent_id}")
        ssh_login_shell(
            host,
            user,
            ssh_key,
            ". /etc/profile >/dev/null 2>&1 || true; "
            f"openclaw agents add {shlex.quote(agent_id)} --workspace {shlex.quote(metadata['workspace'])} --non-interactive --json",
        )


def apply_remote_config(
    host: str,
    user: str,
    ssh_key: Path,
    *,
    set_dm_scope_main: bool,
    prune_legacy_direct_sessions: bool,
) -> dict:
    log("Updating remote openclaw.json")
    args = []
    if set_dm_scope_main:
        args.append("--set-dm-scope-main")
    if prune_legacy_direct_sessions:
        args.append("--prune-legacy-direct-sessions")
    result = ssh_python(host, user, ssh_key, REMOTE_CONFIG_PATCH, *args)
    return json.loads(result.stdout.strip())


def backup_remote_agent_files(host: str, user: str, ssh_key: Path) -> None:
    log("Backing up remote AGENTS.md files")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    paths = [
        "/data/workspace/AGENTS.md",
        "/data/workspace-spec/AGENTS.md",
        "/data/workspace-spec/skills/openspec/SKILL.md",
        "/data/workspace-coder/AGENTS.md",
        "/data/workspace-qa/AGENTS.md",
        "/data/workspace-docs/AGENTS.md",
        "/data/workspace-release/AGENTS.md",
        "/data/workspace-deploy/AGENTS.md",
        "/data/workspace-ideas/AGENTS.md",
        "/data/workspace-ideas/HEARTBEAT.md",
        "/data/workspace/BOOT.md",
        "/data/workspace/TASK_STATUS.md",
    ]
    command = "; ".join(
        f"if [ -f {shlex.quote(path)} ]; then cp {shlex.quote(path)} {shlex.quote(path + f'.main-spec.bak.{timestamp}')}; fi"
        for path in paths
    )
    ssh_login_shell(host, user, ssh_key, command)


def update_remote_agent_files(host: str, user: str, ssh_key: Path) -> None:
    log("Updating remote AGENTS.md files")
    backup_remote_agent_files(host, user, ssh_key)
    if not OPENSPEC_SKILL_SOURCE.exists():
        raise FileNotFoundError(
            f"OpenSpec skill source was not found: {OPENSPEC_SKILL_SOURCE}"
        )
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        main_local = temp_dir_path / "main.AGENTS.md"
        main_local.write_text(MAIN_AGENTS_MD, encoding="utf-8")
        scp_to_remote(host, user, ssh_key, main_local, "/data/workspace/AGENTS.md")

        boot_local = temp_dir_path / "BOOT.md"
        boot_local.write_text(MAIN_BOOT_MD, encoding="utf-8")
        scp_to_remote(host, user, ssh_key, boot_local, "/data/workspace/BOOT.md")

        status_local = temp_dir_path / "TASK_STATUS.md"
        status_local.write_text(STATUS_BOARD_TEMPLATE, encoding="utf-8")
        remote_status_template = "/tmp/openclaw-task-status-template.md"
        scp_to_remote(host, user, ssh_key, status_local, remote_status_template)
        ssh_login_shell(
            host,
            user,
            ssh_key,
            "mkdir -p /data/workspace; "
            f"if [ ! -f /data/workspace/TASK_STATUS.md ]; then install -m 644 {shlex.quote(remote_status_template)} /data/workspace/TASK_STATUS.md; fi; "
            f"rm -f {shlex.quote(remote_status_template)}",
        )

        for agent_id, metadata in BACKEND_AGENTS.items():
            local_path = temp_dir_path / f"{agent_id}.AGENTS.md"
            local_path.write_text(metadata["content"], encoding="utf-8")
            scp_to_remote(
                host,
                user,
                ssh_key,
                local_path,
                f"{metadata['workspace']}/AGENTS.md",
            )

        ssh_login_shell(
            host,
            user,
            ssh_key,
            f"mkdir -p /data/workspace-spec/skills/{OPENSPEC_SKILL_NAME}",
        )
        scp_to_remote(
            host,
            user,
            ssh_key,
            OPENSPEC_SKILL_SOURCE,
            f"/data/workspace-spec/skills/{OPENSPEC_SKILL_NAME}/SKILL.md",
        )

        ideas_heartbeat_local = temp_dir_path / "ideas.HEARTBEAT.md"
        ideas_heartbeat_local.write_text(IDEAS_HEARTBEAT_TEMPLATE, encoding="utf-8")
        scp_to_remote(
            host,
            user,
            ssh_key,
            ideas_heartbeat_local,
            "/data/workspace-ideas/HEARTBEAT.md",
        )


def restart_gateway(host: str, user: str, ssh_key: Path) -> None:
    log("Restarting openclaw-gateway")
    ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; systemctl --user restart openclaw-gateway",
    )


def enable_required_hooks(host: str, user: str, ssh_key: Path) -> None:
    log("Enabling required hooks")
    ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; "
        "openclaw hooks enable boot-md; "
        "openclaw hooks enable session-memory; "
        "openclaw hooks enable command-logger",
    )


def reset_main_session(host: str, user: str, ssh_key: Path) -> dict:
    log("Backing up and resetting main session")
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_name = f"main-session-reset.{timestamp}.tgz"
    backup_path = f"/home/{user}/.openclaw/agents/main/{backup_name}"

    ssh_login_shell(
        host,
        user,
        ssh_key,
        f"cd ~/.openclaw/agents/main && tar -czf {shlex.quote(backup_name)} sessions",
    )

    reset_result = None
    for attempt in range(1, 11):
        try:
            reset_result = ssh_login_shell(
                host,
                user,
                ssh_key,
                ". /etc/profile >/dev/null 2>&1 || true; "
                'openclaw gateway call sessions.reset --json --params \'{"key":"agent:main:main"}\'',
            )
            break
        except CommandError as exc:
            if attempt == 10:
                raise
            log(f"Main session reset retry {attempt}/10 after gateway not ready: {exc}")
            time.sleep(3)

    assert reset_result is not None
    payload = parse_json_from_output(reset_result.stdout)
    payload["backupArchive"] = backup_path
    return payload


def validate_setup(host: str, user: str, ssh_key: Path) -> None:
    log("Running lightweight validation")
    agents_result = ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; openclaw agents list --bindings",
    )
    print(agents_result.stdout.strip())

    config_values = ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; "
        "openclaw config get session.dmScope --json; "
        "openclaw config get agents.defaults.heartbeat --json; "
        "openclaw config get agents.list.7.heartbeat --json; "
        "openclaw config get tools.sessions.visibility --json; "
        "openclaw config get tools.agentToAgent --json",
    )
    print(config_values.stdout.strip())

    status_file = ssh_login_shell(
        host,
        user,
        ssh_key,
        "sed -n '1,80p' /data/workspace/TASK_STATUS.md",
    )
    print(status_file.stdout.strip())

    prompt_files = ssh_login_shell(
        host,
        user,
        ssh_key,
        'for f in /data/workspace/AGENTS.md /data/workspace-spec/AGENTS.md /data/workspace-spec/skills/openspec/SKILL.md /data/workspace-coder/AGENTS.md /data/workspace-qa/AGENTS.md /data/workspace-docs/AGENTS.md /data/workspace-release/AGENTS.md /data/workspace-deploy/AGENTS.md /data/workspace-ideas/AGENTS.md /data/workspace-ideas/HEARTBEAT.md /data/workspace/BOOT.md; do echo ===="$f"====; sed -n \'1,60p\' "$f"; done',
    )
    print(prompt_files.stdout.strip())

    hooks_status = ssh_login_shell(
        host,
        user,
        ssh_key,
        ". /etc/profile >/dev/null 2>&1 || true; openclaw hooks list",
    )
    print(hooks_status.stdout.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure an OpenClaw Azure VM so main stays the general entry agent without heartbeat turns, spec flexibly orchestrates development with OpenSpec, coder follows TDD, docs continuously records progress, deploy handles Azure Container Apps deployment with az, and ideas uses its own heartbeat cadence to periodically propose features to spec.",
    )
    parser.add_argument("--host", required=True, help="Public VM FQDN or IP address")
    parser.add_argument(
        "--user", default=DEFAULT_USER, help="SSH username (default: azureuser)"
    )
    parser.add_argument(
        "--ssh-key",
        type=Path,
        default=Path.home() / ".ssh" / "id_ed25519",
        help="Path to the SSH private key",
    )
    parser.add_argument(
        "--skip-dm-scope-main",
        action="store_true",
        help="Do not force session.dmScope to main",
    )
    parser.add_argument(
        "--prune-legacy-direct-sessions",
        action="store_true",
        help="Delete legacy direct sessions under agent:main:* except agent:main:main",
    )
    parser.add_argument(
        "--reset-main-session",
        action="store_true",
        help="Back up ~/.openclaw/agents/main/sessions and reset agent:main:main via sessions.reset",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip the final lightweight OpenClaw prompt validation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ssh_key = args.ssh_key.expanduser().resolve()
    if not ssh_key.exists():
        raise FileNotFoundError(f"SSH key was not found: {ssh_key}")

    ensure_openclaw_ready(args.host, args.user, ssh_key)
    ensure_backend_agents(args.host, args.user, ssh_key)
    summary = apply_remote_config(
        args.host,
        args.user,
        ssh_key,
        set_dm_scope_main=not args.skip_dm_scope_main,
        prune_legacy_direct_sessions=args.prune_legacy_direct_sessions,
    )
    update_remote_agent_files(args.host, args.user, ssh_key)
    enable_required_hooks(args.host, args.user, ssh_key)
    restart_gateway(args.host, args.user, ssh_key)

    log("Applied remote configuration")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.reset_main_session:
        reset_summary = reset_main_session(args.host, args.user, ssh_key)
        log("Reset main session")
        print(json.dumps(reset_summary, ensure_ascii=False, indent=2))

    if not args.skip_validation:
        validate_setup(args.host, args.user, ssh_key)

    log("Main-entry multi-agent setup completed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
