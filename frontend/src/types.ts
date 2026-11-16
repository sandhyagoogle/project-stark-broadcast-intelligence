export type AgentRole = 'orchestrator' | 'director' | 'replay' | 'graphics_scorebug';

export interface ScorebugState {
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  period: string;
  game_clock: string;
  shot_clock: number;
  possession: string;
  bonus_state: string;
  active_graphic_banner?: string | null;
}

export interface BroadcastTimelineEvent {
  id?: number;
  video_id?: string;
  timestamp_mmss: string;
  timestamp_seconds: number;
  event_type: string;
  agent_domain: AgentRole;
  camera_angle: string;
  game_action_trigger: string;
  editor_decision: string;
  editor_rationale: string;
  duration_seconds: number;
  scorebug: ScorebugState;
}

export interface VideoSummary {
  id: string;
  title: string;
  source_type: string;
  source_uri: string;
  gemini_file_uri?: string | null;
  mime_type: string;
  duration_seconds: number;
  processing_mode: string;
  status: string;
  summary: string;
  avg_shot_duration_sec: number;
  replay_frequency_per_10min: number;
  created_at: string;
  event_count?: number;
}

export interface VideoDetail extends VideoSummary {
  events: BroadcastTimelineEvent[];
}

export type ReviewStatus = 'agree' | 'partially_agree' | 'disagree' | 'unreviewed';

export interface EditorRule {
  id?: number;
  rule_code: string;
  agent_role: AgentRole;
  title: string;
  trigger_condition: string;
  editor_action: string;
  timing_constraint: string;
  priority: number;
  confidence: number;
  observed_count: number;
  example_timestamps: string[];
  source_video_id?: string;
  updated_at?: string;
  review_status?: ReviewStatus;
  reviewer_name?: string;
  reviewer_comment?: string;
  review_updated_at?: string | null;
  plain_english_tip?: string;
}

export interface SkillPackage {
  agent_role: AgentRole;
  skill_name: string;
  title: string;
  description: string;
  skill_md_path: string;
  heuristics_json_path: string;
  rule_count: number;
  skill_markdown: string;
}

export interface SkillsBundleResponse {
  skills_root_dir: string;
  antigravity_runner_path: string;
  antigravity_runner_code: string;
  packages: SkillPackage[];
}

export interface AgentDecisionStep {
  step_order: number;
  offset_sec: number;
  game_clock: string;
  shot_clock: number;
  invoked_agent: AgentRole;
  orchestrator_cue: string;
  matched_kb_rule_code: string;
  action_command: string;
  camera_or_channel: string;
  reasoning: string;
  scorebug_snapshot: ScorebugState;
}

export interface MultiAgentSimulationResponse {
  run_id: string;
  scenario_name: string;
  model_used: string;
  execution_mode: string;
  orchestrator_summary: string;
  edl_steps: AgentDecisionStep[];
}

export interface ProjectStarkBacklogItem {
  id: string;
  phase: string;
  cuj: string;
  feature: string;
  manual_rule_from_prd: string;
  rule_category: 'CONSTITUTIONAL_GUARDRAIL' | 'EMERGENT_LEARNED';
  agent_owner: AgentRole;
  continuous_learning_upgrade: string;
}

export interface ShadowDiscrepancy {
  timestamp_mmss: string;
  what_static_if_else_did: string;
  what_human_director_actually_did: string;
  emergent_rule_synthesized: EditorRule;
}

export interface ShadowEvolutionBatch {
  batch_id: string;
  game_watched: string;
  shadow_agreement_before: number;
  shadow_agreement_after: number;
  discrepancies_detected: ShadowDiscrepancy[];
}

export interface ProjectStarkReferenceResponse {
  metadata: {
    doc_id: string;
    title: string;
    authors: string[];
    collaborators: string[];
    version: string;
    paradigm_shift: string;
    architectural_thesis: {
      why_manual_if_else_fails: string;
      hybrid_solution: string;
    };
  };
  backlog: ProjectStarkBacklogItem[];
  shadow_mode_batches: ShadowEvolutionBatch[];
}

export interface ShadowEvolveResult {
  batch_id: string;
  game_watched: string;
  shadow_agreement_before: number;
  shadow_agreement_after: number;
  evolved_rules_added: EditorRule[];
  total_kb_rules: number;
  skills_updated: boolean;
  skills_root_dir: string;
}

export interface YouTubeClipExample {
  video_id: string;
  yt_id: string;
  broadcast_title: string;
  timestamp_mmss: string;
  timestamp_seconds: number;
  game_clock: string;
  period: string;
  camera_angle: string;
  court_trigger: string;
  human_editor_cut: string;
  why_this_clip_explains_it: string;
  youtube_watch_url: string;
  youtube_embed_url: string;
}

export interface AgentChatAnswerResponse {
  question: string;
  primary_agent: AgentRole;
  what_agent_should_do: string;
  timing_and_override: string;
  matched_rule_code: string;
  matched_rule_title: string;
  rule_category: 'CONSTITUTIONAL_GUARDRAIL' | 'LEARNED_HEURISTIC';
  confidence: number;
  observed_count: number;
  youtube_examples: YouTubeClipExample[];
}


