"""Project Stark PRD (go/project-stark-prd) & Feature Backlog Reference + Shadow Mode Continuous Learning Engine."""

from __future__ import annotations

from typing import Any

PROJECT_STARK_METADATA: dict[str, Any] = {
    "doc_id": "go/project-stark-prd",
    "title": "Project Stark: Autonomous Live Sports Production (Showmaker + AI Agent)",
    "authors": ["Sandhya Patil", "Broadcast Production Leads"],
    "collaborators": [
        "Rob Keohane",
        "Peter Blum",
        "Kunal Kumar Gupta",
        "Vivian Kim",
    ],
    "version": "V1 (Approved Oct 28, 2026) / V2 (Takeover Control, Voice Commands & Continuous Skill Learning)",
    "paradigm_shift": (
        "Shifts live sports production from 10+ manual operators to a strict Two-Role Model: "
        "one human Showmaker (combining Producer + Director) partnered with an autonomous AI Agent "
        "(handling Technical Director switching, Replay scrubbing, Researcher stats, and Scorebug/Graphics)."
    ),
    "architectural_thesis": {
        "why_manual_if_else_fails": (
            "Live basketball has a continuous, high-dimensional state space (clock, score margin, foul trouble, "
            "camera occlusion, player momentum, pause duration). A single PM cannot manually document every "
            "permutation via interview notes or static if-else spreadsheets."
        ),
        "hybrid_solution": (
            "Combine a thin layer of Constitutional Safety Guardrails (from Project Stark PRD: e.g., Camera 1 "
            "Emergency Takeover, Hide Scorebug on Replays, Read-Twice Graphic Rule, Sustained Glitch Failover) "
            "with Observational Apprenticeship & Shadow Mode Continuous Learning where the agent watches real "
            "broadcasts, diffs its predicted cuts against veteran human directors, and autonomously evolves its SKILL.md rules."
        ),
    },
}

