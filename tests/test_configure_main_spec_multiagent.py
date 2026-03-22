import unittest
from pathlib import Path

from scripts.configure_main_spec_multiagent import (
    AGENT_SKILLS,
    BACKEND_AGENTS,
    IDEAS_HEARTBEAT,
    IDEAS_HEARTBEAT_TEMPLATE,
    DISABLED_HEARTBEAT,
    MAIN_AGENTS_MD,
    MAIN_ALLOWLIST,
    MAIN_BOOT_MD,
    OPENSPEC_SKILL_NAME,
    OPENSPEC_SKILL_SOURCE,
    parse_json_from_output,
    REMOTE_CONFIG_PATCH,
    SPEC_ALLOWLIST,
    STATUS_BOARD_TEMPLATE,
    WORKER_ALLOWLIST,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "configure_main_spec_multiagent.py"


class ConfigureMainSpecMultiagentTests(unittest.TestCase):
    def test_main_prompt_requires_status_updates(self):
        self.assertIn("/data/workspace/TASK_STATUS.md", MAIN_AGENTS_MD)
        self.assertIn(
            "For any development-task reply, refresh `/data/workspace/TASK_STATUS.md` in the same turn before answering.",
            MAIN_AGENTS_MD,
        )
        self.assertIn(
            "active agent, state, current step, blocker, and next handoff",
            MAIN_AGENTS_MD,
        )

    def test_boot_prompt_mentions_status_board(self):
        self.assertIn("TASK_STATUS.md", MAIN_BOOT_MD)
        self.assertIn("refresh the status board in the same turn", MAIN_BOOT_MD)
        self.assertIn("`main` should summarize active agent", MAIN_BOOT_MD)

    def test_status_board_template_captures_blockers(self):
        self.assertIn("- Owner: main", STATUS_BOARD_TEMPLATE)
        self.assertIn("- Blocker: none", STATUS_BOARD_TEMPLATE)
        self.assertIn("- Next Handoff: none", STATUS_BOARD_TEMPLATE)

    def test_ideas_heartbeat_is_enabled_while_default_is_disabled(self):
        self.assertEqual(DISABLED_HEARTBEAT, {"every": "0m"})
        self.assertEqual(IDEAS_HEARTBEAT["every"], "15m")
        self.assertEqual(IDEAS_HEARTBEAT["target"], "none")
        self.assertTrue(IDEAS_HEARTBEAT["lightContext"])
        self.assertIn("Send worthwhile proposals to spec", IDEAS_HEARTBEAT["prompt"])
        self.assertIn(
            "if so, reply HEARTBEAT_OK",
            IDEAS_HEARTBEAT["prompt"],
        )

    def test_ideas_heartbeat_template_routes_good_proposals_to_spec(self):
        for agent_id in ["spec", "coder", "qa", "docs", "deploy", "release"]:
            self.assertIn(f"`{agent_id}`", IDEAS_HEARTBEAT_TEMPLATE)
        self.assertIn(
            "If active delivery work is still underway", IDEAS_HEARTBEAT_TEMPLATE
        )
        self.assertIn(
            "at most one concrete, near-term improvement idea", IDEAS_HEARTBEAT_TEMPLATE
        )
        self.assertIn(
            "send it to `spec` with a `STATUS:` block", IDEAS_HEARTBEAT_TEMPLATE
        )
        self.assertIn("reply `HEARTBEAT_OK`", IDEAS_HEARTBEAT_TEMPLATE)

    def test_spec_prompt_owns_status_board_and_bans_role_checks(self):
        content = BACKEND_AGENTS["spec"]["content"]
        self.assertIn("source of truth for active task status", content)
        self.assertIn("Never ask backend agents abstract role-check questions", content)
        self.assertIn("workspace `openspec` skill", content)
        self.assertIn("openspec list", content)
        self.assertIn(
            "Do not directly write product code, tests, deployment changes, or user/operator docs",
            content,
        )
        self.assertIn("Prefer clean-context delegation", content)

    def test_spec_keeps_orchestration_tools_while_workers_cannot_orchestrate(self):
        self.assertIn("subagents", SPEC_ALLOWLIST)
        self.assertIn("sessions_spawn", SPEC_ALLOWLIST)
        self.assertNotIn("subagents", WORKER_ALLOWLIST)
        self.assertNotIn("sessions_spawn", WORKER_ALLOWLIST)
        self.assertNotIn("sessions_yield", WORKER_ALLOWLIST)

    def test_spec_agent_loads_openspec_skill(self):
        self.assertEqual(AGENT_SKILLS["spec"], [OPENSPEC_SKILL_NAME])

    def test_openspec_skill_asset_exists_and_is_gated_by_binary(self):
        self.assertTrue(OPENSPEC_SKILL_SOURCE.exists())
        content = OPENSPEC_SKILL_SOURCE.read_text(encoding="utf-8")
        self.assertIn("name: openspec", content)
        self.assertIn('"bins":["openspec"]', content)
        self.assertIn("openspec validate <item-name>", content)

    def test_backend_prompts_require_status_block(self):
        for agent_id in ["coder", "qa", "docs", "release", "deploy", "ideas"]:
            content = BACKEND_AGENTS[agent_id]["content"]
            self.assertIn("Start your reply with a `STATUS:` block.", content)
            self.assertIn(
                "`agent`, `state`, `task`, `current`, `blocker`, `next`",
                content,
            )

    def test_worker_prompts_require_handoff_files_as_source_of_truth(self):
        for agent_id in ["coder", "qa", "docs", "release", "deploy"]:
            content = BACKEND_AGENTS[agent_id]["content"]
            self.assertIn("source of truth", content)
            self.assertIn("referenced files", content)

    def test_backend_prompts_suppress_empty_announce_steps(self):
        for agent_id in ["spec", "coder", "qa", "docs", "release", "deploy", "ideas"]:
            content = BACKEND_AGENTS[agent_id]["content"]
            self.assertIn("agent-to-agent announce step", content)
            self.assertIn("ANNOUNCE_SKIP", content)

    def test_ideas_prompt_mentions_heartbeat_behavior(self):
        content = BACKEND_AGENTS["ideas"]["content"]
        self.assertIn("When invoked by heartbeat", content)
        self.assertIn("return `HEARTBEAT_OK`", content)

    def test_allowlists_exclude_known_unavailable_entries(self):
        for entry in ["apply_patch", "cron", "image"]:
            self.assertNotIn(entry, MAIN_ALLOWLIST)
            self.assertNotIn(entry, SPEC_ALLOWLIST)
            self.assertNotIn(entry, WORKER_ALLOWLIST)

    def test_script_centralizes_specialist_delegation_through_spec(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            '"spec": ["coder", "qa", "docs", "release", "deploy", "ideas"]', source
        )
        self.assertIn('"coder": ["spec"]', source)
        self.assertIn('"qa": ["spec"]', source)
        self.assertIn('"docs": ["spec"]', source)
        self.assertIn('"release": ["spec"]', source)
        self.assertIn('"deploy": ["spec"]', source)

    def test_remote_patch_removes_global_tools_profile(self):
        self.assertIn('tools.pop("profile", None)', REMOTE_CONFIG_PATCH)
        self.assertIn(
            'config.setdefault("agents", {}).setdefault("defaults", {})["heartbeat"] = disabled_heartbeat',
            REMOTE_CONFIG_PATCH,
        )
        self.assertIn('if agent_id == "ideas":', REMOTE_CONFIG_PATCH)
        self.assertIn('agent["heartbeat"] = ideas_heartbeat', REMOTE_CONFIG_PATCH)

    def test_script_validation_no_longer_uses_role_probe_prompts(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("In one short sentence", source)
        self.assertIn("openclaw config get session.dmScope --json", source)
        self.assertIn("openclaw config get agents.defaults.heartbeat --json", source)
        self.assertIn("sed -n '1,80p' /data/workspace/TASK_STATUS.md", source)
        self.assertIn("/data/workspace-spec/skills/openspec/SKILL.md", source)

    def test_script_supports_reset_main_session_option(self):
        source = SCRIPT_PATH.read_text(encoding="utf-8")
        self.assertIn('"--reset-main-session"', source)
        self.assertIn("openclaw gateway call sessions.reset --json", source)
        self.assertIn("main-session-reset.", source)

    def test_parse_json_from_output_ignores_log_prefix(self):
        payload = parse_json_from_output(
            '[plugins] loaded\n{"ok":true,"key":"agent:main:main"}'
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["key"], "agent:main:main")


if __name__ == "__main__":
    unittest.main()
