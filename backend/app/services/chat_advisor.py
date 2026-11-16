"""Engineering Q&A Advisor for Broadcast Agent Behavior with 346-Rule Retrieval & YouTube Clip Evidence."""

import json
import logging
import math
import re
import sqlite3
from typing import Any

from google import genai
from google.genai import types

from ..config import DEFAULT_GEMINI_VIDEO_MODEL, get_gemini_api_key
from ..database import DB_PATH, list_editor_rules
from ..schemas import AgentChatAnswerResponse, YouTubeClipExample

logger = logging.getLogger("courtvision.chat_advisor")


def _make_clip(
    video_id: str,
    yt_id: str,
    broadcast_title: str,
    timestamp_mmss: str,
    timestamp_seconds: int,
    game_clock: str,
    period: str,
    camera_angle: str,
    court_trigger: str,
    human_editor_cut: str,
    why_this_clip_explains_it: str,
) -> YouTubeClipExample:
    start_sec = max(0, int(timestamp_seconds) - 2)
    return YouTubeClipExample(
        video_id=video_id,
        yt_id=yt_id,
        broadcast_title=broadcast_title,
        timestamp_mmss=timestamp_mmss,
        timestamp_seconds=timestamp_seconds,
        game_clock=game_clock,
        period=period,
        camera_angle=camera_angle,
        court_trigger=court_trigger,
        human_editor_cut=human_editor_cut,
        why_this_clip_explains_it=why_this_clip_explains_it,
        youtube_watch_url=f"https://www.youtube.com/watch?v={yt_id}&t={start_sec}s",
        youtube_embed_url=f"https://www.youtube.com/embed/{yt_id}?start={start_sec}&end={timestamp_seconds + 18}&rel=0",
    )


def _split_plain_guide(trigger_text: str) -> tuple[str, str]:
    """Separate the core trigger condition from the appended [Plain-English Guide: ...] note."""
    if "[Plain-English Guide:" in trigger_text:
        parts = trigger_text.split("[Plain-English Guide:", 1)
        core = parts[0].strip()
        guide = parts[1].rstrip("]").strip()
        return core, guide
    return trigger_text.strip(), ""