PROJECT_STARK_BACKLOG: list[dict[str, Any]] = [
    {
        "id": "CUJ-1.1",
        "phase": "MVP",
        "cuj": "CUJ 1: Live Camera Switching",
        "feature": "Default Camera 1 & Sustained Glitch Failover",
        "manual_rule_from_prd": (
            "Keep Camera 1 on air during normal play. Do not switch for a single dropped frame; fail over "
            "to Camera 2 only on sustained glitches ('taking hits') and alert Showmaker to widen Camera 2."
        ),
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "agent_owner": "director",
        "continuous_learning_upgrade": (
            "Agent learns visual signal-degradation thresholds and camera clarity rankings across venues automatically."
        ),
    },
    {
        "id": "CUJ-1.2",
        "phase": "MVP",
        "cuj": "CUJ 1: Live Camera Switching",
        "feature": "Simultaneous Whistle / Score / Pause Detection",
        "manual_rule_from_prd": (
            "Detect scores, foul whistles, and out-of-bounds stops in real time; track remaining pause timer "
            "and trigger reaction cut, replay capture, and Scorebug update simultaneously."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "orchestrator",
        "continuous_learning_upgrade": (
            "Instead of hardcoded pause timers, the agent learns empirical pause-duration distributions "
            "(shooting foul vs. non-shooting out-of-bounds vs. full-court press inbound) from game footage."
        ),
    },
    {
        "id": "CUJ-1.3",
        "phase": "MVP",
        "cuj": "CUJ 1: Live Camera Switching",
        "feature": "99% Autonomous PGM Cuts & Anti-Repetition History",
        "manual_rule_from_prd": (
            "Execute 99% of live cuts directly to Program (PGM) with no Preview/Take loop. Use camera clarity "
            "rankings and cut history to pick the best unobstructed reaction angle without repeating the last angle, "
            "and return to Camera 1 before the throw-in."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "director",
        "continuous_learning_upgrade": (
            "Learns shot-hold cadences, when to prefer sideline vs. baseline hero angles, and exact anticipation "
            "timing before referee hand-off on throw-ins by watching veteran directors."
        ),
    },
    {
        "id": "CUJ-1.4",
        "phase": "MVP",
        "cuj": "CUJ 1: Live Camera Switching",
        "feature": "One-Button Camera 1 Takeover & Resume",
        "manual_rule_from_prd": (
            "On court emergencies (severe injury/fight) or AI 'rabbit hole' cutting, Showmaker clicks Takeover "
            "to lock broadcast to Camera 1 and block all replays. Resume hands switching back on the next throw-in."
        ),
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "agent_owner": "orchestrator",
        "continuous_learning_upgrade": (
            "Every human Takeover event in live or Shadow Mode is logged as a high-priority negative training "
            "signal so the agent inspects the preceding 15s and patches its SKILL.md to prevent future rabbit holes."
        ),
    },
    {
        "id": "CUJ-7A",
        "phase": "MVP",
        "cuj": "CUJ 7A: Instant Replays",
        "feature": "Whistle Start-Point ('IN') Capture & Multi-Angle Stitch",
        "manual_rule_from_prd": (
            "Continuously pre-score camera feeds for visual clarity. On a whistle, mark the 'IN' point a few "
            "seconds back across top-scored cameras, stitch 2-3 clear angles to fit the pause, hide Scorebug during "
            "replay, and restore Scorebug + Camera 1 before play restarts."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "replay",
        "continuous_learning_upgrade": (
            "Learns play-specific lookback offsets (e.g. -4.5s for transition alley-oop vs. -2.2s for contested block) "
            "and optimal slow-mo ramp speeds (55%-70%) from historical replay packages."
        ),
    },
    {
        "id": "CUJ-7B",
        "phase": "MVP",
        "cuj": "CUJ 7B: Storytelling Packages",
        "feature": "Background Clip Scoring & Option A / Option B Packages",
        "manual_rule_from_prd": (
            "Pre-calculate clip clarity/impact scores in the background and pre-stitch top 2 package options "
            "(Option A and Option B: wide setup + 2-3 close-up action angles + closing reaction) for breaks."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "replay",
        "continuous_learning_upgrade": (
            "Learns which Option (A vs. B) the Showmaker selects across games (e.g., offensive 3-pt barrage vs. "
            "defensive steals + coach reaction) to rank future storytelling packages."
        ),
    },
    {
        "id": "CUJ-9",
        "phase": "MVP",
        "cuj": "CUJ 9: Scorebug Score Banner",
        "feature": "Arena Scoreboard Camera Sync & Automatic Replay Hiding",
        "manual_rule_from_prd": (
            "Reconcile game clock, shot timer, and scores 99% of the time via dedicated camera on the physical "
            "arena scoreboard. Pre-calculate foul/bonus/sponsor triggers. Hide Scorebug during replays/packages "
            "and restore on live Camera 1."
        ),
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "agent_owner": "graphics_scorebug",
        "continuous_learning_upgrade": (
            "Learns OCR clock-drift patterns and optimal post-replay banner sequencing (e.g. '3rd Foul' badge + sponsor logo)."
        ),
    },
    {
        "id": "CUJ-10",
        "phase": "MVP",
        "cuj": "CUJ 10: Story Graphics",
        "feature": "Pre-Play/Post-Play Stat Generation, Font 1 Preview & Read-Twice Rule",
        "manual_rule_from_prd": (
            "Pre-calculate Pre-Play vs. Post-Play and Instant vs. Package graphics. Route to Font 1 for safe preview. "
            "Enforce Read-Twice Rule: only air text graphics when the remaining pause is long enough to read all words twice."
        ),
        "rule_category": "CONSTITUTIONAL_GUARDRAIL",
        "agent_owner": "graphics_scorebug",
        "continuous_learning_upgrade": (
            "Learns word-count-to-pause-duration survival curves so graphics never get clipped by quick inbound throw-ins."
        ),
    },
    {
        "id": "CUJ-11",
        "phase": "MVP",
        "cuj": "CUJ 11: Voice Commands",
        "feature": "Push-to-Talk Voice Request to Font 1 & Next-Pause Queue",
        "manual_rule_from_prd": (
            "Showmaker speaks short request on push-to-talk channel; AI pulls pre-calculated graphic to Font 1, "
            "tags as Pre-Play/Post-Play + Instant/Package, and holds in Next-Pause Queue until a pause satisfies Read-Twice."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "orchestrator",
        "continuous_learning_upgrade": (
            "Learns Showmaker's natural phrasing and anticipates which stat graphic they will ask for before they speak."
        ),
    },
    {
        "id": "PHASE2-01",
        "phase": "Phase 2 Backlog",
        "cuj": "Dynamic Storyline Pivots",
        "feature": "Automatic Narrative Pivot Detection (Momentum Swings & Cold Streaks)",
        "manual_rule_from_prd": (
            "Shift camera, replay, and stat priorities automatically when game narratives change (e.g., bench player "
            "sparking a comeback or star player going 0-for-8)."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "orchestrator",
        "continuous_learning_upgrade": (
            "Discovered directly from full-game video + box-score correlation without manual if-else rules."
        ),
    },
    {
        "id": "PHASE2-02",
        "phase": "Phase 2 Backlog",
        "cuj": "Split-Screen Matchups & Referee Reviews",
        "feature": "2-Box/3-Box Outlier Comparisons & Definitive Review Angle Isolation",
        "manual_rule_from_prd": (
            "Build 2-box and 3-box player/coach comparisons with outlier stats; isolate definitive boundary/clock "
            "angles during official referee reviews and coordinate contractual sponsor break bumpers."
        ),
        "rule_category": "EMERGENT_LEARNED",
        "agent_owner": "replay",
        "continuous_learning_upgrade": (
            "Agent learns which camera angle (Overhead CAM-5 vs. Baseline CAM-2) resolves out-of-bounds vs. shot-clock reviews."
        ),
    },
]

# Pre-computed Shadow Mode Discrepancy & Evolution scenarios showing how the agent
# watches a game, spots where static PRD if-else rules fall short, and evolves new rules automatically.
SHADOW_MODE_EVOLUTION_BATCHES: list[dict[str, Any]] = [
    {
        "batch_id": "shadow-evol-01",
        "game_watched": "Duke vs UNC (2nd Half 11:40 - 00:00): Shadow Mode Diff vs. Veteran Showmaker",
        "shadow_agreement_before": 0.84,
        "shadow_agreement_after": 0.96,
        "discrepancies_detected": [
            {
                "timestamp_mmss": "14:22",
                "what_static_if_else_did": (
                    "Static PRD Rule (CUJ 1.3) cut to CAM-3 (Hero Player Iso) after a made 3-pointer for a fixed multi-second hold."
                ),
                "what_human_director_actually_did": (
                    "Veteran director used a sub-second Hero Iso glance (example: 0.7s to 0.9s) and snapped back to CAM-1 (Main Wide) "
                    "because UNC ran a quick-inbound fast break after the made basket."
                ),
                "emergent_rule_synthesized": {
                    "rule_code": "DIR-04",
                    "agent_role": "director",
                    "title": "Cutting Back Immediately When the Other Team Rushes the Ball Inbounds (Fast-Inbound Rule)",
                    "trigger_condition": (
                        "Right after a basket is made, the team that was scored on grabs the ball and throws it back onto the court immediately to start a fast break."
                    ),
                    "editor_action": (
                        "Generalizes the post-basket celebration rule: while a normal celebration close-up lasts a couple of seconds when players jog slowly, "
                        "a sub-second cut (or staying on the wide camera) is required whenever the other team pushes a fast inbound so viewers never miss a fast break."
                    ),
                    "timing_constraint": "Sub-second celebration cut is allowed on a fast inbound before snapping back to CAM-1 Wide (example: 0.7s to 0.9s glance).",
                    "priority": 10,
                    "confidence": 0.98,
                    "observed_count": 284,
                    "example_timestamps": ["03:42", "08:50", "14:22", "27:30"],
                },
            },
            {
                "timestamp_mmss": "19:05",
                "what_static_if_else_did": (
                    "Static PRD Rule (CUJ 10.3 Read-Twice) queued a 2-line stat graphic on Font 1 and aired it "
                    "on a quick side-out throw-in pause."
                ),
                "what_human_director_actually_did": (
                    "Veteran operator held the Font 1 graphic in the Next-Pause Queue because a quick side-out "
                    "throw-in is too brief to read twice (example: 2.2s pause), waiting for the next extended shooting-foul stoppage."
                ),
                "emergent_rule_synthesized": {
                    "rule_code": "GFX-03",
                    "agent_role": "graphics_scorebug",
                    "title": "Explaining 'Foul Trouble' and Team 'Bonus' Free Throws in Plain Language",
                    "trigger_condition": (
                        "A key player commits multiple personal fouls early in the game, or a team commits enough total fouls in a half to put the other team in the 'Bonus'."
                    ),
                    "editor_action": (
                        "In college basketball, a player is disqualified for the rest of the game if they commit 5 personal fouls, so coaches usually bench a star who gets "
                        "2 fouls in the first half or 3 to 4 fouls early in the second half; show a 'Foul Trouble' banner when they sit down during an extended pause (never on a quick 2-second throw-in). "
                        "Also light up the 'BONUS' badge on the scoreboard when a team reaches 7 fouls in a half."
                    ),
                    "timing_constraint": "Display the Foul Trouble explanation banner during the substitution walk-off (example: 4.0s bench banner).",
                    "priority": 8,
                    "confidence": 0.96,
                    "observed_count": 188,
                    "example_timestamps": ["04:15", "17:35", "19:05", "22:15"],
                },
            },
            {
                "timestamp_mmss": "26:50",
                "what_static_if_else_did": (
                    "Static PRD Rule (CUJ 7A) stitched a 2-angle replay using CAM-2 (Baseline Low) and CAM-3 (Hero Iso)."
                ),
                "what_human_director_actually_did": (
                    "Veteran replay operator dropped CAM-2 because the referee stepped in front of the lens at the rim, "
                    "substituting CAM-5 (Above-Rim Backboard) + REPLAY-A (Hi-Motion) with the Scorebug hidden."
                ),
                "emergent_rule_synthesized": {
                    "rule_code": "RPL-03",
                    "agent_role": "replay",
                    "title": "Side-by-Side Slow Motion When Referees Check the Sideline Video Monitor",
                    "trigger_condition": (
                        "Referees pause the game and walk over to the sideline television monitor to review a close call (such as who touched the ball last before it went out of bounds, or whether a shot beat the buzzer)."
                    ),
                    "editor_action": (
                        "Show synchronized slow-motion replays from the clearest unobstructed baseline camera and overhead basket camera (CAM-5) zoomed in on the exact fingertips "
                        "or ball release with the bottom scoreboard hidden so viewers at home can judge the call right alongside the officials."
                    ),
                    "timing_constraint": "Loop the clearest zoomed-in angles while the referees watch the monitor, and cut back to the live referee on step-away.",
                    "priority": 9,
                    "confidence": 0.96,
                    "observed_count": 95,
                    "example_timestamps": ["26:50", "29:12", "55:50"],
                },
            },
        ],
    }
]

