"""Compiles the Editor Knowledge Base into standardized SKILL.md agent packages and Antigravity SDK runner code."""

import json
from typing import Any

from ..config import EXPORTED_SKILLS_DIR, resolve_safe_path
from ..database import list_editor_rules

AGENT_SKILL_METADATA: dict[str, dict[str, str]] = {
    "orchestrator": {
        "folder": "orchestrator-agent",
        "name": "broadcast-orchestrator-agent",
        "title": "Broadcast Orchestrator Agent",
        "description": (
            "Master broadcast control-room orchestrator for live college basketball. "
            "Monitors the game clock, shot clock, whistle/dead-ball state, and scoring runs "
            "to dynamically queue and hand off control between the Live Director Agent, "
            "Replay Agent, and Graphics & Scorebug Agent."
        ),
        "contract": (
            "Emit structured **ORCHESTRATOR_CUE** commands specifying which specialist agent "
            "(**director**, **replay**, or **graphics_scorebug**) is queued, the active broadcast state "
            "(**LIVE_HALFCOURT**, **DEAD_BALL_FOUL_WINDOW**, **MEDIA_TIMEOUT_BUMPER**, **CRUNCH_TIME_LOCKOUT**), "
            "and the general timing window."
        ),
    },
    "director": {
        "folder": "live-director-agent",
        "name": "live-game-director-agent",
        "title": "Live Game Director Agent (Technical Director / Switcher)",
        "description": (
            "Executes live multi-camera cuts for college basketball broadcasts based on "
            "learned human editor heuristics. Switches between CAM-1 (Main Wide), CAM-2 (Baseline Low), "
            "CAM-3 (Hero Player Iso), CAM-4 (Coach/Bench Iso), and CAM-5 (Above-Rim)."
        ),
        "contract": (
            "Emit switcher **CUT TO <CAMERA_BUS>** commands with generalized pacing guidance and example hold windows, "
            "citing the learned **DIR-*** Knowledge Base rule and game clock condition."
        ),
    },
    "replay": {
        "folder": "replay-agent",
        "name": "replay-capture-and-queue-agent",
        "title": "Replay Capture & Queue Agent (EVS / Slow-Mo Producer)",
        "description": (
            "Continuously monitors live basketball action to silently clip high-excitement plays "
            "(dunks, blocks, transition 3s) into rolling replay buffers and rolls slow-motion "
            "replays during dead-ball whistles, free-throw walk-ups, and official reviews."
        ),
        "contract": (
            "Emit **MARK_REPLAY_BUFFER [T_start, T_end]** during live play and **ROLL_REPLAY_PACKAGE** "
            "(with playback speed %, camera angles, stinger wipe, and exit safety margin before FT/inbound) "
            "during dead balls, citing the learned **RPL-*** rule."
        ),
    },
    "graphics_scorebug": {
        "folder": "graphics-scorebug-agent",
        "name": "graphics-and-scorebug-scoring-agent",
        "title": "Graphics & Scorebug Scoring Agent (Chyron / Scorebug Operator)",
        "description": (
            "Manages the live broadcast scorebug (Home/Away score, Period, Game Clock, Shot Clock 30s/20s resets, "
            "Bonus/Double-Bonus badges) and triggers Lower-Third player/team stat overlays during free throws, "
            "foul trouble substitutions, and scoring runs."
        ),
        "contract": (
            "Emit **UPDATE_SCOREBUG** state payloads and **TRIGGER_LOWER_THIRD** graphic overlays with generalized "
            "display timing and clear conditions, citing the learned **GFX-*** Knowledge Base rule."
        ),
    },
}


