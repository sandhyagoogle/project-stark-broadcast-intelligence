"""Gemini Video Understanding service using google-genai Interactions API (gemini-3.8-flash)."""

import logging
import time
from pathlib import Path
from typing import Any

from google import genai

from ..config import DEFAULT_GEMINI_VIDEO_MODEL, get_gemini_api_key
from ..schemas import GeminiVideoAnalysisResult, LearnedEditorRuleSchema
from .rule_engine import compute_broadcast_telemetry_metrics, merge_window_rules

logger = logging.getLogger("courtvision.gemini_video")

BROADCAST_ANALYSIS_PROMPT = """
You are an expert NCAA Men's College Basketball Broadcast Producer and Video Intelligence Analyst.
Extract EVERY key broadcast editing moment in this video segment in exact chronological order. Do not cap or truncate the number of events.

CRITICAL NCAA MEN'S BASKETBALL & FORMATTING RULES:
- NCAA Men's Basketball uses TWO 20-MINUTE HALVES (1st Half and 2nd Half, plus 5-minute Overtime periods if tied). Never refer to 'quarters' or '4th quarter'.
- NCAA uses a 30-SECOND SHOT CLOCK (with a 20-second reset on offensive rebounds), a 10-SECOND BACKCOURT COUNT, a 5-PERSONAL-FOUL player disqualification limit, 1-and-1 Bonus at 7 team fouls (Double Bonus at 10), and mandatory media timeouts at Under-16, Under-12, Under-8, and Under-4 of each half.
- Never use em dashes in titles, triggers, actions, or timing constraints. Use colons, commas, or parentheses instead.

Log every instance of:
1. LIVE CAMERA CUTS ('LIVE_CUT' -> agent_domain='director'):
   - Every switch between CAM-1 (Main Wide), CAM-2 (Baseline Low), CAM-3 (Hero Player Iso), CAM-4 (Coach/Bench Iso), and CAM-5 (Above-Rim / Backboard).
   - Every post-basket reaction cut, fast-break wide hold, baseline drive punch-in, and coach/bench reaction cut.
2. REPLAY CAPTURE & ROLLS ('REPLAY_CAPTURE' or 'REPLAY_ROLL' -> agent_domain='replay'):
   - Every live play buffered for replay ('IN' point mark on dunks, blocks, contested fouls, 3-pointers).
   - Every slow-motion replay roll on whistles, free-throw walk-ups, official reviews, and media timeouts.
3. GRAPHICS & NCAA BOX SCOREBOARD ('SCOREBUG_UPDATE' or 'GRAPHICS_LOWER_THIRD' -> agent_domain='graphics_scorebug'):
   - Every Scorebug score change, 20s/30s shot-clock reset, bonus state transition, and Font 1 lower-third stat graphic.
4. BROADCAST ORCHESTRATION ('WHISTLE_DEADBALL' -> agent_domain='orchestrator'):
   - Every whistle, timeout, substitution pause, signal failover, and crunch-time (<02:00) camera lockout.

When distilling reusable editor rules (`learned_rules`), there is NO cap or limit on how many rules you may extract. Extract rules across ALL of these complementary broadcast and engineering dimensions, written in plain, accessible English so someone who does not know basketball can easily follow the game:
- MACRO GAME-STORYTELLING & PACING RULES (`STORY-*`): Overall game-level patterns such as full-game camera air-time allocation (keeping CAM-1 Main Wide on air ~68-74% of the game vs. ~12-15% on CAM-3 Hero Iso), three-act tempo changes across halves (opening establishment vs. mid-game runs vs. crunch time), star player hot-hand or foul-trouble narrative continuity, bench spark-plug storylines, underdog upset tension, and 10-minute replay/graphic cadence budgets.
- SHOT-LEVEL & SITUATIONAL NUANCE RULES (`DIR-*`, `RPL-*`, `GFX-*`, `ORC-*`): Moment-by-moment cuts, replay triggers, and plain-English scoreboard explainers.
- CONTROL-ROOM ENGINEERING & PRODUCTION SYSTEMS RULES:
  * `AUD-*`: Audio-visual synchronization (following commentator 'look-at' callouts, holding replays until analyst sentence completion, crowd decibel hold extensions, acoustic whistle pre-triggers).
  * `CAM-*`: Camera motion & framing (pre-cut camera stability gates against whip-pans, fast-break lead room on CAM-1, half-court zoom corridors, post-free-throw zoom-outs).
  * `CNT-*`: Spatial continuity & eye-trace (180-degree court axis preservation, minimum shot-hold floor against ping-pong cuts, net-splash eye-trace beat).
  * `ARB-*`: Multi-agent priority arbitration & preemption (5-tier conflict hierarchy, mid-replay speed-ramp vs. hard-cut bailout, 1-possession graphic TTL expiration).
  * `LYT-*`: Spatial screen-real-estate & graphic collision avoidance (near-sideline ball occlusion checks, overlay mutual exclusion, under-30s shot-clock hide).
  * `BRK-*`: Commercial break & show structure (3-step going-to-break teases, returning-from-break re-orientation, halftime resets, cold opens).
  * `REL-*`: Ambiguity & degraded-confidence reliability fallbacks (ambiguous whistle holds until referee signal, live lens occlusion auto-eject, low ball-tracking confidence lock to CAM-1).
Always formulate a GENERALIZED broadcast rule first rather than locking onto a rigid exact number, include a measurable timing or cadence window in `timing_constraint`, and include observed timings as parenthetical examples (for instance: "Sub-second hero cut is allowed on fast inbounds (example: 0.7s); return to CAM-1 before mid-court").

Return all chronological timeline events (`events`) and distilled reusable editor rules (`learned_rules`) adhering strictly to the JSON schema.
""".strip()


