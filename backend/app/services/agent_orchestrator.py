"""Multi-Agent Broadcast Control Room Orchestrator (Orchestrator, Director, Replay, Graphics/Scorebug)."""

import json
import logging
import re
import uuid
from typing import Any

from google import genai
from pydantic import BaseModel, Field

from ..config import DEFAULT_GEMINI_VIDEO_MODEL, get_gemini_api_key
from ..database import list_editor_rules, save_agent_run
from ..schemas import (
    AgentDecisionStep,
    ScorebugState,
    LiveGameSituationInput,
    MultiAgentSimulationResponse,
)

logger = logging.getLogger("courtvision.agent_orchestrator")


class GeminiMultiAgentPlanSchema(BaseModel):
    orchestrator_summary: str = Field(
        description="High-level summary of how the Orchestrator sequenced the Director, Replay, and Scorebug agents"
    )
    edl_steps: list[AgentDecisionStep] = Field(
        description="Chronological control room steps executed by the 4 agents"
    )


def _parse_clock_seconds(clock_str: str) -> float:
    try:
        if ":" in clock_str:
            parts = clock_str.split(":")
            return float(parts[0]) * 60.0 + float(parts[1])
        return float(clock_str)
    except ValueError:
        return 120.0


def _tokenize_situation(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "when",
        "into",
        "during",
        "after",
        "before",
        "while",
        "over",
        "under",
        "ball",
        "game",
        "play",
        "team",
        "player",
    }
    return {
        t
        for t in re.findall(r"[a-z0-9]+", text.lower())
        if len(t) > 2 and t not in stop
    }


