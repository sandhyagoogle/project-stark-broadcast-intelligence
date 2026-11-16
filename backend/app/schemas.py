"""Pydantic schemas for Gemini Structured Outputs, Timeline Events, Editor KB, and Multi-Agent Control Room."""

from typing import Literal
from pydantic import BaseModel, Field


AgentRole = Literal["orchestrator", "director", "replay", "graphics_scorebug"]
EventType = Literal[
    "LIVE_CUT",
    "REPLAY_CAPTURE",
    "REPLAY_ROLL",
    "SCOREBUG_UPDATE",
    "GRAPHICS_LOWER_THIRD",
    "WHISTLE_DEADBALL",
]
CameraAngle = Literal[
    "CAM-1 (Main Wide)",
    "CAM-2 (Baseline Low)",
    "CAM-3 (Hero Player Iso)",
    "CAM-4 (Coach/Bench Iso)",
    "CAM-5 (Above-Rim / Backboard)",
    "REPLAY-A (Hi-Motion Baseline)",
    "REPLAY-B (Slash Iso)",
]


class ScorebugState(BaseModel):
    home_team: str = Field(description="Home team abbreviation, e.g. DUKE", max_length=12)
    away_team: str = Field(description="Away team abbreviation, e.g. UNC", max_length=12)
    home_score: int = Field(ge=0, le=250, description="Home team score")
    away_score: int = Field(ge=0, le=250, description="Away team score")
    period: str = Field(description="Period/Half, e.g. '1ST', '2ND', 'OT'", max_length=10)
    game_clock: str = Field(description="Game clock MM:SS or SS.d, e.g. '04:18'", max_length=10)
    shot_clock: int = Field(ge=0, le=30, description="Shot clock in seconds (0-30)")
    possession: str = Field(description="Team with possession or 'DEAD'", max_length=12)
    bonus_state: str = Field(
        default="NONE",
        description="Bonus state, e.g. 'NONE', 'DUKE BONUS', 'BOTH DOUBLE BONUS'",
        max_length=40,
    )
    active_graphic_banner: str | None = Field(
        default=None,
        description="Active lower-third or Scorebug stat banner text, if visible",
        max_length=180,
    )


class BroadcastTimelineEventSchema(BaseModel):
    timestamp_mmss: str = Field(
        description="Video timestamp in MM:SS format (00:00 to 60:00)", max_length=10
    )
    timestamp_seconds: int = Field(
        ge=0, le=3600, description="Video timestamp in seconds from start of video (0 to 3600s / 60 mins)"
    )
    event_type: EventType = Field(description="Category of broadcast edit or game event")
    agent_domain: AgentRole = Field(
        description="Which broadcast agent role handles this decision"
    )
    camera_angle: CameraAngle = Field(description="Active camera or replay feed selected")
    game_action_trigger: str = Field(
        description="What happened on the court or game clock that caused this edit",
        max_length=300,
    )
    editor_decision: str = Field(
        description="Specific action taken by the human broadcast editor/director",
        max_length=300,
    )
    editor_rationale: str = Field(
        description="Why the human editor made this cut/replay/graphic choice at this moment",
        max_length=400,
    )
    duration_seconds: float = Field(
        ge=0.5, le=120.0, description="Duration of this shot, replay, or graphic overlay"
    )
    scorebug: ScorebugState = Field(description="Scoreboard / Scorebug state at this timestamp")


class LearnedEditorRuleSchema(BaseModel):
    rule_code: str = Field(
        description="Short rule identifier, e.g. 'DIR-01', 'STORY-01', 'AUD-01', 'ARB-01', or 'AUTO'",
        max_length=24,
    )
    agent_role: AgentRole = Field(description="Target agent that will execute this rule")
    title: str = Field(description="Concise human-readable Title Case title of the editing pattern", max_length=200)
    trigger_condition: str = Field(
        description="Plain-English game-action, whistle, audio, or game-clock condition that activates the rule",
        max_length=900,
    )
    editor_action: str = Field(
        description="Plain-English camera cut, replay buffer/roll action, or Scorebug/graphic instruction",
        max_length=900,
    )
    timing_constraint: str = Field(
        description="Measurable timing or cadence window in seconds, frames, or clock ticks (e.g., 'Hold hero close-up 2.0-3.0s, cut back before midcourt cross')",
        max_length=500,
    )
    priority: int = Field(ge=1, le=10, description="Priority weight from 1 (low) to 10 (critical override)")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from observed video occurrences")
    observed_count: int = Field(ge=1, le=5000, description="Number of times observed in broadcast footage")
    example_timestamps: list[str] = Field(
        description="List of MM:SS video timestamps where the human editor applied this rule"
    )


class GeminiVideoAnalysisResult(BaseModel):
    broadcast_title: str = Field(description="Title of the analyzed college basketball broadcast")
    summary: str = Field(description="Executive summary of the human editor's pacing and style")
    avg_shot_duration_sec: float = Field(description="Average duration between camera cuts in seconds")
    replay_frequency_per_10min: float = Field(description="Average replays rolled per 10 minutes of broadcast")
    events: list[BroadcastTimelineEventSchema] = Field(
        description="Chronological broadcast timeline events across the 30-to-60 minute video"
    )
    learned_rules: list[LearnedEditorRuleSchema] = Field(
        description="Distilled editor heuristics for the Orchestrator, Director, Replay, and Scorebug agents"
    )