def _render_skill_markdown(role: str, rules: list[dict[str, Any]]) -> str:
    meta = AGENT_SKILL_METADATA[role]
    lines = [
        "---",
        f"name: {meta['name']}",
        f"description: {meta['description']}",
        "---",
        "",
        f"# {meta['title']}",
        "",
        "## Overview",
        meta["description"],
        "",
        "## Project Stark Constitutional Guardrails (go/project-stark-prd)",
        "- **Two-Role Model**: You operate as the autonomous **AI Agent** partnered with the human **Showmaker** (combined Producer + Director). Execute cuts directly to Program (PGM) without staging on Preview/Take.",
        "- **CUJ 1.4 Camera 1 Emergency Takeover**: If the Showmaker triggers **Takeover** (court injury, fight, or AI rabbit-hole), immediately lock Program to **CAM-1 (Main Wide)** and block all replays until **Resume** is clicked on the next throw-in.",
        "- **CUJ 1.1 Sustained Glitch Failover**: Never switch off **CAM-1** for a single dropped frame; fail over to **CAM-2** only on sustained glitches ('taking hits') and alert the Showmaker to widen out **CAM-2**.",
        "- **CUJ 9.3 & 7A.2 Scorebug Replay Hiding**: Automatically hide the broadcast scorebug whenever an instant replay or Option A/B storytelling package airs, and restore Scorebug on **CAM-1** before live play restarts.",
        "- **CUJ 10.3 Font 1 Preview & Read-Twice Rule**: Route pre-calculated graphics to **Font 1** first; only air text graphics when the remaining pause duration allows viewers to read all words twice.",
        "",
        "## Output Command Contract",
        meta["contract"],
        "",
        "## Plain-English NCAA Court & Camera Reference",
        "- **CAM-1 (Main Wide)**: Elevated center-court camera showing all 10 players and both hoops (~70% of game air time).",
        "- **CAM-2 (Baseline Low)**: Floor-level camera behind the basket for drives, layups, and baseline out-of-bounds plays.",
        "- **CAM-3 (Player Close-Up)**: Tight chest-up camera for scorer celebrations, free-throw shooters, and star reactions.",
        "- **CAM-4 (Coach & Bench)**: Sideline camera focused on head coaches, team huddles, and bench reactions.",
        "- **CAM-5 (Above-Rim)**: Overhead backboard camera for dunks, blocked shots, and fingertip review replays.",
        "- **NCAA Men's Basketball Structure**: Two 20-minute halves (plus 5-minute Overtime if tied), 30-second shot clock (20-second reset on offensive rebounds), 10-second backcourt count, 5-personal-foul player disqualification, 1-and-1 Bonus at 7 team fouls (Double Bonus at 10), and mandatory media timeouts under 16:00, 12:00, 8:00, and 4:00 of each half.",
        "",
        "## Macro Game-Storytelling & Broadcast Pacing Patterns (STORY-*)",
        "",
        "These macro rules govern overall game-level storytelling, camera air-time allocation (such as time on CAM-1 Wide vs. specialty cameras), three-act tempo across halves, and multi-possession player arcs:",
        "",
    ]

    eng_prefixes = ("AUD-", "CAM-", "CNT-", "ARB-", "LYT-", "BRK-", "REL-")
    macro_rules = [r for r in rules if str(r.get("rule_code", "")).startswith("STORY-")]
    eng_rules = [r for r in rules if str(r.get("rule_code", "")).startswith(eng_prefixes)]
    shot_rules = [
        r
        for r in rules
        if not str(r.get("rule_code", "")).startswith("STORY-")
        and not str(r.get("rule_code", "")).startswith(eng_prefixes)
    ]

    def _format_reviewer_line(rule_item: dict[str, Any]) -> list[str]:
        status = str(rule_item.get("review_status") or "unreviewed")
        comment = str(rule_item.get("reviewer_comment") or "").strip()
        reviewer = str(rule_item.get("reviewer_name") or "Broadcast Reviewer").strip()
        if status == "unreviewed" and not comment:
            return []
        label_map = {
            "agree": "AGREED",
            "partially_agree": "PARTIALLY AGREED",
            "disagree": "DISAGREED (DO NOT EXECUTE WITHOUT REVISION)",
            "unreviewed": "COMMENTED",
        }
        status_label = label_map.get(status, status.upper())
        note = f" | Reviewer Note: {comment}" if comment else ""
        return [f"- **Human Reviewer Sign-Off ({reviewer})**: {status_label}{note}"]

    for rule in macro_rules:
        timestamps = ", ".join(rule.get("example_timestamps", [])) or "N/A"
        lines.extend(
            [
                f"### [{rule['rule_code']}] {rule['title']} (Priority: {rule['priority']}/10 | Confidence: {int(float(rule['confidence']) * 100)}%)",
                f"- **Storytelling Context**: {rule['trigger_condition']}",
                f"- **Broadcast Pacing Policy**: {rule['editor_action']}",
                f"- **Full-Game Target & Cadence**: {rule['timing_constraint']}",
                f"- **Observed Occurrences**: {rule['observed_count']}x across analyzed broadcasts (Examples: {timestamps})",
                *_format_reviewer_line(rule),
                "",
            ]
        )

    lines.extend(
        [
            "## Control-Room Engineering & Production Systems Rules (AUD-*, CAM-*, CNT-*, ARB-*, LYT-*, BRK-*, REL-*)",
            "",
            "These system-level rules govern audio/commentator synchronization, pre-cut camera motion stability, 180-degree spatial continuity, multi-agent conflict arbitration, overlay collision avoidance, commercial break sequences, and degraded-confidence fallbacks:",
            "",
        ]
    )

    for rule in eng_rules:
        timestamps = ", ".join(rule.get("example_timestamps", [])) or "N/A"
        lines.extend(
            [
                f"### [{rule['rule_code']}] {rule['title']} (Priority: {rule['priority']}/10 | Confidence: {int(float(rule['confidence']) * 100)}%)",
                f"- **System Condition**: {rule['trigger_condition']}",
                f"- **Control-Room Behavior**: {rule['editor_action']}",
                f"- **Timing & Safety Constraint**: {rule['timing_constraint']}",
                f"- **Observed Occurrences**: {rule['observed_count']}x across analyzed broadcasts (Examples: {timestamps})",
                *_format_reviewer_line(rule),
                "",
            ]
        )

    lines.extend(
        [
            "## Shot-Level Transition & Event Heuristics (Observational + Shadow Mode KB)",
            "",
            "You MUST follow these generalized shot-level transition rules distilled from full and condensed college basketball broadcasts (numerical values in parentheses are illustrative examples rather than rigid cutoffs):",
            "",
        ]
    )

    for rule in shot_rules:
        timestamps = ", ".join(rule.get("example_timestamps", [])) or "N/A"
        lines.extend(
            [
                f"### [{rule['rule_code']}] {rule['title']} (Priority: {rule['priority']}/10 | Confidence: {int(float(rule['confidence']) * 100)}%)",
                f"- **When to Trigger**: {rule['trigger_condition']}",
                f"- **Editor Action**: {rule['editor_action']}",
                f"- **Generalized Timing Guidance**: {rule['timing_constraint']}",
                f"- **Observed Occurrences**: {rule['observed_count']}x across analyzed broadcasts (Examples: {timestamps})",
                *_format_reviewer_line(rule),
                "",
            ]
        )

    lines.extend(
        [
            "## Coordination Protocol",
            "- Always include the **rule_code** (such as **STORY-01**, **ORC-01**, **DIR-01**, **RPL-02**, **GFX-01**) in your decision trace.",
            "- Balance macro game storytelling (camera share targets, three-act pacing, and star/foul-trouble arcs) with shot-level transition rules.",
            "- Never violate a Priority 10 constraint (such as cutting away from **CAM-1 (Main Wide)** during late shot-clock possessions or lingering on a Hero Iso during a Crunch Time full-court press).",
            "",
        ]
    )
    return "\n".join(lines)