SCENARIO_KNOWLEDGE_GRAPH: list[dict[str, Any]] = [
    {
        "keywords": [
            "cut in between",
            "replays ever cut",
            "replay ever cut",
            "interrupt a replay",
            "interrupted replay",
            "cut a replay",
            "cut out of a replay",
            "cut out of replay",
            "cut mid-replay",
            "mid-replay",
            "mid replay",
            "cut short",
            "cut early",
            "abort a replay",
            "abort replay",
            "stop a replay",
            "between replay",
            "between two replay",
            "two replay angles",
            "multi-angle replay",
            "cut during a replay",
            "replay is still playing",
            "while a replay is",
        ],
        "primary_agent": "replay",
        "matched_rule_code": "ARB-02 / CNT-10 / RPL-08 / REL-05",
        "matched_rule_title": "Mid-Replay Preemption, Multi-Angle Replay Cuts & Analyst Sentence Hold",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 312,
        "what_agent_should_do": (
            "Yes. Replays are cut in between in two distinct ways across the 346 broadcast rules:\n\n"
            "1. Cutting a Replay Short Mid-Roll When Live Action Resumes (ARB-02, REL-05, REL-10):\n"
            "• Immediate Hard-Cut Bailout (<0.2s to 0.4s): Live basketball is always Priority 1 (ARB-01). If the referee hands the ball to the free-throw shooter or throw-in passer while a replay is still rolling (ARB-02), or if a defender suddenly steals an inbound pass (REL-05), the Replay Agent immediately cuts out of the replay back to CAM-1 (Main Wide Court View) and restores the scoreboard so viewers never miss live play.\n"
            "• 1.5x Speed-Ramp Finish (<1.0s to Climax): If a replay is less than 1.0 second away from showing the ball go through the hoop and the live ball is not yet in play (ARB-02), the agent briefly speeds up the replay (1.5x speed-ramp) instead of cutting mid-air so viewers still see the finish before returning to CAM-1.\n"
            "• Frozen Clip Watchdog Abort (<=0.8s): If the replay server stalls on a frozen frame when cued (REL-10), the agent aborts the replay within 0.8s back to live cameras.\n\n"
            "2. Cutting Between Two Camera Angles Inside a Multi-Angle Replay (RPL-08, CNT-10):\n"
            "• Two-Angle Dunk/Block Showcase (RPL-08): During longer pauses (timeouts or two-shot fouls), the Replay Agent plays two angles back-to-back, starting with REPLAY-A (Low Baseline) to show the jump and cutting in between to CAM-5 (Above-Rim Camera) right at impact.\n"
            "• Match-On-Action Overlap (CNT-10): When cutting between two replay angles of the same play, the agent never cuts randomly mid-air; it overlaps the action by ~0.5 seconds at the exact moment of takeoff or contact so the viewer's eye tracks the play seamlessly.\n\n"
            "3. When a Replay Is Never Cut In Between (AUD-02):\n"
            "• If the ball is still dead (clock stopped) and the commentator is mid-sentence explaining a foul or footwork play, the agent never cuts away on a rigid timer; it slows or pauses at the contact frame until the analyst finishes speaking."
        ),
        "timing_and_override": (
            "Hard-cut to CAM-1 in <0.2s-0.4s if live play or a backcourt steal begins (ARB-02 / REL-05); "
            "1.5x speed-ramp if <1.0s remains to the basket climax before throw-in (ARB-02); "
            "~0.5s action overlap when cutting between REPLAY-A and CAM-5 in multi-angle replays (CNT-10 / RPL-08)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="05:12",
                timestamp_seconds=312,
                game_clock="15:44",
                period="1ST",
                camera_angle="REPLAY-A -> CAM-5 -> CAM-1",
                court_trigger="Contested baseline drive and shooting foul; analyst narrates the replay before the referee hands the ball to the free-throw shooter.",
                human_editor_cut="Held and speed-ramped the CAM-5 Above-Rim replay through the analyst's point, then cut cleanly back to live CAM-1 right before the free-throw routine.",
                why_this_clip_explains_it="Demonstrates ARB-02 and AUD-02: speed-ramping and timing the replay exit so the analyst finishes speaking and the viewer returns to CAM-1 before the live free throw.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="35:15",
                timestamp_seconds=2115,
                game_clock="10:45",
                period="2ND",
                camera_angle="CAM-5 (Above-Rim / Backboard)",
                court_trigger="Two-hand dunk on baseline cut with an and-one whistle at 10:45 2ND Half.",
                human_editor_cut="Rolled high-motion replay during the dead-ball pause with the Scorebug hidden, then cut back to live CAM-1 before the free-throw handoff.",
                why_this_clip_explains_it="Shows RPL-08 and ARB-02: fitting the replay showcase inside the dead-ball window and cutting back to live CAM-1 before the free throw.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="08:50",
                timestamp_seconds=530,
                game_clock="12:40",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Rapid inbound pass and fast break immediately after a made basket.",
                human_editor_cut="Aborted post-play close-up/replay queue in under 0.8s and snapped immediately to CAM-1 (Main Wide) as the ball crossed mid-court.",
                why_this_clip_explains_it="Demonstrates ARB-18 and REL-05: live transition play immediately preempts any post-score close-up or replay.",
            ),
        ],
    },
    {
        "keywords": [
            "pushes a fast break",
            "fast inbound",
            "hits a 3-pointer and the defense",
            "3rd three-pointer in a row",
            "abort hero",
            "post-score celebration",
        ],
        "primary_agent": "director",
        "matched_rule_code": "DIR-04",
        "matched_rule_title": "Fast-Inbound Transition Override (Generalized Across 52 Full Playlist Broadcasts)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 142,
        "what_agent_should_do": (
            "Hold CAM-1 (Main Wide Court View) while the shot is in the air. After the ball goes through the net, "
            "punch to CAM-3 (Player Close-Up) for a brief celebration on normal walk-up possessions (example: 2.2s). "
            "However, if the opposing team grabs the ball and triggers a rapid inbound or sprints down the court on a fast break, "
            "a sub-second cut is allowed (example: 0.7s) and the Live Director Agent must immediately snap back to CAM-1 (Main Wide Court View) before the ball crosses mid-court."
        ),
        "timing_and_override": (
            "Brief hero hold on normal walk-ups (example: 2s); sub-second cut or immediate return to CAM-1 Wide allowed "
            "whenever the opponent pushes a fast inbound (example: 0.7s)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="08:50",
                timestamp_seconds=530,
                game_clock="12:40",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="West Virginia scores a layup, and Oklahoma inbounds rapidly to push a fast break.",
                human_editor_cut="Used a sub-second post-basket CAM-3 Hero Iso cut (example: 0.8s) and snapped back to CAM-1 (Main Wide) as Oklahoma crossed mid-court.",
                why_this_clip_explains_it="Shows why a fixed multi-second Hero Iso rule fails: holding the close-up here would have missed Oklahoma's live fast break.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="03:42",
                timestamp_seconds=222,
                game_clock="16:18",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Oklahoma guard drains a top-of-the-key 3-pointer with a standard walk-up inbound.",
                human_editor_cut="Held CAM-1 through the shot arc, punched to CAM-3 (Hero Player Iso) after the swish for a standard celebration (example: 2.2s), then returned to CAM-1.",
                why_this_clip_explains_it="Demonstrates the standard hero celebration hold when the defense walks the ball up without a fast-break push.",
            ),
            _make_clip(
                video_id="yt-pl-Luro0VLrXuc",
                yt_id="Luro0VLrXuc",
                broadcast_title="Live Sports Crown: Oklahoma vs Baylor",
                timestamp_mmss="05:09",
                timestamp_seconds=309,
                game_clock="16:31",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="After a made basket, the trailing team triggers a rapid baseline inbound push.",
                human_editor_cut="Used a sub-second CAM-3 Hero Iso cut (example: 0.7s) and returned to CAM-1 Wide before the guard reached the timeline.",
                why_this_clip_explains_it="Confirms the generalized DIR-04 rule allowing sub-second cuts whenever transition begins.",
            ),
        ],
    },
    {
        "keywords": [
            "font 1",
            "quick side-out",
            "side-out whistle",
            "read twice",
            "stat graphic is queued",
            "pause-duration gate",
        ],
        "primary_agent": "graphics_scorebug",
        "matched_rule_code": "GFX-04",
        "matched_rule_title": "Pause-Duration Gate for Font 1 Lower-Thirds (Generalized Read-Twice Rule)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.97,
        "observed_count": 136,
        "what_agent_should_do": (
            "Preview the player or team stat banner on Font 1 during live play, then classify the dead-ball whistle type before airing. "
            "Only take the Font 1 lower-third banner to air during extended stoppages (shooting fouls, free-throw setups, "
            "full substitutions, or timeouts) where viewers have time to read the text twice (example: 6.5s). If the whistle is a quick side-out or baseline throw-in "
            "(example: 2.3s), hold the graphic in preview and do not air it."
        ),
        "timing_and_override": (
            "Hold long enough for viewers to read the text twice (CUJ 10.3) and clear before the referee hands the ball "
            "to the inbounder or free-throw shooter (example: 6s substitution window vs. 2s throw-in)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="31:50",
                timestamp_seconds=1910,
                game_clock="13:12",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Quick side-out-of-bounds deflection at 13:12 2ND Half (example: 2.3s pause).",
                human_editor_cut="Held the queued Font 1 player shooting graphic in preview and suppressed on-air display during the brief throw-in.",
                why_this_clip_explains_it="A quick throw-in is too short for a viewer to read the banner twice without covering live court action on the inbound.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="28:10",
                timestamp_seconds=1690,
                game_clock="15:35",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Dead-ball substitution horn at 15:35 2ND Half with game tied 46-46.",
                human_editor_cut="Aired the Font 1 Points in Paint comparison banner during the full substitution walk-on (example: 6.5s) and cleared before the inbound.",
                why_this_clip_explains_it="Full substitution stoppages give the Graphics Agent enough time to satisfy the Read-Twice rule cleanly.",
            ),
        ],
    },
    {
        "keywords": [
            "referee blocks the replay",
            "baseline referee blocks",
            "blocks the replay angle",
            "occluded replay",
            "occlusion-filtered",
            "broadcast box hide",
        ],
        "primary_agent": "replay",
        "matched_rule_code": "RPL-04",
        "matched_rule_title": "Occlusion-Filtered Multi-Angle Replay Selection & Scorebug Hide",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.97,
        "observed_count": 118,
        "what_agent_should_do": (
            "During live play, silently mark an IN point pre-roll on REPLAY-A (Hi-Motion Baseline) and CAM-5 (Above-Rim) "
            "whenever a dunk, block, or contested foul occurs (CUJ 7A). When the whistle stops the clock, immediately hide the live Scorebug "
            "(CUJ 9.3), check both angles for line-of-sight visibility, drop any baseline angle where a referee or player blocks the rim view, "
            "roll the clean angle in slow-motion, and cut back to live CAM-1 before the free throw or inbound."
        ),
        "timing_and_override": (
            "Roll with the Scorebug hidden during the dead-ball pause (example: 4.8s slow-mo roll) and exit back to live play "
            "before the referee hands the ball to the shooter or inbounder."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="35:15",
                timestamp_seconds=2115,
                game_clock="10:45",
                period="2ND",
                camera_angle="CAM-5 (Above-Rim / Backboard)",
                court_trigger="Contested two-hand dunk by Oklahoma forward on baseline cut with an and-one whistle.",
                human_editor_cut="Dropped CAM-2 (baseline referee occluded the lens at the rim) and rolled a clean CAM-5 Above-Rim replay (example: 4.8s) with Scorebug hidden.",
                why_this_clip_explains_it="Proves why the Replay Agent must run an occlusion check before airing a buffered baseline camera.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="06:04",
                timestamp_seconds=364,
                game_clock="14:12",
                period="1ST",
                camera_angle="CAM-5 (Above-Rim / Backboard)",
                court_trigger="Under-16 media timeout whistle at 14:12 1ST after an earlier live chase-down block at 05:12.",
                human_editor_cut="Hid the Scorebug and rolled the buffered chase-down block from CAM-5 in slow-motion into a CAM-4 bench reaction.",
                why_this_clip_explains_it="Shows delayed replay queuing: the block happened at 05:12 during live transition, so the Replay Agent buffered it and waited for the 06:04 whistle.",
            ),
        ],
    },
    {
        "keywords": [
            "player injury",
            "apparent injury",
            "safety takeover",
            "signal glitch",
            "macro-blocking",
            "sdi signal",
        ],
        "primary_agent": "director",
        "matched_rule_code": "CUJ-1.4",
        "matched_rule_title": "Cam 1 Safety Takeover & Signal Glitch Failover (Constitutional Guardrail)",
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "confidence": 1.0,
        "observed_count": 52,
        "what_agent_should_do": (
            "If a player suffers an apparent injury on the floor or trainers are beckoned onto the court, execute an immediate "
            "Cam 1 Safety Takeover (CUJ 1.4): lock onto CAM-1 (Main Wide) framing and block all close-up Iso cuts and slow-motion replays. "
            "If CAM-1 experiences a sustained SDI signal drop or macro-blocking (ignoring single-frame flickers), trigger Signal Glitch Failover (CUJ 1.1) "
            "to CAM-2 until CAM-1 sync stabilizes."
        ),
        "timing_and_override": (
            "Priority 10 Hard Guardrail: overrides all learned excitement rules. Zero close-ups or replays permitted during injury stoppages."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="39:05",
                timestamp_seconds=2345,
                game_clock="08:20",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Player slips hard on a wet court spot near the baseline at 08:20 2ND and trainers are signaled onto the floor.",
                human_editor_cut="Immediately locked wide CAM-1 framing and suppressed all slow-motion replay rolls before stepping to break.",
                why_this_clip_explains_it="Illustrates the non-negotiable broadcast safety guardrail protecting player dignity during injury stoppages.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="21:10",
                timestamp_seconds=1270,
                game_clock="04:05",
                period="1ST",
                camera_angle="CAM-2 (Baseline Low)",
                court_trigger="Sustained signal macro-blocking detected on CAM-1 at 04:05 1ST.",
                human_editor_cut="Switched program feed to CAM-2 backup until CAM-1 sync stabilized.",
                why_this_clip_explains_it="Shows automatic backup camera failover when signal degradation persists beyond a single dropped frame (CUJ 1.1).",
            ),
        ],
    },
    {
        "keywords": [
            "crunch time",
            "crunch-time",
            "full-court press",
            "full court press",
            "final 2 minutes",
            "under 2 minutes",
            "late shot-clock",
        ],
        "primary_agent": "orchestrator",
        "matched_rule_code": "ORC-02",
        "matched_rule_title": "Crunch-Time Press Lockout & Late Shot-Clock Discipline",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 164,
        "what_agent_should_do": (
            "During late-game close situations or full-court press possessions (or whenever the shot clock winds down into the red zone), "
            "the Orchestrator activates Crunch-Time Lockout: keep the Live Director locked on CAM-1 (Main Wide), allow at most a sub-second "
            "reaction glance after a basket so inbound denials are visible, pulse the Scorebug shot-clock warning in late clock, "
            "and defer non-review replays until full timeout stoppages."
        ),
        "timing_and_override": (
            "Stay on CAM-1 Wide during full-court press and late shot-clock possessions (example: final 7s on shot clock); "
            "only sub-second post-basket glances allowed when press is active."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="52:40",
                timestamp_seconds=3160,
                game_clock="01:22",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Crunch time at 01:22 2ND Half in Crown Championship (OU 74, WVU 72) with active full-court press.",
                human_editor_cut="Locked CAM-1 (Main Wide) immediately on the made basket and suppressed the post-score CAM-3 Hero Iso to show the press.",
                why_this_clip_explains_it="In a two-point game with a full-court press, the inbound denial is the highest-stakes action on the floor.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="48:12",
                timestamp_seconds=2892,
                game_clock="03:05",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Half-court trap forces the shot clock down to 5 seconds with 03:05 remaining in the 2ND Half.",
                human_editor_cut="Stayed locked on CAM-1 wide to show all 10 players and passing lanes while pulsing the Scorebug shot-clock warning.",
                why_this_clip_explains_it="Cutting to a tight Iso camera in the final seconds of the shot clock blinds viewers to open bailout shooters.",
            ),
        ],
    },
    {
        "keywords": ["camera 3", "cam 3", "cam-3", "hero iso", "player iso", "scorer iso"],
        "primary_agent": "director",
        "matched_rule_code": "DIR-02 / DIR-04",
        "matched_rule_title": "CAM-3 (Hero Player Iso) Full-Game Share & Cut Policy",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 1068,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed broadcasts, CAM-3 (Hero Player Iso) is on air for roughly 12% to 15% of total "
            "full-game broadcast time and accounts for 25.1% of all discrete camera cuts (17.7% of tracked specialty cut duration). "
            "The Live Director Agent cuts to CAM-3 in three primary situations: (1) post-basket scorer celebrations on normal walk-ups "
            "(example: 2s to 3.5s hold), (2) sub-second reaction flashes when the opponent pushes a fast inbound before snapping back to CAM-1 Wide "
            "(example: 0.7s per DIR-04), and (3) free-throw shooter routines between foul shots."
        ),
        "timing_and_override": (
            "~12% to 15% of full-game air time (25.1% of discrete cuts). Standard post-basket hold on normal walk-ups (example: 2s to 3.5s); "
            "sub-second cut allowed on fast inbounds (example: 0.7s)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="03:42",
                timestamp_seconds=222,
                game_clock="16:18",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Oklahoma guard drains a top-of-the-key 3-pointer with a standard walk-up inbound.",
                human_editor_cut="Punched from CAM-1 to CAM-3 (Hero Player Iso) after the swish for a standard celebration (example: 2.2s), then returned to CAM-1.",
                why_this_clip_explains_it="Shows a typical CAM-3 Hero Iso cut after a perimeter basket during standard walk-up tempo.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="43:30",
                timestamp_seconds=2610,
                game_clock="05:10",
                period="2ND",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="West Virginia guard hits a corner 3-pointer to tie the game 67-67 at 05:10 2ND, forcing a timeout.",
                human_editor_cut="Held CAM-3 (Hero Player Iso) during the crowd roar (example: 3.2s) before cutting to CAM-4 Coach Iso.",
                why_this_clip_explains_it="Shows an extended CAM-3 Hero Iso hold when a made basket leads directly into a called timeout.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="08:50",
                timestamp_seconds=530,
                game_clock="12:40",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="West Virginia scores a layup and Oklahoma triggers a rapid fast-break inbound.",
                human_editor_cut="Used a sub-second CAM-3 Hero Iso flash (example: 0.8s) and immediately returned to CAM-1 Wide.",
                why_this_clip_explains_it="Shows how CAM-3 is abbreviated to a sub-second cut whenever transition starts immediately.",
            ),
        ],
    },
    {
        "keywords": ["camera 1", "cam 1", "cam-1", "main wide", "wide camera"],
        "primary_agent": "director",
        "matched_rule_code": "DIR-01",
        "matched_rule_title": "CAM-1 (Main Wide) Full-Game Share & Play-by-Play Baseline",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 1757,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed broadcasts, CAM-1 (Main Wide) is on air for roughly 68% to 74% of total "
            "full-game broadcast time (and 41.3% of discrete cut events / 51.8% of transition windows). The Live Director Agent "
            "uses CAM-1 as the continuous baseline during all live half-court play and fast breaks, and locks onto CAM-1 without "
            "exception during late shot-clock possessions, crunch-time full-court presses (ORC-02), and injury takeovers (CUJ 1.4)."
        ),
        "timing_and_override": (
            "~68% to 74% of full-game air time. Continuous hold during active play (example: 5s to 8s between whistles); "
            "mandatory lock during late shot clock (example: under 10s) and crunch-time press."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="48:12",
                timestamp_seconds=2892,
                game_clock="03:05",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Half-court trap forces the shot clock down to 5 seconds with 03:05 remaining in the 2ND Half.",
                human_editor_cut="Stayed locked on CAM-1 (Main Wide) to show all 10 players and passing lanes during the late-clock scramble.",
                why_this_clip_explains_it="Shows why CAM-1 Wide dominates live play and is locked whenever the shot clock winds down.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="52:40",
                timestamp_seconds=3160,
                game_clock="01:22",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Crunch time at 01:22 2ND Half (OU 74, WVU 72) with active full-court press.",
                human_editor_cut="Kept CAM-1 Wide locked after the made basket to capture the full-court inbound denial.",
                why_this_clip_explains_it="Demonstrates mandatory CAM-1 Wide retention during late-game full-court press situations.",
            ),
        ],
    },
    {
        "keywords": ["camera 2", "cam 2", "cam-2", "baseline low", "baseline camera"],
        "primary_agent": "director",
        "matched_rule_code": "DIR-02 / CUJ-1.1",
        "matched_rule_title": "CAM-2 (Baseline Low) Full-Game Share, Rim Finishes & Backup Failover",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.96,
        "observed_count": 365,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed broadcasts, CAM-2 (Baseline Low) accounts for roughly 4% to 6% of total "
            "full-game broadcast time (and 8.6% of discrete specialty cuts). The Live Director Agent punches to CAM-2 for brief "
            "post-dunk or contested paint layup reactions under the basket (example: 1.5s to 2s hold before returning to CAM-1 prior to mid-court), "
            "baseline inbound throw-ins, and as the automatic backup camera if CAM-1 suffers sustained signal glitches (CUJ 1.1)."
        ),
        "timing_and_override": (
            "~4% to 6% of full-game air time (8.6% of discrete cuts). Brief baseline reaction punch after rim finishes (example: 1.8s), "
            "returning to CAM-1 Wide before the ball crosses mid-court."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="01:45",
                timestamp_seconds=105,
                game_clock="18:15",
                period="1ST",
                camera_angle="CAM-2 (Baseline Low)",
                court_trigger="West Virginia forward drives baseline and finishes a reverse layup in traffic at 18:15 1ST.",
                human_editor_cut="Cut from CAM-1 to CAM-2 (Baseline Low) after the ball cleared the net for a brief reaction hold (example: 1.8s), then returned to CAM-1.",
                why_this_clip_explains_it="Demonstrates standard CAM-2 Baseline usage immediately after an interior paint finish.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="21:10",
                timestamp_seconds=1270,
                game_clock="04:05",
                period="1ST",
                camera_angle="CAM-2 (Baseline Low)",
                court_trigger="Sustained signal macro-blocking detected on CAM-1 at 04:05 1ST.",
                human_editor_cut="Switched program feed to CAM-2 backup until CAM-1 sync stabilized.",
                why_this_clip_explains_it="Shows CAM-2 serving as the primary failover camera under CUJ 1.1.",
            ),
        ],
    },
    {
        "keywords": ["camera 4", "cam 4", "cam-4", "coach iso", "bench iso", "coach camera"],
        "primary_agent": "director",
        "matched_rule_code": "DIR-03",
        "matched_rule_title": "CAM-4 (Coach & Bench Iso) Full-Game Share, Timeouts & Foul Trouble",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.95,
        "observed_count": 345,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed broadcasts, CAM-4 (Coach/Bench Iso) accounts for roughly 5% to 7% of total "
            "full-game broadcast time (and 8.1% of discrete specialty cuts). The Live Director Agent cuts to CAM-4 when an opposing coach "
            "calls a timeout during a momentum run, when a player in foul trouble (3rd or 4th personal foul) is substituted to the bench, "
            "or during dead-ball coaching reactions."
        ),
        "timing_and_override": (
            "~5% to 7% of full-game air time (8.1% of discrete cuts). Hold during dead-ball bench reactions or timeout huddles (example: 3s to 5s), "
            "returning to CAM-1 before live throw-in."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="43:30",
                timestamp_seconds=2610,
                game_clock="05:10",
                period="2ND",
                camera_angle="CAM-4 (Coach/Bench Iso)",
                court_trigger="West Virginia ties the game 67-67 at 05:10 2ND and Oklahoma calls a 30-second timeout.",
                human_editor_cut="Cut from CAM-3 Scorer Iso to CAM-4 Coach Iso as the teams walked into the timeout huddle.",
                why_this_clip_explains_it="Shows the classic CAM-3 scorer to CAM-4 coach reaction sequence entering a timeout.",
            ),
        ],
    },
    {
        "keywords": ["camera 5", "cam 5", "cam-5", "above-rim", "above rim", "backboard camera"],
        "primary_agent": "replay",
        "matched_rule_code": "RPL-03",
        "matched_rule_title": "CAM-5 (Above-Rim / Backboard) Full-Game Share & Occlusion Substitute",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.97,
        "observed_count": 118,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed broadcasts, CAM-5 (Above-Rim / Backboard) accounts for roughly 1% to 2% of total "
            "full-game broadcast time. It is primarily used by the Replay Agent for high-angle slow-motion replays on dunks, rim blocks, "
            "and basket-interference reviews, and serves as the automatic substitute whenever a baseline referee or player occludes CAM-2 at the rim (RPL-03)."
        ),
        "timing_and_override": (
            "~1% to 2% of full-game air time. Used during dead-ball slow-motion replay rolls (example: 4s to 5s at 60% speed) with Scorebug hidden."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="35:15",
                timestamp_seconds=2115,
                game_clock="10:45",
                period="2ND",
                camera_angle="CAM-5 (Above-Rim / Backboard)",
                court_trigger="Contested two-hand dunk by Oklahoma forward on baseline cut with an and-one whistle.",
                human_editor_cut="Dropped CAM-2 (occluded by baseline official) and rolled a clean CAM-5 Above-Rim slow-motion replay (example: 4.8s).",
                why_this_clip_explains_it="Demonstrates CAM-5 substituting for an occluded baseline angle on a rim finish.",
            ),
        ],
    },
    {
        "keywords": ["%", "percent", "percentage", "camera share", "camera breakdown", "camera distribution", "how much time", "camera mix", "time on camera"],
        "primary_agent": "director",
        "matched_rule_code": "STORY-01",
        "matched_rule_title": "Full-Game Camera Allocation & CAM-1 Baseline Share (Macro Pacing)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 7984,
        "what_agent_should_do": (
            "Across the 54 analyzed full and condensed college basketball broadcasts (7,984 moments), full-game air time distributes as follows: "
            "CAM-1 (Main Wide) is on air ~68% to 74% of the game (continuous play-by-play baseline); "
            "CAM-3 (Hero Player Iso) is on air ~12% to 15% of the game (25.1% of discrete cuts, used for post-basket reactions and free-throw shooters); "
            "Slow-Motion Replays (REPLAY-A / CAM-5) account for ~10% to 12% during whistles and timeouts; "
            "CAM-4 (Coach/Bench Iso) accounts for ~5% to 7% (8.1% of cuts during timeouts and substitutions); "
            "CAM-2 (Baseline Low) accounts for ~4% to 6% (8.6% of cuts after paint finishes); "
            "and CAM-5 (Above-Rim) accounts for ~1% to 2%."
        ),
        "timing_and_override": (
            "Full-game mix: CAM-1 Wide (~68-74%), CAM-3 Hero Iso (~12-15%), Replays (~10-12%), CAM-4 Bench (~5-7%), CAM-2 Baseline (~4-6%), CAM-5 Above-Rim (~1-2%)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="00:18",
                timestamp_seconds=18,
                game_clock="19:46",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Opening half-court possessions in the Crown Championship (Act 1 establishment phase).",
                human_editor_cut="Held CAM-1 (Main Wide) continuously across the opening tip and first half-court sets (~68-74% full-game share) to establish court geometry.",
                why_this_clip_explains_it="Demonstrates the macro STORY-01 rule where CAM-1 Wide anchors over two-thirds of the entire broadcast.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="03:42",
                timestamp_seconds=222,
                game_clock="16:18",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Oklahoma guard drains a top-of-the-key 3-pointer during standard half-court flow.",
                human_editor_cut="Switched from CAM-1 Wide (~70% game share) to CAM-3 Hero Iso (~12-15% game share) for a brief celebration (example: 2.2s), then returned to CAM-1.",
                why_this_clip_explains_it="Shows the core CAM-1 Wide to CAM-3 Hero Iso rhythm that drives most live broadcast cuts.",
            ),
        ],
    },
    {
        "keywords": ["storytelling", "storyline", "macro", "overall game", "three-act", "hot hand", "narrative", "across the game"],
        "primary_agent": "orchestrator",
        "matched_rule_code": "STORY-02 / STORY-03",
        "matched_rule_title": "Three-Act Broadcast Tempo & Player Storyline Continuity (Macro Storytelling)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 54,
        "what_agent_should_do": (
            "At the macro game-storytelling level, the Orchestrator and Director modulate pacing across three acts: "
            "Act 1 (Opening 5 minutes) holds CAM-1 Wide longer to establish court spacing and starter storylines; "
            "Act 2 (Mid-game) tracks hot-hand scorers and foul-trouble storylines across possessions (checking in with CAM-3/CAM-4 and stat progression banners on dead balls every ~4 to 6 game minutes, and rolling 2-to-3 clip Option B replay packages at media timeouts); "
            "and Act 3 (Final 5:00 in close games) locks CAM-1 on live play while compressing emotional close-ups and replays strictly into dead-ball windows."
        ),
        "timing_and_override": (
            "Three-act tempo shift (~8 cuts/min in opening establishment -> ~12 cuts/min during mid-game runs -> live CAM-1 lock in crunch time); "
            "revisit active star/foul storylines every ~4 to 6 game minutes on dead balls."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="00:18",
                timestamp_seconds=18,
                game_clock="19:46",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Act 1 Opening Tip-Off & Matchup Establishment in Las Vegas (19:46 1ST).",
                human_editor_cut="Held wide CAM-1 framing across the opening possessions while introducing the championship storyline banner.",
                why_this_clip_explains_it="Illustrates Act 1 establishment pacing where spatial orientation takes priority over rapid close-up cuts.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="43:30",
                timestamp_seconds=2610,
                game_clock="05:10",
                period="2ND",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Act 2/3 Momentum Climax: West Virginia ties the game 67-67 at 05:10 2ND, forcing an Oklahoma timeout.",
                human_editor_cut="Paired CAM-3 Scorer Hero Iso with CAM-4 Opposing Coach Huddle Iso and a scoring-run graphic entering the timeout.",
                why_this_clip_explains_it="Shows how multi-possession scoring runs culminate in a coordinated scorer-to-coach storytelling sequence.",
            ),
        ],
    },
    {
        "keywords": ["synchronize camera cuts", "commentator", "announcer", "analyst sentence", "crowd roar", "decibel", "sideline reporter"],
        "primary_agent": "director",
        "matched_rule_code": "AUD-01",
        "matched_rule_title": "Audio-Driven & Commentator-Synchronized Switching (AUD-01 to AUD-06)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.97,
        "observed_count": 168,
        "what_agent_should_do": (
            "Synchronize camera cuts and replay durations with broadcast audio across three signals: "
            "(1) Commentator Look-At Follow (AUD-01): When an announcer calls out a specific player, tired expression, or coach reaction during a dead ball or slow walk-up, "
            "cut to CAM-3 (Player Close-Up) or CAM-4 (Coach/Bench) within a brief beat (example: 1.0s lag, 3.5s hold) so the picture proves what the announcer is saying. "
            "(2) Replay Sentence Completion (AUD-02): Never cut out of a slow-motion replay in the middle of the analyst's sentence if the ball is still dead; slow-ramp or pause at the contact frame until they finish explaining. "
            "(3) Crowd Decibel Extension (AUD-03): On a massive home-crowd roar spike (example: +10 dB), let the CAM-3/CAM-4 celebration breathe slightly longer (example: 2.8s vs. 1.5s) unless the opponent pushes a fast break."
        ),
        "timing_and_override": (
            "Match visual cuts within ~1.0s of commentator callouts; extend replay holds until analyst sentence completion as long as >=1.5s remains before live play."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="06:04",
                timestamp_seconds=364,
                game_clock="14:52",
                period="1ST",
                camera_angle="CAM-4 (Coach / Bench Iso)",
                court_trigger="Commentator discusses coach strategy and huddle adjustments entering the Under-16 timeout (14:52 1ST).",
                human_editor_cut="Followed the announcer's commentary by cutting to CAM-4 (Coach/Bench Huddle) and pairing the audio breakdown with the coach clip.",
                why_this_clip_explains_it="Demonstrates AUD-01 and AUD-06: camera selection directly follows the commentator's spoken focus during a stoppage.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="05:12",
                timestamp_seconds=312,
                game_clock="15:44",
                period="1ST",
                camera_angle="REPLAY-A (Hi-Mo Replay)",
                court_trigger="Analyst breaks down the contact on an Oklahoma baseline drive and shooting foul.",
                human_editor_cut="Held and slow-ramped the CAM-5 Above-Rim replay through the end of the analyst's explanation before returning to CAM-1 for free throws.",
                why_this_clip_explains_it="Demonstrates AUD-02: the replay exit is timed to the completion of the analyst's spoken breakdown rather than cutting mid-sentence.",
            ),
        ],
    },
    {
        "keywords": ["whip-pan", "whip pan", "blurry", "stability gate", "lead room", "zoom corridor"],
        "primary_agent": "director",
        "matched_rule_code": "CAM-01",
        "matched_rule_title": "Camera Motion, Framing & Pre-Cut Stability Gate (CAM-01 to CAM-06)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 420,
        "what_agent_should_do": (
            "Enforce intra-shot camera quality before and during every cut: "
            "(1) Pre-Cut Stability Gate (CAM-01): Never switch Program to an isolation camera (CAM-2, CAM-3, CAM-4) while it is still whip-panning, zooming rapidly, or hunting for focus; require a settled, centered frame first (example: 0.3s to 0.5s of stable framing). "
            "(2) Fast-Break Lead Room (CAM-02): On CAM-1 fast breaks, pan slightly ahead of the dribbler so ~65% of the screen shows the open court and defenders ahead of the ball. "
            "(3) Half-Court Zoom Corridor (CAM-03): Keep all 10 players and both baseline corners visible on CAM-1 during perimeter passing, and zoom out smoothly as the final free throw is released (CAM-04)."
        ),
        "timing_and_override": (
            "Require stable pre-cut framing (example: 0.3s to 0.5s low pan velocity) and clean face/headroom on CAM-3 before switching to Program."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="03:42",
                timestamp_seconds=222,
                game_clock="16:18",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Oklahoma guard makes a 3-pointer; CAM-3 operator locks onto the shooter's torso and face before the cut.",
                human_editor_cut="Waited until the ball cleared the net and CAM-3 was locked and steady on the shooter before punching CAM-3 to Program.",
                why_this_clip_explains_it="Shows CAM-01 and CAM-05: the technical director waits until CAM-3 is settled with clean headroom so the viewer never sees a whip-pan.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="08:50",
                timestamp_seconds=530,
                game_clock="12:40",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Oklahoma pushes a high-speed fast break across mid-court.",
                human_editor_cut="CAM-1 leads the ball-handler with ~65% of the frame open toward the attacking basket.",
                why_this_clip_explains_it="Demonstrates CAM-02 forward lead-room framing so viewers can see passing lanes and transition defenders ahead of the ball.",
            ),
        ],
    },
    {
        "keywords": ["180-degree", "180 degree", "court line", "ping-pong", "ping pong", "eye-trace", "spatial continuity"],
        "primary_agent": "director",
        "matched_rule_code": "CNT-01",
        "matched_rule_title": "Spatial Continuity, 180-Degree Court Line & Anti-Flicker Floor (CNT-01 to CNT-05)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 720,
        "what_agent_should_do": (
            "Prevent viewer spatial disorientation across cuts: "
            "(1) 180-Degree Court Line (CNT-01): Keep all live-action cameras (CAM-1, CAM-2, CAM-3) on the same side of the court so a team attacking left-to-right never suddenly appears to run right-to-left after a cut. "
            "(2) Minimum Shot-Hold Floor (CNT-02): Never ping-pong across three cameras in under two seconds; enforce a minimum dwell floor (example: 1.2s to 1.5s) outside of emergency fast-break bailouts. "
            "(3) Net-Splash Eye-Trace Beat (CNT-03): Because viewers watch the rim during a shot, wait a brief beat after the ball splashes through the net (example: 0.3s to 0.5s) before cutting to CAM-3 Close-Up."
        ),
        "timing_and_override": (
            "100% same-side axis preservation during live dribbling; minimum camera hold floor (example: 1.2s to 1.5s) and post-splash beat (example: 0.4s)."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="00:18",
                timestamp_seconds=18,
                game_clock="19:46",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Opening tip-off and continuous left-to-right offensive transition.",
                human_editor_cut="Maintained same-side 180-degree court axis across CAM-1 and sideline cuts so team attack directions stayed consistent.",
                why_this_clip_explains_it="Demonstrates CNT-01: preserving the 180-degree line keeps left-to-right court geography intuitive for casual viewers.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="11:15",
                timestamp_seconds=675,
                game_clock="10:08",
                period="1ST",
                camera_angle="CAM-3 (Hero Player Iso)",
                court_trigger="Made 3-pointer at the peak of a scoring run.",
                human_editor_cut="Held CAM-1 for ~0.4s after the ball splashed through the net before punching to CAM-3 Shooter Close-Up.",
                why_this_clip_explains_it="Demonstrates CNT-03 eye-trace timing: letting the viewer see the net splash before switching to the shooter's celebration.",
            ),
        ],
    },
    {
        "keywords": ["4 agents collide", "agents collide", "priority arbitration", "graphic ttl", "and-one", "and one"],
        "primary_agent": "orchestrator",
        "matched_rule_code": "ARB-01",
        "matched_rule_title": "Multi-Agent Priority Arbitration, Preemption & TTL Expiration (ARB-01 to ARB-06)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.99,
        "observed_count": 540,
        "what_agent_should_do": (
            "When multiple agents compete for the screen at the same second, the Orchestrator resolves conflicts using a strict 5-tier ladder (ARB-01): "
            "(1) Live Ball in Play / Court Safety Lock (CAM-1) > (2) Referee Foul/Violation Hand Signal > (3) Live Player/Coach Reaction (CAM-3/CAM-4) > (4) Slow-Motion Replay (REPLAY-A) > (5) Lower-Third Stat Banner (GFX). "
            "On an 'And-One' basket-plus-foul (ARB-04), sequence a 4-step relay: CAM-3 Celebration (example: 2.5s) -> Slow-Mo Replay with scoreboard hidden (example: 5.0s) -> CAM-1 Free-Throw Setup with scoreboard restored -> Shooter Free-Throw % Banner. "
            "Additionally, attach a 1-possession Time-To-Live (ARB-03) to queued momentum graphics so stale stats are purged if the other team scores first."
        ),
        "timing_and_override": (
            "Higher priority tiers preempt lower tiers within 0.2s; expire queued momentum graphics after 1 possession if game context changes."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="05:12",
                timestamp_seconds=312,
                game_clock="15:44",
                period="1ST",
                camera_angle="CAM-5 (Above Rim)",
                court_trigger="Contested baseline drive with basket and foul whistle where Director, Replay, and Graphics all trigger simultaneously.",
                human_editor_cut="Sequenced CAM-3 scorer reaction -> CAM-5 slow-mo replay (Scorebug hidden) -> CAM-1 free-throw setup (Scorebug restored) + shooter FT banner.",
                why_this_clip_explains_it="Shows ARB-01 and ARB-04: clean 4-stage relay choreography instead of overlapping cuts and banners.",
            ),
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="29:12",
                timestamp_seconds=1752,
                game_clock="14:40",
                period="2ND",
                camera_angle="CAM-4 (Coach / Bench Iso)",
                court_trigger="4th personal foul on starter triggers reaction, replay, and foul-trouble graphic requests at once.",
                human_editor_cut="Showed referee signal -> player/coach reaction on CAM-4 -> slow-mo foul replay -> 4-foul trouble banner on substitution walk-off.",
                why_this_clip_explains_it="Demonstrates multi-agent priority ordering during high-stakes foul stoppages.",
            ),
        ],
    },
    {
        "keywords": ["covering the ball", "cover the ball", "near sideline", "stacking over the scoreboard", "mutual exclusion"],
        "primary_agent": "graphics_scorebug",
        "matched_rule_code": "LYT-01",
        "matched_rule_title": "Spatial Screen-Real-Estate & Graphic Collision Avoidance (LYT-01 to LYT-05)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 280,
        "what_agent_should_do": (
            "Prevent graphics from colliding with live basketball action or with each other: "
            "(1) Near-Sideline Ball Occlusion Check (LYT-01): Track the ball and dribbler bounding box on CAM-1; if they enter the bottom 25% of the screen where a lower-third banner sits, immediately hide or delay the banner so it never covers the live ball. "
            "(2) Overlay Mutual Exclusion (LYT-02): Never display a full lower-third player banner at the same time as an expanded broadcast scorebug drawer. "
            "(3) Under-30s Shot-Clock Hide (LYT-04): Automatically hide the shot-clock box when less than 30 seconds remain in the half or game and the shot clock is turned off. "
            "(4) Net-Splash Score Sync (LYT-05): Increment scoreboard points (+2/+3) ~0.3s to 0.8s after the ball visibly clears the net."
        ),
        "timing_and_override": (
            "Dismiss lower-thirds within 0.2s if the ball enters the bottom 25% frame zone; 100% mutual exclusion between expanded Scorebug drawers and lower-thirds."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="28:10",
                timestamp_seconds=1690,
                game_clock="15:35",
                period="2ND",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Lower-third stat comparison aired during dead-ball substitution and cleared before bottom-sideline throw-in.",
                human_editor_cut="Cleared the lower-third banner before the guard dribbled into the near-sideline corridor at the bottom of CAM-1.",
                why_this_clip_explains_it="Demonstrates LYT-01 and LYT-02: keeping the bottom court corridor and scoreboard free of overlapping graphics during live dribbling.",
            ),
        ],
    },
    {
        "keywords": ["3-step sequence", "commercial break", "returning from a break", "going into a commercial", "outbound sequence"],
        "primary_agent": "orchestrator",
        "matched_rule_code": "BRK-01",
        "matched_rule_title": "Commercial Break Outbound Teases, Re-Entry & Halftime Structure (BRK-01 to BRK-05)",
        "rule_category": "LEARNED_HEURISTIC",
        "confidence": 0.98,
        "observed_count": 216,
        "what_agent_should_do": (
            "Manage show structure around commercial breaks and intermissions: "
            "(1) Going-to-Break 3-Step Outbound Sequence (BRK-01): Over the 6s to 8s before commercials, cut to CAM-3/CAM-4 player/bench huddle -> roll the best slow-motion highlight from the segment -> display the full-screen score bumper card with music. "
            "(2) Returning-from-Break Re-Orientation (BRK-02): Open on a wide arena or huddle shot, restore the scoreboard immediately, and flash a plain-English 'What Happened During the Break' banner if any free throws or reviews occurred before cutting to CAM-1 at least 3s before the throw-in. "
            "(3) Halftime & Cold Open (BRK-03 / BRK-04): Show Starting Lineups and 2-bullet Keys to the Game at least 5s before the opening tip, and reset team fouls to 0 at halftime."
        ),
        "timing_and_override": (
            "6s to 8s 3-step outbound bumper entering breaks; return to CAM-1 Wide >=3.0s before post-break throw-in."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="06:04",
                timestamp_seconds=364,
                game_clock="14:52",
                period="1ST",
                camera_angle="REPLAY-A (Hi-Mo Replay)",
                court_trigger="Under-16 Media Timeout commercial transition at 14:52 1ST Half.",
                human_editor_cut="Cut to bench huddle reaction -> rolled slow-mo highlight package -> displayed full-screen score bumper into commercial break.",
                why_this_clip_explains_it="Demonstrates BRK-01: the classic 3-step outbound tease sequence entering a scheduled television timeout.",
            ),
        ],
    },
    {
        "keywords": ["whistle is ambiguous", "ball-tracking confidence", "fan blocks the lens", "reliability fallbacks"],
        "primary_agent": "orchestrator",
        "matched_rule_code": "REL-01",
        "matched_rule_title": "Ambiguity, Degraded-Confidence & Reliability Fallbacks (REL-01 to REL-05)",
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "confidence": 0.99,
        "observed_count": 265,
        "what_agent_should_do": (
            "Guarantee broadcast reliability when signals or calls are uncertain: "
            "(1) Ambiguous Whistle Hold (REL-01): For the first 1.0s to 2.0s after a crowded whistle when the call is unclear (foul vs. travel vs. jump ball), hold a medium-wide CAM-1/CAM-4 view showing both the players and the referee until the hand signal confirms the call. "
            "(2) Live-Camera Occlusion Auto-Eject (REL-02): If a standing fan or referee walks directly in front of live CAM-2 or CAM-3, bail out to CAM-1 Wide within a sub-second beat (example: 0.4s to 0.6s). "
            "(3) Low Ball-Tracking Confidence Fallback (REL-03): If floor scrambles drop ball-tracker confidence below ~65%, freeze close-up cuts and lock onto wide CAM-1. "
            "(4) Backcourt Steal Instant Bailout (REL-05): If a defender steals an inbound pass while CAM-3/CAM-4 or a replay is on air, hard-cut to CAM-1 in <0.4s."
        ),
        "timing_and_override": (
            "Hold medium-wide framing for 1s to 2s on ambiguous whistles; sub-second (<0.4s to 0.6s) bailout to CAM-1 Wide on lens occlusion, tracker loss, or surprise backcourt steals."
        ),
        "clips": [
            _make_clip(
                video_id="yt-crown-T_uLlzfDCjI",
                yt_id="T_uLlzfDCjI",
                broadcast_title="College Basketball Crown Championship: Oklahoma vs West Virginia",
                timestamp_mmss="01:05",
                timestamp_seconds=65,
                game_clock="18:55",
                period="1ST",
                camera_angle="CAM-1 (Main Wide)",
                court_trigger="Full-court trap and loose-ball deflection in the backcourt right after an inbound pass.",
                human_editor_cut="Stayed locked on wide CAM-1 throughout the trap and scramble rather than risking a close-up cut.",
                why_this_clip_explains_it="Demonstrates REL-03 and REL-05: keeping wide CAM-1 locked during unpredictable backcourt scrambles and steal attempts.",
            ),
        ],
    },
]