class YouTubeAnalyzeRequest(BaseModel):
    youtube_url: str = Field(min_length=10, max_length=300)
    title: str = Field(min_length=3, max_length=140)
    processing_mode: Literal["agentic", "static"] = "agentic"
    duration_minutes: int = Field(default=60, ge=5, le=60)


class MicroWindowInspectRequest(BaseModel):
    video_id: str = Field(min_length=2, max_length=80)
    start_offset_sec: int = Field(ge=0, le=3590)
    end_offset_sec: int = Field(ge=5, le=3600)
    fps: float = Field(default=2.0, ge=0.5, le=5.0)
    focus_prompt: str = Field(
        default="Analyze every camera cut, replay stinger, and Scorebug clock/score tick in this window.",
        min_length=5,
        max_length=400,
    )


class CreateRuleRequest(BaseModel):
    rule_code: str = Field(min_length=2, max_length=24)
    agent_role: AgentRole
    title: str = Field(min_length=3, max_length=200)
    trigger_condition: str = Field(min_length=5, max_length=900)
    editor_action: str = Field(min_length=5, max_length=900)
    timing_constraint: str = Field(min_length=2, max_length=500)
    priority: int = Field(default=8, ge=1, le=10)
    confidence: float = Field(default=0.92, ge=0.0, le=1.0)
    example_timestamps: list[str] = Field(default_factory=list)


ReviewStatus = Literal["agree", "partially_agree", "disagree", "unreviewed"]


class RuleReviewRequest(BaseModel):
    review_status: ReviewStatus = Field(
        description="Reviewer evaluation: 'agree', 'partially_agree', 'disagree', or 'unreviewed'"
    )
    reviewer_comment: str = Field(
        default="",
        max_length=1000,
        description="Reviewer notes, partial-agreement caveats, or feedback persisted with the rule",
    )
    reviewer_name: str = Field(
        default="Broadcast Reviewer",
        min_length=1,
        max_length=80,
        description="Name or role of the reviewer",
    )



class LiveGameSituationInput(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=120)
    video_uri_or_url: str | None = Field(default=None, max_length=300)
    game_clock: str = Field(default="01:42", max_length=10)
    period: str = Field(default="2ND", max_length=10)
    shot_clock: int = Field(default=30, ge=0, le=30)
    home_team: str = Field(default="DUKE", max_length=12)
    away_team: str = Field(default="UNC", max_length=12)
    home_score: int = Field(default=74, ge=0, le=250)
    away_score: int = Field(default=71, ge=0, le=250)
    play_stream_description: str = Field(
        min_length=10,
        max_length=2000,
        description="Live play-by-play feed or video segment context for the multi-agent crew",
    )


class AgentDecisionStep(BaseModel):
    step_order: int = Field(ge=1, le=50)
    offset_sec: float = Field(ge=0.0, le=600.0, description="Seconds from start of sequence")
    game_clock: str = Field(max_length=10)
    shot_clock: int = Field(ge=0, le=30)
    invoked_agent: AgentRole
    orchestrator_cue: str = Field(
        description="Command issued by the Orchestrator Agent to wake/cue this specialist agent"
    )
    matched_kb_rule_code: str = Field(
        description="Rule code from the Editor Knowledge Base that governed this action"
    )
    action_command: str = Field(
        description="Control room switcher / replay / Scorebug execution command"
    )
    camera_or_channel: str = Field(description="Target camera bus, replay channel, or CG layer")
    reasoning: str = Field(
        description="Why this agent took this exact action based on the learned editor heuristics"
    )
    scorebug_snapshot: ScorebugState


class MultiAgentSimulationResponse(BaseModel):
    run_id: str
    scenario_name: str
    model_used: str
    execution_mode: Literal["gemini_live_api", "kb_deterministic_fallback"]
    orchestrator_summary: str
    edl_steps: list[AgentDecisionStep]


class AgentChatQuestionRequest(BaseModel):
    question: str = Field(
        min_length=3,
        max_length=600,
        description="Engineering or broadcast director question, e.g. 'When a player hits a 3-pointer and the defense pushes a fast break, what should the agent do?'",
    )


class YouTubeClipExample(BaseModel):
    video_id: str
    yt_id: str
    broadcast_title: str
    timestamp_mmss: str
    timestamp_seconds: int
    game_clock: str
    period: str
    camera_angle: str
    court_trigger: str
    human_editor_cut: str
    why_this_clip_explains_it: str
    youtube_watch_url: str
    youtube_embed_url: str


class AgentChatAnswerResponse(BaseModel):
    question: str
    primary_agent: AgentRole
    what_agent_should_do: str
    timing_and_override: str
    matched_rule_code: str
    matched_rule_title: str
    rule_category: Literal["CONSTITUTIONAL_GUARDRAIL", "LEARNED_HEURISTIC"]
    confidence: float
    observed_count: int
    youtube_examples: list[YouTubeClipExample]


class PasswordLoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)