def _select_relevant_rules_for_role(
    kb_rules: list[dict[str, Any]],
    role: str,
    situation_tokens: set[str],
    is_crunch_time: bool,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """
    Retrieve the most relevant active rules for `role` across all 12 rule categories,
    automatically suppressing any rule marked 'disagree' by a human reviewer.
    """
    candidates = [
        r
        for r in kb_rules
        if r.get("agent_role") == role and str(r.get("review_status") or "unreviewed") != "disagree"
    ]
    if not candidates:
        candidates = [r for r in kb_rules if r.get("agent_role") == role]

    scored: list[tuple[float, dict[str, Any]]] = []
    for r in candidates:
        blob = f"{r['rule_code']} {r['title']} {r['trigger_condition']} {r['editor_action']}".lower()
        r_tokens = _tokenize_situation(blob)
        overlap = len(situation_tokens & r_tokens)
        score = overlap * 3.0 + float(r.get("priority", 8)) * 0.35 + float(r.get("confidence", 0.9))
        if is_crunch_time and any(k in blob for k in ("final 2", "crunch", "02:00", "press", "clutch", "close")):
            score += 4.5
        if str(r.get("review_status")) == "agree":
            score += 1.0
        scored.append((score, r))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [r for _, r in scored[:top_k]]


def _format_rule_with_reviewer_note(rule: dict[str, Any], base_reasoning: str) -> str:
    comment = str(rule.get("reviewer_comment") or "").strip()
    if str(rule.get("review_status")) == "partially_agree" and comment:
        return f"{base_reasoning} (Reviewer Refinement Applied: {comment})"
    return base_reasoning


def _run_kb_deterministic_control_room(
    situation: LiveGameSituationInput,
    kb_rules: list[dict[str, Any]],
) -> MultiAgentSimulationResponse:
    """Execute the 4-agent control room using dynamic retrieval over all active Knowledge Base rules."""
    clock_sec = _parse_clock_seconds(situation.game_clock)
    margin = abs(situation.home_score - situation.away_score)
    is_crunch_time = clock_sec <= 120.0 and margin <= 6
    desc_lower = situation.play_stream_description.lower()
    sit_tokens = _tokenize_situation(
        f"{situation.scenario_name} {situation.play_stream_description} {situation.period}"
    )

    active_rules = [
        r for r in kb_rules if str(r.get("review_status") or "unreviewed") != "disagree"
    ]
    orc_top = _select_relevant_rules_for_role(active_rules, "orchestrator", sit_tokens, is_crunch_time, top_k=3)
    dir_top = _select_relevant_rules_for_role(active_rules, "director", sit_tokens, is_crunch_time, top_k=3)
    rpl_top = _select_relevant_rules_for_role(active_rules, "replay", sit_tokens, is_crunch_time, top_k=3)
    gfx_top = _select_relevant_rules_for_role(active_rules, "graphics_scorebug", sit_tokens, is_crunch_time, top_k=3)

    has_injury = any(w in desc_lower for w in ("injury", "injured", "limping", "down on the court", "trainer"))
    has_fast_inbound = any(w in desc_lower for w in ("fast inbound", "quick inbound", "fast break", "press", "steal"))
    has_dunk_or_three = any(
        w in desc_lower for w in ("dunk", "alley-oop", "three", "3-pt", "3pt", "layup", "scores", "basket")
    )
    has_foul_or_whistle = any(
        w in desc_lower for w in ("foul", "whistle", "free throw", "and-one", "and-1", "review", "timeout")
    )
    has_run_or_timeout = any(
        w in desc_lower for w in ("timeout", "run", "8-0", "10-2", "bench", "coach")
    )

    score_delta = (
        3
        if ("three" in desc_lower or "3-pt" in desc_lower or "3pt" in desc_lower)
        else (2 if has_dunk_or_three and not has_injury else 0)
    )
    new_home_score = situation.home_score + score_delta

    orc_chosen = orc_top[0] if orc_top else {"rule_code": "ORC-02" if is_crunch_time else "ORC-01", "title": "Broadcast State Routing"}
    dir_chosen = dir_top[0] if dir_top else {"rule_code": "DIR-04" if has_fast_inbound else "DIR-01", "title": "Live Camera Selection"}
    rpl_chosen = rpl_top[0] if rpl_top else {"rule_code": "RPL-02" if has_foul_or_whistle else "RPL-01", "title": "Replay Queue Control"}
    gfx_chosen = gfx_top[0] if gfx_top else {"rule_code": "GFX-01", "title": "Scorebug Score Sync"}

    steps: list[AgentDecisionStep] = []

    steps.append(
        AgentDecisionStep(
            step_order=1,
            offset_sec=0.0,
            game_clock=situation.game_clock,
            shot_clock=situation.shot_clock,
            invoked_agent="orchestrator",
            orchestrator_cue=(
                "EMERGENCY SAFETY LOCK (CUJ 1.4) -> Lock CAM-1 Wide & Suppress Replays"
                if has_injury
                else (
                    "LOCK CRUNCH_TIME_PRESS_MODE -> Cue Live Director to hold CAM-1 Wide"
                    if is_crunch_time
                    else "SET LIVE_HALFCOURT_STATE -> Cue Live Director on CAM-1 Wide & arm Replay Buffer"
                )
            ),
            matched_kb_rule_code=str(orc_chosen["rule_code"]),
            action_command="STATE_TRANSITION: SAFETY_WIDE_LOCK" if has_injury else "STATE_TRANSITION: LIVE_PLAY_MONITORING",
            camera_or_channel="MASTER_CONTROL_BUS",
            reasoning=_format_rule_with_reviewer_note(
                orc_chosen,
                f"Game clock at {situation.game_clock} ({situation.period}) with {margin}-pt margin matched [{orc_chosen['rule_code']}] {orc_chosen['title']}. "
                "Orchestrator routes primary camera authority while enforcing Layer 1 safety and priority arbitration.",
            ),
            scorebug_snapshot=ScorebugState(
                home_team=situation.home_team,
                away_team=situation.away_team,
                home_score=situation.home_score,
                away_score=situation.away_score,
                period=situation.period,
                game_clock=situation.game_clock,
                shot_clock=situation.shot_clock,
                possession=situation.home_team,
                bonus_state="BOTH DOUBLE BONUS" if is_crunch_time else "BONUS",
                active_graphic_banner=None,
            ),
        )
    )

    steps.append(
        AgentDecisionStep(
            step_order=2,
            offset_sec=2.8,
            game_clock=situation.game_clock,
            shot_clock=max(0, situation.shot_clock - 3),
            invoked_agent="director",
            orchestrator_cue="CUE_DIRECTOR: Execute live camera framing & post-play transition",
            matched_kb_rule_code=str(dir_chosen["rule_code"]),
            action_command=(
                "LOCK CAM-1 (Main Wide) RESPECTFUL WIDE HOLD"
                if has_injury
                else (
                    "SUB-SECOND GLANCE CAM-3 [0.7s] -> SNAP BACK TO CAM-1 (Main Wide) FOR FAST INBOUND"
                    if has_fast_inbound and has_dunk_or_three
                    else (
                        "HOLD CAM-1 (Main Wide) -> PUNCH CAM-2 (Baseline Low) [1.1s] -> CUT CAM-3 (Hero Player Iso) [1.5s]"
                        if has_dunk_or_three
                        else "HOLD CAM-1 (Main Wide) LOCKED ON 10-PLAYER SPACING"
                    )
                )
            ),
            camera_or_channel=(
                "CAM-1 (Main Wide)"
                if (has_injury or not has_dunk_or_three)
                else "CAM-2 (Baseline Low) -> CAM-3 (Hero Player Iso) -> CAM-1 (Main Wide)"
            ),
            reasoning=_format_rule_with_reviewer_note(
                dir_chosen,
                f"Applied [{dir_chosen['rule_code']}] {dir_chosen['title']}: "
                f"{'snapped back to CAM-1 Wide in 0.7s to cover live transition pressure.' if has_fast_inbound else 'maintained clean 180-degree court orientation and post-action framing.'}",
            ),
            scorebug_snapshot=ScorebugState(
                home_team=situation.home_team,
                away_team=situation.away_team,
                home_score=new_home_score,
                away_score=situation.away_score,
                period=situation.period,
                game_clock=situation.game_clock,
                shot_clock=30,
                possession=situation.away_team,
                bonus_state="BOTH DOUBLE BONUS" if is_crunch_time else "BONUS",
                active_graphic_banner=f"+{score_delta} PTS ({situation.home_team})" if score_delta else None,
            ),
        )
    )

    steps.append(
        AgentDecisionStep(
            step_order=3,
            offset_sec=3.3,
            game_clock=situation.game_clock,
            shot_clock=30,
            invoked_agent="graphics_scorebug",
            orchestrator_cue="CUE_SCOREBUG: Sync score delta & enforce Read-Twice / screen-space rules",
            matched_kb_rule_code=str(gfx_chosen["rule_code"]),
            action_command=(
                f"UPDATE_SCOREBUG: {situation.home_team} {new_home_score} - {situation.away_team} {situation.away_score} | "
                f"RESET NCAA SHOT CLOCK 30s"
            ),
            camera_or_channel="CG-1 SCOREBUG",
            reasoning=_format_rule_with_reviewer_note(
                gfx_chosen,
                f"Matched [{gfx_chosen['rule_code']}] {gfx_chosen['title']} for verified scorebug synchronization and collision-free lower-third gating.",
            ),
            scorebug_snapshot=ScorebugState(
                home_team=situation.home_team,
                away_team=situation.away_team,
                home_score=new_home_score,
                away_score=situation.away_score,
                period=situation.period,
                game_clock=situation.game_clock,
                shot_clock=30,
                possession=situation.away_team,
                bonus_state="BOTH DOUBLE BONUS" if is_crunch_time else "BONUS",
                active_graphic_banner=f"SCORING UPDATE // {situation.home_team} +{score_delta}" if score_delta else None,
            ),
        )
    )

    steps.append(
        AgentDecisionStep(
            step_order=4,
            offset_sec=4.0,
            game_clock=situation.game_clock,
            shot_clock=30,
            invoked_agent="replay",
            orchestrator_cue=(
                "SUPPRESS_REPLAY: Court injury safety lock active (CUJ 1.4)"
                if has_injury
                else (
                    "DEAD_BALL_WHISTLE: Roll unobstructed slow-mo replay with Scorebug hidden (CUJ 9.3)"
                    if has_foul_or_whistle
                    else "LIVE_BALL_CONTINUES: Silently clip [T-5.0s..T+1.5s] to Replay Bank Slot #1"
                )
            ),
            matched_kb_rule_code=str(rpl_chosen["rule_code"]),
            action_command=(
                "HOLD_REPLAY_BANK_LOCKED (NO INJURY REPLAY)"
                if has_injury
                else (
                    "HIDE_SCOREBUG -> ROLL REPLAY-A / CAM-5 Above-Rim (60% Speed, 5.0s) -> EXIT BEFORE LIVE BALL"
                    if has_foul_or_whistle
                    else "MARK_REPLAY_BUFFER [REPLAY-A + CAM-5 Above-Rim, 6.5s] -> QUEUE FOR NEXT WHISTLE"
                )
            ),
            camera_or_channel="EVS REPLAY-A / CAM-5",
            reasoning=_format_rule_with_reviewer_note(
                rpl_chosen,
                f"Applied [{rpl_chosen['rule_code']}] {rpl_chosen['title']} while enforcing CUJ 9.3 scoreboard hiding and <0.2s live-ball preemption.",
            ),
            scorebug_snapshot=ScorebugState(
                home_team=situation.home_team,
                away_team=situation.away_team,
                home_score=new_home_score,
                away_score=situation.away_score,
                period=situation.period,
                game_clock=situation.game_clock,
                shot_clock=30,
                possession=situation.home_team if has_foul_or_whistle else situation.away_team,
                bonus_state="BOTH DOUBLE BONUS" if is_crunch_time else "BONUS",
                active_graphic_banner="REPLAY // UNOBSTRUCTED ANGLE" if (has_foul_or_whistle and not has_injury) else None,
            ),
        )
    )

    final_dir = dir_top[1] if len(dir_top) > 1 else dir_chosen
    steps.append(
        AgentDecisionStep(
            step_order=5,
            offset_sec=7.5 if has_foul_or_whistle else 5.2,
            game_clock=situation.game_clock,
            shot_clock=30 if has_foul_or_whistle else 26,
            invoked_agent="director",
            orchestrator_cue=(
                "SCORING_RUN_TIMEOUT: Capture coach reaction before huddle"
                if has_run_or_timeout and not has_injury
                else "RETURN_TO_SAFE_HARBOR: Re-anchor CAM-1 Main Wide before live action"
            ),
            matched_kb_rule_code=str(final_dir["rule_code"]),
            action_command=(
                "CUT TO CAM-4 (Coach/Bench Iso) [2.0s] -> RETURN CAM-1 (Main Wide)"
                if has_run_or_timeout and not has_injury
                else "CUT TO CAM-1 (Main Wide) PRIOR TO LIVE BALL"
            ),
            camera_or_channel="CAM-4 (Coach/Bench Iso)" if (has_run_or_timeout and not has_injury) else "CAM-1 (Main Wide)",
            reasoning=_format_rule_with_reviewer_note(
                final_dir,
                f"Completed sequence under [{final_dir['rule_code']}] {final_dir['title']}, restoring CAM-1 Main Wide and live Scorebug before play resumes.",
            ),
            scorebug_snapshot=ScorebugState(
                home_team=situation.home_team,
                away_team=situation.away_team,
                home_score=new_home_score,
                away_score=situation.away_score,
                period=situation.period,
                game_clock=situation.game_clock,
                shot_clock=30 if has_foul_or_whistle else 26,
                possession=situation.away_team,
                bonus_state="BOTH DOUBLE BONUS" if is_crunch_time else "BONUS",
                active_graphic_banner=None,
            ),
        )
    )

    suppressed_count = len(kb_rules) - len(active_rules)
    run_id = f"run-{uuid.uuid4().hex[:10]}"
    response = MultiAgentSimulationResponse(
        run_id=run_id,
        scenario_name=situation.scenario_name,
        model_used=f"{DEFAULT_GEMINI_VIDEO_MODEL} + KB Rule Engine ({len(active_rules)} active rules, {suppressed_count} reviewer-suppressed)",
        execution_mode="kb_deterministic_fallback",
        orchestrator_summary=(
            f"Orchestrator evaluated '{situation.scenario_name}' at {situation.game_clock} ({situation.period}) "
            f"[{situation.home_team} {situation.home_score} - {situation.away_team} {situation.away_score}]. "
            f"Matched rules [{orc_chosen['rule_code']}, {dir_chosen['rule_code']}, {gfx_chosen['rule_code']}, {rpl_chosen['rule_code']}] "
            f"across {len(active_rules)} active KB rules and coordinated {len(steps)} synchronized control-room steps."
        ),
        edl_steps=steps,
    )
    save_agent_run(response.model_dump())
    return response


def run_multi_agent_control_room(
    situation: LiveGameSituationInput,
) -> MultiAgentSimulationResponse:
    """Run the 4-Agent Broadcast Control Room using Gemini 3.8 Flash + relevant active Editor Knowledge Base rules."""
    kb_rules = list_editor_rules()
    active_rules = [
        r for r in kb_rules if str(r.get("review_status") or "unreviewed") != "disagree"
    ]
    api_key = get_gemini_api_key()

    if api_key:
        try:
            clock_sec = _parse_clock_seconds(situation.game_clock)
            margin = abs(situation.home_score - situation.away_score)
            is_crunch_time = clock_sec <= 120.0 and margin <= 6
            sit_tokens = _tokenize_situation(
                f"{situation.scenario_name} {situation.play_stream_description} {situation.period}"
            )

            # Retrieve top 12 most relevant rules per agent (48 rules total) instead of dumping 180KB of redundant JSON
            shortlisted: list[dict[str, Any]] = []
            for role in ("orchestrator", "director", "replay", "graphics_scorebug"):
                shortlisted.extend(
                    _select_relevant_rules_for_role(active_rules, role, sit_tokens, is_crunch_time, top_k=12)
                )

            client = genai.Client(api_key=api_key)
            rules_summary = json.dumps(
                [
                    {
                        "rule_code": r["rule_code"],
                        "agent_role": r["agent_role"],
                        "title": r["title"],
                        "trigger_condition": r["trigger_condition"],
                        "editor_action": r["editor_action"],
                        "timing_constraint": r["timing_constraint"],
                        "priority": r["priority"],
                        **(
                            {"reviewer_note": r["reviewer_comment"]}
                            if r.get("reviewer_comment")
                            else {}
                        ),
                    }
                    for r in shortlisted
                ],
                indent=2,
            )

            prompt = f"""
You are the 4-Agent NCAA Men's College Basketball Broadcast Control Room powered by Gemini Video Intelligence:
1. `orchestrator` (Broadcast Orchestrator Agent)
2. `director` (Live Game Director Agent)
3. `replay` (Replay Capture & Queue Agent)
4. `graphics_scorebug` (Graphics & Scorebug Scoring Agent)

Use the following Active Human-Reviewed Editor Knowledge Base Rules (spanning STORY-*, DIR-*, ORC-*, RPL-*, GFX-*, AUD-*, CAM-*, CNT-*, ARB-*, LYT-*, BRK-*, REL-*):
{rules_summary}

Simulate the exact multi-agent coordination and produce a 5-to-7 step chronological Master Edit Decision List (`edl_steps`) for this live NCAA basketball situation (two 20-minute halves, 30s/20s shot clock):
- Scenario: {situation.scenario_name}
- Score: {situation.home_team} {situation.home_score} vs {situation.away_team} {situation.away_score}
- Clock: {situation.game_clock} ({situation.period}), Shot Clock: {situation.shot_clock}s
- Live Action Stream: {situation.play_stream_description}

Every step MUST reference a real `matched_kb_rule_code` from the shortlisted Knowledge Base above, obey all Layer 1 guardrails (CUJ 1.4 Injury Wide Lock, CUJ 9.3 Replay Scorebug Hide, CUJ 10.3 Read-Twice), avoid em dashes, and update `scorebug_snapshot` accurately.
""".strip()

            inputs: list[Any] = []
            if situation.video_uri_or_url and situation.video_uri_or_url.startswith("https://"):
                inputs.append(
                    {
                        "type": "video",
                        "uri": situation.video_uri_or_url,
                        "processing": "agentic",
                    }
                )
            inputs.append({"type": "text", "text": prompt})

            interaction = client.interactions.create(
                model=DEFAULT_GEMINI_VIDEO_MODEL,
                input=inputs,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": GeminiMultiAgentPlanSchema.model_json_schema(),
                },
            )
            parsed = GeminiMultiAgentPlanSchema.model_validate_json(interaction.output_text)
            run_id = f"run-{uuid.uuid4().hex[:10]}"
            result = MultiAgentSimulationResponse(
                run_id=run_id,
                scenario_name=situation.scenario_name,
                model_used=DEFAULT_GEMINI_VIDEO_MODEL,
                execution_mode="gemini_live_api",
                orchestrator_summary=parsed.orchestrator_summary.replace("—", ": "),
                edl_steps=parsed.edl_steps,
            )
            save_agent_run(result.model_dump())
            return result
        except Exception as exc:
            logger.warning(
                "Gemini live API call fell back to KB deterministic engine: %s",
                type(exc).__name__,
            )

    return _run_kb_deterministic_control_room(situation, kb_rules)