# Conversational synonym expansion so natural questions map to the exact technical & plain-English terms in our 346 rules
CONVERSATIONAL_EXPANSIONS: list[tuple[list[str], list[str]]] = [
    (
        ["cut in between", "in between", "cut short", "cut early", "interrupted", "interrupt", "mid-replay", "stop a replay", "abort"],
        ["mid-replay", "preemption", "speed-ramp", "bailout", "interrupt", "match-on-action", "sequential", "complementary", "ARB-02", "CNT-10", "RPL-08", "REL-05"],
    ),
    (
        ["two angles", "multiple angles", "different angles", "switch angles", "second angle"],
        ["complementary angles", "sequential camera angles", "match-on-action", "RPL-08", "CNT-10"],
    ),
    (
        ["foul out", "fouls out", "fouling out", "5 fouls", "5th foul", "disqualified", "ejected"],
        ["5th personal foul", "disqualified", "fouling out", "ORC-10"],
    ),
    (
        ["technical foul", "flagrant", "unsportsmanlike", "fight", "argument"],
        ["technical fouls", "unsportsmanlike", "flagrant", "ORC-11", "CUJ-1.4"],
    ),
    (
        ["challenge", "coach challenge", "video review", "official review", "monitor", "scorer's table"],
        ["coach challenge", "video reviews", "scorer's table", "ARB-08", "ORC-06", "BRK-18"],
    ),
    (
        ["buzzer", "buzzer beater", "end of quarter", "end of half", "horn", "0.0", "red light"],
        ["buzzer-beater", "red backboard light", "quarter expiration", "ARB-13", "RPL-07", "AUD-10"],
    ),
    (
        ["stepped out", "out of bounds", "sideline", "baseline line", "boundary"],
        ["out-of-bounds", "stepped on", "deflection", "RPL-11", "RPL-13"],
    ),
    (
        ["2 or 3", "2 or a 3", "two or three", "check if a shot", "toe on the line", "three point line", "foot on the line", "shoes", "toe on the arc"],
        ["2-pointer vs. 3-pointer", "toe-on-the-arc", "shooter's shoes", "RPL-07", "RPL-12"],
    ),
    (
        ["travel", "traveling", "walked", "pivot foot", "extra step", "double dribble"],
        ["traveling", "footwork", "pivot-foot", "RPL-14"],
    ),
    (
        ["free throw", "foul shot", "charity stripe", "lane violation"],
        ["free-throw", "free throws", "lane violation", "DIR-05", "ORC-21", "CAM-04", "ARB-04"],
    ),
    (
        ["overtime", "extra period", "tied at the end"],
        ["overtime", "reset structure", "BRK-11"],
    ),
    (
        ["halftime", "half time", "intermission", "locker room"],
        ["halftime", "BRK-03", "BRK-04"],
    ),
    (
        ["split screen", "picture in picture", "pip", "two boxes", "side by side"],
        ["split-screen", "pip", "split-box", "CNT-20", "LYT-08", "RPL-28"],
    ),
    (
        ["telestrator", "draw on screen", "drawing", "yellow lines"],
        ["telestrator", "drawing", "LYT-15", "ARB-22"],
    ),
    (
        ["celebrity", "vip", "mascot", "crowd", "fans", "student section"],
        ["celebrity", "vip", "mascot", "crowd", "ARB-21", "BRK-17", "AUD-03"],
    ),
    (
        ["scorebug", "scoreboard", "broadcast box", "score banner", "bottom bar"],
        ["scoreboard", "broadcast box", "lower-third", "LYT-01", "LYT-02", "RPL-05"],
    ),
]

