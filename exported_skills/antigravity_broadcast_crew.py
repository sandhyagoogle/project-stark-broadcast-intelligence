"""Multi-Agent College Basketball Broadcast Control Room using Google Antigravity SDK & Gemini 3.8 Flash."""

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
            "timestamped Master Edit Decision List (EDL) for this live game situation:\n\n"
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