def _render_antigravity_sdk_runner() -> str:
    return '''"""Multi-Agent College Basketball Broadcast Control Room using Google Antigravity SDK & Gemini 3.8 Flash."""

import asyncio
from pathlib import Path
from google.antigravity import Agent, LocalAgentConfig, types


SKILLS_ROOT = Path(__file__).resolve().parent


def build_broadcast_control_room_config() -> LocalAgentConfig:
    """Configure the Orchestrator Agent and its 3 specialist subagents loaded with learned SKILL.md packages."""
    director_subagent = types.SubagentConfig(
        name="live_director_agent",
        description=(
            "Live Game Director Agent that switches camera buses (CAM-1 Wide, CAM-2 Baseline, "
            "CAM-3 Hero Iso, CAM-4 Coach Iso, CAM-5 Above-Rim) using learned DIR-* heuristics."
        ),
        capabilities=types.SubagentCapabilities(
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
            enabled_tools=[types.BuiltinTools.VIEW_FILE],
        ),
    )

    replay_subagent = types.SubagentConfig(
        name="replay_agent",
        description=(
            "Replay Capture & Queue Agent that clips rolling replay buffers during live play "
            "and rolls slow-motion replay packages during dead balls using learned RPL-* heuristics."
        ),
        capabilities=types.SubagentCapabilities(
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
            enabled_tools=[types.BuiltinTools.VIEW_FILE],
        ),
    )

    graphics_scorebug_subagent = types.SubagentConfig(
        name="graphics_scorebug_agent",
        description=(
            "Graphics & Scorebug Scoring Agent that updates the live scorebug, shot clock (30s/20s), "
            "bonus indicators, and lower-third stat banners using learned GFX-* heuristics."
        ),
        capabilities=types.SubagentCapabilities(
            agent_behavior=types.AgentBehavior.AUTONOMOUS,
            enabled_tools=[types.BuiltinTools.VIEW_FILE],
        ),
    )

    return LocalAgentConfig(
        skills_paths=[str(SKILLS_ROOT)],
        subagents=[director_subagent, replay_subagent, graphics_scorebug_subagent],
        capabilities=types.CapabilitiesConfig(
            enable_subagents=True,
            max_subagent_depth=2,
            allowed_subagents=[
                "live_director_agent",
                "replay_agent",
                "graphics_scorebug_agent",
            ],
        ),
    )


async def run_live_sequence(play_situation: str) -> None:
    config = build_broadcast_control_room_config()
    async with Agent(config) as orchestrator:
        prompt = (
            "You are the Broadcast Orchestrator Agent. Using your loaded broadcast skills "
            "(broadcast-orchestrator-agent, live-game-director-agent, replay-capture-and-queue-agent, "
            "and graphics-and-scorebug-scoring-agent), coordinate your subagents to produce a "
            "timestamped Master Edit Decision List (EDL) for this live game situation:\\n\\n"
            f"{play_situation}"
        )
        response = await orchestrator.chat(prompt)
        print(await response.text())


if __name__ == "__main__":
    sample_situation = (
        "2nd Half, 01:48 remaining, Duke 74 - UNC 71. Duke drives baseline, finishes a contested "
        "two-hand dunk (+2) and draws the whistle for an and-one shooting foul (UNC #4's 4th personal foul)."
    )
    asyncio.run(run_live_sequence(sample_situation))
'''