def _extract_agentic_processing_trace(interaction: Any) -> list[dict[str, str]]:
    """Extract thought and processing_call/processing_result steps from an agentic video interaction."""
    trace: list[dict[str, str]] = []
    steps = getattr(interaction, "steps", None) or []
    for idx, step in enumerate(steps):
        step_type = getattr(step, "type", "unknown")
        if step_type == "thought":
            summaries = getattr(step, "summary", None) or []
            text_parts = [
                getattr(s, "text", "") for s in summaries if getattr(s, "text", None)
            ]
            trace.append(
                {
                    "step": str(idx + 1),
                    "type": "thought",
                    "detail": " ".join(text_parts) or "Navigating broadcast timeline...",
                }
            )
        elif step_type in ("processing_call", "processing_result"):
            call_id = getattr(step, "id", None) or getattr(step, "call_id", "segment")
            trace.append(
                {
                    "step": str(idx + 1),
                    "type": step_type,
                    "detail": f"Agentic timeline inspection ({call_id})",
                }
            )
    return trace


def _run_windowed_broadcast_extraction(
    client: Any,
    video_uri: str,
    title: str,
    mime_type: str | None,
    processing_mode: str,
    duration_seconds: int = 3600,
) -> tuple[GeminiVideoAnalysisResult, list[dict[str, str]]]:
    """
    Two-pass broadcast extraction pipeline:
    - Pass 1: Scan contiguous 5-minute (300s) windows to extract chronological editing events and candidate rules.
    - Pass 2: Compute empirical full-game telemetry metrics from all events and semantically merge/sanitize window rules.
    """
    window_sec = 300
    all_events = []
    raw_window_rules: list[Any] = []
    all_traces: list[dict[str, str]] = []
    summaries: list[str] = []

    for start_sec in range(0, duration_seconds, window_sec):
        end_sec = min(start_sec + window_sec, duration_seconds)
        start_mmss = f"{start_sec // 60:02d}:{start_sec % 60:02d}"
        end_mmss = f"{end_sec // 60:02d}:{end_sec % 60:02d}"

        video_part: dict[str, Any] = {
            "type": "video",
            "uri": video_uri,
            "processing": (
                "agentic"
                if processing_mode == "agentic" and duration_seconds <= 600
                else {
                    "type": "static",
                    "start_offset": start_sec,
                    "end_offset": end_sec,
                    "fps": 1.0,
                }
            ),
        }
        if mime_type:
            video_part["mime_type"] = mime_type

        window_prompt = (
            f"Broadcast Title: {title}\n"
            f"Target Broadcast Window: {start_mmss} to {end_mmss} ({start_sec}s to {end_sec}s).\n"
            f"Extract EVERY camera cut, replay capture/roll, whistle, and Scorebug graphic within [{start_mmss} - {end_mmss}].\n\n"
            f"{BROADCAST_ANALYSIS_PROMPT}"
        )

        interaction = client.interactions.create(
            model=DEFAULT_GEMINI_VIDEO_MODEL,
            input=[
                video_part,
                {"type": "text", "text": window_prompt},
            ],
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": GeminiVideoAnalysisResult.model_json_schema(),
            },
            background=True,
        )

        poll_count = 0
        while getattr(interaction, "status", "") in ("in_progress", "queued"):
            if poll_count >= 120:
                raise TimeoutError(f"Gemini video interaction timed out on window {start_mmss}-{end_mmss}.")
            time.sleep(3)
            interaction = client.interactions.get(interaction.id)
            poll_count += 1

        if getattr(interaction, "status", "") in ("failed", "cancelled"):
            raise RuntimeError(
                f"Gemini video interaction ended with status: {interaction.status}"
            )

        parsed = GeminiVideoAnalysisResult.model_validate_json(interaction.output_text)
        all_events.extend(parsed.events)
        raw_window_rules.extend(parsed.learned_rules)
        if parsed.summary:
            summaries.append(parsed.summary)
        all_traces.extend(_extract_agentic_processing_trace(interaction))

    all_events.sort(key=lambda ev: ev.timestamp_seconds)
    telemetry = compute_broadcast_telemetry_metrics(
        [ev.model_dump() for ev in all_events],
        duration_seconds=duration_seconds,
    )
    consolidated_dicts = merge_window_rules(raw_window_rules)
    validated_rules = [
        LearnedEditorRuleSchema(
            rule_code=r["rule_code"],
            agent_role=r["agent_role"],
            title=r["title"],
            trigger_condition=r["trigger_condition"],
            editor_action=r["editor_action"],
            timing_constraint=r["timing_constraint"],
            priority=r["priority"],
            confidence=r["confidence"],
            observed_count=r["observed_count"],
            example_timestamps=r["example_timestamps"],
        )
        for r in consolidated_dicts
    ]

    merged = GeminiVideoAnalysisResult(
        broadcast_title=title,
        summary=summaries[0] if summaries else f"Full window-by-window analysis of {title}",
        avg_shot_duration_sec=telemetry["avg_shot_duration_sec"],
        replay_frequency_per_10min=telemetry["replay_frequency_per_10min"],
        events=all_events,
        learned_rules=validated_rules,
    )
    return merged, all_traces