STOP_WORDS = {
    "what", "when", "where", "which", "who", "whom", "whose", "why", "how",
    "are", "is", "do", "does", "did", "can", "could", "should", "would", "will",
    "the", "and", "for", "that", "this", "with", "from", "into", "onto", "upon",
    "about", "have", "has", "had", "been", "being", "were", "was", "there", "their",
    "they", "them", "then", "than", "also", "ever", "any", "all", "some", "such",
    "rule", "rules", "agent", "agents", "game", "games", "basketball", "broadcast",
    "happen", "happens", "happened", "make", "made", "take", "taken", "give", "given",
}


def _tokenize(text: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())
    return [t for t in raw if len(t) >= 2 and t not in STOP_WORDS]


def _stem(word: str) -> str:
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("es"):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _score_scenario_entry(q_lower: str, entry: dict[str, Any]) -> int:
    score = 0
    for kw in entry["keywords"]:
        if kw in q_lower:
            if kw.startswith("camera ") or kw.startswith("cam ") or kw.startswith("cam-"):
                score += 14
            elif len(kw.split()) >= 3:
                score += 14
            elif len(kw.split()) == 2:
                score += 9
            else:
                score += 4
    return score


def _rank_kb_rules(question: str, all_rules: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    """Rank all 346 rules in courtvision.db using BM25/IDF token weighting, phrase matching, and synonym expansion."""
    q_lower = question.lower().strip()
    q_tokens = _tokenize(q_lower)
    q_stems = [_stem(t) for t in q_tokens]

    # Build bigrams from the user's question
    q_bigrams = [f"{q_tokens[i]} {q_tokens[i+1]}" for i in range(len(q_tokens) - 1)]

    # Check conversational expansions
    expanded_phrases: list[str] = []
    boosted_codes: set[str] = set()
    for triggers, targets in CONVERSATIONAL_EXPANSIONS:
        if any(trig in q_lower for trig in triggers):
            for tgt in targets:
                if re.match(r"^[A-Z]{3}-\d+$", tgt):
                    boosted_codes.add(tgt.lower())
                else:
                    expanded_phrases.append(tgt.lower())

    # Prepare clean rule documents (stripping [Plain-English Guide: ...] so boilerplate glossary words don't skew IDF)
    docs: list[tuple[dict[str, Any], str, str, set[str]]] = []
    df_counts: dict[str, int] = {}
    n_docs = max(1, len(all_rules))

    for r in all_rules:
        core_trigger, _ = _split_plain_guide(r.get("trigger_condition", ""))
        title_lower = r.get("title", "").lower()
        code_lower = r.get("rule_code", "").lower()
        body_lower = f"{code_lower} {title_lower} {core_trigger.lower()} {r.get('editor_action', '').lower()} {r.get('timing_constraint', '').lower()}"
        doc_stems = {_stem(t) for t in _tokenize(body_lower)}
        for st in doc_stems:
            df_counts[st] = df_counts.get(st, 0) + 1
        docs.append((r, title_lower, body_lower, doc_stems))

    scored: list[tuple[float, dict[str, Any]]] = []
    for r, title_lower, body_lower, doc_stems in docs:
        score = 0.0
        code_lower = r.get("rule_code", "").lower()

        # Exact rule code mention (e.g., "ARB-02" or "RPL-08")
        if code_lower in q_lower:
            score += 40.0
        if code_lower in boosted_codes:
            score += 22.0

        # IDF-weighted token & stem matching
        for tok, st in zip(q_tokens, q_stems):
            idf = math.log(1.0 + (n_docs / (1.0 + df_counts.get(st, 0))))
            if tok in title_lower or st in title_lower:
                score += 3.2 * idf
            if st in doc_stems or tok in body_lower:
                score += 1.6 * idf

        # Bigram phrase bonus
        for bg in q_bigrams:
            if bg in title_lower:
                score += 9.0
            elif bg in body_lower:
                score += 5.0

        # Conversational expansion bonus
        for phrase in expanded_phrases:
            if phrase in title_lower:
                score += 8.5
            elif phrase in body_lower:
                score += 4.5

        if score > 0:
            scored.append((score, r))

    scored.sort(key=lambda x: (x[0], float(x[1].get("confidence", 0.9))), reverse=True)
    return scored


def _find_matching_youtube_clips(
    question: str,
    top_rules: list[dict[str, Any]],
    fallback_clips: list[YouTubeClipExample],
) -> list[YouTubeClipExample]:
    """Query the 596 real broadcast timeline events in courtvision.db to return the best-matching YouTube clips."""
    try:
        q_tokens = set(_tokenize(question))
        for r in top_rules[:2]:
            q_tokens.update(_tokenize(r.get("title", "")))
        q_stems = {_stem(t) for t in q_tokens}
        preferred_agent = top_rules[0].get("agent_role", "") if top_rules else ""

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT e.*, v.title AS broadcast_title, v.source_uri
            FROM timeline_events e
            JOIN videos v ON e.video_id = v.id
            WHERE v.source_uri LIKE '%youtube.com/watch?v=%'
            """
        ).fetchall()
        conn.close()

        scored_events: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            ev_text = f"{row['game_action_trigger']} {row['editor_decision']} {row['editor_rationale']} {row['camera_angle']}".lower()
            ev_stems = {_stem(t) for t in _tokenize(ev_text)}
            overlap = len(q_stems & ev_stems)
            if overlap == 0:
                continue
            ev_score = float(overlap) * 2.5
            if preferred_agent and row["agent_domain"] == preferred_agent:
                ev_score += 3.0
            # Prefer our primary verified championship broadcast when scores tie
            if row["video_id"] == "yt-crown-T_uLlzfDCjI":
                ev_score += 1.5
            scored_events.append((ev_score, row))

        scored_events.sort(key=lambda x: x[0], reverse=True)

        clips: list[YouTubeClipExample] = []
        seen_keys: set[tuple[str, str]] = set()
        for _, row in scored_events:
            key = (row["video_id"], row["timestamp_mmss"])
            if key in seen_keys:
                continue
            seen_keys.add(key)
            uri = row["source_uri"]
            yt_id = uri.split("v=")[-1].split("&")[0] if "v=" in uri else "T_uLlzfDCjI"
            scorebug = {}
            try:
                scorebug = json.loads(row["scorebug_json"] or "{}")
            except Exception:
                scorebug = {}
            clips.append(
                _make_clip(
                    video_id=row["video_id"],
                    yt_id=yt_id,
                    broadcast_title=row["broadcast_title"],
                    timestamp_mmss=row["timestamp_mmss"],
                    timestamp_seconds=int(row["timestamp_seconds"]),
                    game_clock=str(scorebug.get("game_clock", "12:00")),
                    period=str(scorebug.get("period", "1ST")),
                    camera_angle=row["camera_angle"],
                    court_trigger=row["game_action_trigger"],
                    human_editor_cut=row["editor_decision"],
                    why_this_clip_explains_it=row["editor_rationale"],
                )
            )
            if len(clips) >= 3:
                break

        if clips:
            return clips
    except Exception as exc:
        logger.warning("Dynamic clip search fallback: %s", type(exc).__name__)

    return fallback_clips


def _synthesize_direct_kb_answer(question: str, ranked_rules: list[tuple[float, dict[str, Any]]]) -> dict[str, Any]:
    """Synthesize a direct, conversational, multi-rule engineering answer from the top matched rules in the 346-rule KB."""
    top_rules = [r for _, r in ranked_rules[:3]]
    primary = top_rules[0]
    p_trigger, p_guide = _split_plain_guide(primary.get("trigger_condition", ""))

    q_clean = question.strip()
    q_lower = q_clean.lower()

    # Craft a direct opening line that directly answers the user's question framing
    is_yes_no = bool(re.match(r"^(are|is|do|does|can|should|will|would|could)\b", q_lower))
    codes_str = " / ".join(r["rule_code"] for r in top_rules)

    lines: list[str] = []
    if is_yes_no:
        lines.append(
            f"Direct Answer ({codes_str}): Yes, under specific broadcast conditions governed by {primary['rule_code']} ({primary['title']}) and related control-room rules:"
        )
    else:
        lines.append(
            f"Direct Answer ({codes_str}): Governed primarily by {primary['rule_code']} ({primary['title']}) alongside {len(top_rules) - 1} related broadcast rules:"
        )

    for idx, r in enumerate(top_rules, start=1):
        core_trig, _ = _split_plain_guide(r.get("trigger_condition", ""))
        action_text = r.get("editor_action", "").strip()
        lines.append(
            f"\n{idx}. {r['rule_code']} - {r['title']}:\n"
            f"• When It Applies: {core_trig}\n"
            f"• What the Agent Does: {action_text}"
        )

    if p_guide:
        lines.append(f"\nPlain-English Basketball Note: {p_guide}")

    timing_parts = [f"{r['rule_code']}: {r.get('timing_constraint', '').strip()}" for r in top_rules if r.get("timing_constraint")]
    timing_combined = " | ".join(timing_parts)

    avg_conf = sum(float(r.get("confidence", 0.95)) for r in top_rules) / len(top_rules)
    total_obs = sum(int(r.get("observed_count", 25)) for r in top_rules)

    if len(top_rules) > 1:
        combined_title = f"{primary['title']} (+ {len(top_rules) - 1} Related Rules)"
    else:
        combined_title = primary["title"]

    return {
        "primary_agent": primary.get("agent_role", "director"),
        "matched_rule_code": codes_str,
        "matched_rule_title": combined_title,
        "rule_category": primary.get("category", "LEARNED_HEURISTIC"),
        "confidence": round(avg_conf, 2),
        "observed_count": total_obs,
        "what_agent_should_do": "\n".join(lines),
        "timing_and_override": timing_combined,
        "top_rules": top_rules,
    }


def answer_engineer_question(question: str) -> AgentChatAnswerResponse:
    """Match an engineer's question to the best agent rules across all 346 KB rules, telemetry stats, and YouTube clip evidence."""
    q_lower = question.lower().strip()

    # 1. Score curated multi-rule scenario entries
    best_scenario = SCENARIO_KNOWLEDGE_GRAPH[0]
    best_scenario_score = 0
    for entry in SCENARIO_KNOWLEDGE_GRAPH:
        s_score = _score_scenario_entry(q_lower, entry)
        if s_score > best_scenario_score:
            best_scenario_score = s_score
            best_scenario = entry

    # 2. Always rank all 346 rules in courtvision.db
    all_rules = list_editor_rules()
    ranked_rules = _rank_kb_rules(question, all_rules)
    top_kb_score = ranked_rules[0][0] if ranked_rules else 0.0

    # Decide whether a curated scenario entry explicitly matched a multi-word preset/intent,
    # or whether our 346-rule KB synthesis provides the more specific answer.
    use_curated = best_scenario_score >= 9

    if use_curated:
        what_to_do = best_scenario["what_agent_should_do"]
        timing_override = best_scenario["timing_and_override"]
        matched_code = best_scenario["matched_rule_code"]
        matched_title = best_scenario["matched_rule_title"]
        primary_agent = best_scenario["primary_agent"]
        rule_category = best_scenario["rule_category"]
        confidence = best_scenario["confidence"]
        observed_count = best_scenario["observed_count"]
        clips = best_scenario["clips"]
    elif ranked_rules:
        synth = _synthesize_direct_kb_answer(question, ranked_rules)
        what_to_do = synth["what_agent_should_do"]
        timing_override = synth["timing_and_override"]
        matched_code = synth["matched_rule_code"]
        matched_title = synth["matched_rule_title"]
        primary_agent = synth["primary_agent"]
        rule_category = synth["rule_category"]
        confidence = synth["confidence"]
        observed_count = synth["observed_count"]
        clips = _find_matching_youtube_clips(question, synth["top_rules"], SCENARIO_KNOWLEDGE_GRAPH[0]["clips"])
    else:
        what_to_do = best_scenario["what_agent_should_do"]
        timing_override = best_scenario["timing_and_override"]
        matched_code = best_scenario["matched_rule_code"]
        matched_title = best_scenario["matched_rule_title"]
        primary_agent = best_scenario["primary_agent"]
        rule_category = best_scenario["rule_category"]
        confidence = best_scenario["confidence"]
        observed_count = best_scenario["observed_count"]
        clips = best_scenario["clips"]

    # Optional Gemini refinement for custom free-form questions when GEMINI_API_KEY is configured
    api_key = get_gemini_api_key()
    if api_key and not use_curated:
        try:
            client = genai.Client(api_key=api_key)
            top_context_rules = [r for _, r in ranked_rules[:12]] if ranked_rules else all_rules[:12]
            rules_summary = "\n".join(
                f"- {r['rule_code']} ({r['agent_role']}): {r['title']} | Trigger: {_split_plain_guide(r['trigger_condition'])[0]} | Action: {r['editor_action']} | Timing: {r['timing_constraint']}"
                for r in top_context_rules
            )
            prompt = (
                f"You are the Lead Broadcast Engineering Advisor for CourtVision AI (Project Stark).\n"
                f"A user asked: {question}\n\n"
                f"Synthesized knowledge-base answer:\n{what_to_do}\n\n"
                f"Top matching Editor Knowledge Base rules:\n{rules_summary}\n\n"
                f"Directly and clearly answer the user's question in plain English so even someone unfamiliar with basketball can follow along. "
                f"Cite the relevant rule codes (e.g. ARB-02, CNT-10) and include concrete timing examples in parentheses like (example: 0.7s). "
                f"Do not use em-dashes or markdown backticks."
            )
            resp = client.models.generate_content(
                model=DEFAULT_GEMINI_VIDEO_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.15),
            )
            if resp.text and len(resp.text.strip()) > 20:
                what_to_do = resp.text.strip().replace("—", "-").replace("`", "")
        except Exception as exc:
            logger.warning("Gemini advisor fallback to deterministic KB: %s", type(exc).__name__)

    return AgentChatAnswerResponse(
        question=question,
        primary_agent=primary_agent,
        what_agent_should_do=what_to_do,
        timing_and_override=timing_override,
        matched_rule_code=matched_code,
        matched_rule_title=matched_title,
        rule_category=rule_category,
        confidence=confidence,
        observed_count=observed_count,
        youtube_examples=clips,
    )