def export_all_agent_skills() -> dict[str, Any]:
    """Generate SKILL.md packages on disk for all 4 broadcast agents and return their contents."""
    all_rules = list_editor_rules()
    packages: list[dict[str, Any]] = []

    for role, meta in AGENT_SKILL_METADATA.items():
        role_rules = [r for r in all_rules if r["agent_role"] == role]
        skill_dir = resolve_safe_path(EXPORTED_SKILLS_DIR, meta["folder"])
        refs_dir = skill_dir / "references"
        skill_dir.mkdir(parents=True, exist_ok=True)
        refs_dir.mkdir(parents=True, exist_ok=True)

        skill_md_content = _render_skill_markdown(role, role_rules)
        skill_md_path = skill_dir / "SKILL.md"
        skill_md_path.write_text(skill_md_content, encoding="utf-8")

        heuristics_json_path = refs_dir / "heuristics.json"
        heuristics_json_path.write_text(
            json.dumps(role_rules, indent=2), encoding="utf-8"
        )

        packages.append(
            {
                "agent_role": role,
                "skill_name": meta["name"],
                "title": meta["title"],
                "description": meta["description"],
                "skill_md_path": str(skill_md_path),
                "heuristics_json_path": str(heuristics_json_path),
                "rule_count": len(role_rules),
                "skill_markdown": skill_md_content,
            }
        )

    runner_path = resolve_safe_path(EXPORTED_SKILLS_DIR, "antigravity_broadcast_crew.py")
    runner_code = _render_antigravity_sdk_runner()
    runner_path.write_text(runner_code, encoding="utf-8")

    return {
        "skills_root_dir": str(EXPORTED_SKILLS_DIR),
        "antigravity_runner_path": str(runner_path),
        "antigravity_runner_code": runner_code,
        "packages": packages,
    }