def analyze_uploaded_video_file(
    file_path: Path,
    title: str,
    mime_type: str = "video/mp4",
    processing_mode: str = "agentic",
    duration_seconds: int = 3600,
) -> tuple[GeminiVideoAnalysisResult, str | None, list[dict[str, str]]]:
    """Upload a local .mp4/.mov via the Gemini Files API and extract every editing moment across all windows."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in the environment. Set GEMINI_API_KEY to analyze live video files with Gemini 3.8 Flash."
        )

    client = genai.Client(api_key=api_key)
    logger.info("Uploading basketball broadcast via Gemini Files API: %s", file_path.name)
    uploaded_file = client.files.upload(
        file=str(file_path),
        config={"mime_type": mime_type, "display_name": title[:80]},
    )

    max_polls = 120
    polls = 0
    while (
        not getattr(uploaded_file, "state", None)
        or getattr(uploaded_file.state, "name", str(uploaded_file.state)) == "PROCESSING"
    ):
        if polls >= max_polls:
            raise TimeoutError("Timed out waiting for Gemini File API video processing.")
        time.sleep(3)
        uploaded_file = client.files.get(name=uploaded_file.name)
        polls += 1

    state_name = getattr(uploaded_file.state, "name", str(uploaded_file.state))
    if state_name != "ACTIVE":
        raise RuntimeError(f"Gemini File API processing ended in state: {state_name}")

    parsed, trace = _run_windowed_broadcast_extraction(
        client=client,
        video_uri=uploaded_file.uri,
        title=title,
        mime_type=uploaded_file.mime_type or mime_type,
        processing_mode=processing_mode,
        duration_seconds=duration_seconds,
    )
    return parsed, uploaded_file.uri, trace


def analyze_youtube_broadcast(
    youtube_url: str,
    title: str,
    processing_mode: str = "agentic",
    duration_seconds: int = 3600,
) -> tuple[GeminiVideoAnalysisResult, list[dict[str, str]]]:
    """Analyze a public YouTube college basketball broadcast URL across contiguous windows with Gemini 3.8 Flash."""
    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set in the environment. Set GEMINI_API_KEY to analyze YouTube broadcasts with Gemini 3.8 Flash."
        )

    client = genai.Client(api_key=api_key)
    return _run_windowed_broadcast_extraction(
        client=client,
        video_uri=youtube_url,
        title=title,
        mime_type=None,
        processing_mode=processing_mode,
        duration_seconds=duration_seconds,
    )


def inspect_video_micro_window(
    video_record: dict[str, Any],
    start_offset_sec: int,
    end_offset_sec: int,
    fps: float,
    focus_prompt: str,
) -> dict[str, Any]:
    """Run high-FPS static clipping inspection on a specific [start_offset, end_offset] window."""
    api_key = get_gemini_api_key()
    uri = video_record.get("gemini_file_uri") or video_record.get("source_uri", "")
    is_live_uri = uri.startswith("https://") or uri.startswith("gs://")

    if api_key and is_live_uri:
        client = genai.Client(api_key=api_key)
        video_part: dict[str, Any] = {
            "type": "video",
            "uri": uri,
            "processing": {
                "type": "static",
                "start_offset": start_offset_sec,
                "end_offset": end_offset_sec,
                "fps": fps,
            },
        }
        if video_record.get("mime_type"):
            video_part["mime_type"] = video_record["mime_type"]

        interaction = client.interactions.create(
            model=DEFAULT_GEMINI_VIDEO_MODEL,
            input=[
                video_part,
                {
                    "type": "text",
                    "text": (
                        f"Inspect this clipped broadcast window [{start_offset_sec}s to {end_offset_sec}s] "
                        f"sampled at {fps} FPS.\nUser focus: {focus_prompt}\n"
                        "Provide frame-accurate observations of camera cuts, replay stingers, and Scorebug clock/score ticks."
                    ),
                },
            ],
        )
        return {
            "mode": "gemini_static_clipping_live",
            "model": DEFAULT_GEMINI_VIDEO_MODEL,
            "window": f"{start_offset_sec}s - {end_offset_sec}s @ {fps} FPS",
            "analysis": interaction.output_text,
        }

    events = video_record.get("events", [])
    matching_events = [
        e
        for e in events
        if start_offset_sec - 15 <= int(e.get("timestamp_seconds", 0)) <= end_offset_sec + 15
    ]
    if not matching_events and events:
        matching_events = events[:3]

    lines = [
        f"Static High-FPS Micro-Window Analysis ({start_offset_sec}s to {end_offset_sec}s @ {fps} FPS):",
        f"Prompt Focus: {focus_prompt}",
        "",
    ]
    for ev in matching_events:
        fb = ev.get("scorebug", {})
        lines.append(
            f"• [{ev['timestamp_mmss']}] {ev['event_type']} ({ev['camera_angle']}): "
            f"{ev['editor_decision']} | Scorebug: {fb.get('home_team')} {fb.get('home_score')} - "
            f"{fb.get('away_team')} {fb.get('away_score')} ({fb.get('game_clock')} {fb.get('period')}, "
            f"Shot Clock {fb.get('shot_clock')}s)"
        )
        lines.append(f"  ↳ Human Editor Rationale: {ev['editor_rationale']}")

    return {
        "mode": "broadcast_telemetry_inspector",
        "model": f"{DEFAULT_GEMINI_VIDEO_MODEL} (Static Clipping Spec: start_offset={start_offset_sec}, end_offset={end_offset_sec}, fps={fps})",
        "window": f"{start_offset_sec}s - {end_offset_sec}s @ {fps} FPS",
        "analysis": "\n".join(lines),
    }
