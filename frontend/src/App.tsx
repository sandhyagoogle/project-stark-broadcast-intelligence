import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Cpu,
  Download,
  ExternalLink,
  FileText,
  Film,
  Layers,
  Lock,
  MessageSquare,
  Play,
  Sparkles,
  Tv,
  Upload,
  XCircle,
} from 'lucide-react';
import {
  analyzeUploadedBroadcast,
  analyzeYoutubeBroadcast,
  askBroadcastAgent,
  checkAuthStatus,
  fetchAgentSkills,
  fetchEditorRules,
  fetchProjectStarkReference,
  fetchVideoDetail,
  fetchVideos,
  loginWithPassword,
  logoutSession,
  runShadowModeEvolution,
  simulateBroadcastAgents,
  submitRuleReview,
} from './api';
import type {
  AgentChatAnswerResponse,
  AgentRole,
  BroadcastTimelineEvent,
  EditorRule,
  MultiAgentSimulationResponse,
  ProjectStarkReferenceResponse,
  ReviewStatus,
  SkillsBundleResponse,
  VideoDetail,
  VideoSummary,
} from './types';

type StudioTab =
  | 'telemetry'
  | 'ask-agent'
  | 'knowledge-base'
  | 'project-stark'
  | 'skills-studio'
  | 'control-room'
  | 'ingest';

const CAMERA_FEEDS = [
  { id: 'CAM-1', name: 'Main Wide' },
  { id: 'CAM-2', name: 'Baseline Low' },
  { id: 'CAM-3', name: 'Hero Iso' },
  { id: 'CAM-4', name: 'Coach / Bench' },
  { id: 'CAM-5', name: 'Above Rim' },
  { id: 'REPLAY-A', name: 'Hi-Mo Replay' },
];

const PRESET_ENGINEER_QUESTIONS = [
  'Are replays ever cut in between, or cut across multiple angles?',
  'What % of a full game is on camera 3?',
  'What is the percentage breakdown of all cameras across a full game?',
  'How does overall game storytelling and camera pacing evolve across the 1st half, mid-game runs, and crunch time?',
  'When the commentator calls out a tired player or coach on the sideline, or is explaining a slow-mo replay, how should audio sync work?',
  'How should the agent check for camera whip-pans, stability, and fast-break lead room before cutting?',
  'How does the agent preserve the 180-degree court line and prevent rapid ping-pong camera cuts?',
  'When all 4 agents collide on an And-One basket-plus-foul, what is the priority arbitration hierarchy and graphic TTL?',
  'How do we prevent lower-third banners from covering the ball on the near sideline or stacking over the scoreboard?',
  'What is the 3-step sequence going into a commercial break and returning from a break?',
  'When a whistle is ambiguous, ball-tracking confidence drops, or a fan blocks the lens, what are the reliability fallbacks?',
  'When a player hits a 3-pointer and the defense pushes a fast break, what should the agent do?',
  'When a quick side-out whistle happens and a Font 1 stat graphic is queued, what should the agent do?',
  'When a baseline referee blocks the replay angle on a dunk, what should the agent do?',
];

function getRuleCategoryLabel(ruleCode: string): string {
  if (ruleCode.startsWith('STORY-')) return 'Game Storytelling';
  if (ruleCode.startsWith('AUD-')) return 'Audio & Commentary';
  if (ruleCode.startsWith('CAM-')) return 'Camera Motion';
  if (ruleCode.startsWith('CNT-')) return 'Spatial Continuity';
  if (ruleCode.startsWith('ARB-')) return 'Agent Arbitration';
  if (ruleCode.startsWith('LYT-')) return 'Overlay Layout';
  if (ruleCode.startsWith('BRK-')) return 'Breaks & Bumpers';
  if (ruleCode.startsWith('REL-')) return 'Reliability & Fallbacks';
  return 'Shot Transitions';
}

function formatAgentRoleLabel(role: string): string {
  const normalized = role.trim().toLowerCase();
  if (normalized === 'orchestrator') return 'Orchestrator';
  if (normalized === 'director') return 'Director';
  if (normalized === 'replay') return 'Replay';
  if (normalized === 'graphics_scorebug' || normalized === 'graphics') return 'Graphics & Scorebug';
  return role
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

const CATEGORY_TOP_INSIGHTS: Record<string, readonly string[]> = {
  MACRO: ['STORY-38', 'STORY-08'], // Game Storytelling
  SHOT: ['ORC-04', 'RPL-23'], // Shot Transitions
  'AUD-': ['AUD-04', 'AUD-02'], // Audio & Commentary
  'CAM-': ['CAM-01', 'CAM-02'], // Camera Motion
  'CNT-': ['CNT-03', 'CNT-01'], // Spatial Continuity
  'ARB-': ['ARB-01', 'ARB-02'], // Agent Arbitration
  'LYT-': ['LYT-05', 'LYT-01'], // Overlay Layout
  'BRK-': ['BRK-21', 'BRK-15'], // Breaks & Bumpers
  'REL-': ['REL-02', 'REL-13'], // Reliability & Fallbacks
};

const AGENT_TOP_INSIGHTS: Record<string, readonly string[]> = {
  orchestrator: ['ARB-01', 'AUD-04'],
  director: ['CNT-03', 'CAM-01'],
  replay: ['AUD-02', 'RPL-23'],
  graphics_scorebug: ['LYT-05', 'LYT-01'],
};

const ALL_CATEGORY_TOP_INSIGHTS: readonly string[] = Object.values(CATEGORY_TOP_INSIGHTS).flat();

export function App() {
  const [activeTab, setActiveTab] = useState<StudioTab>('telemetry');
  const [videos, setVideos] = useState<VideoSummary[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState<string>('');
  const [videoDetail, setVideoDetail] = useState<VideoDetail | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<BroadcastTimelineEvent | null>(null);
  const [rules, setRules] = useState<EditorRule[]>([]);
  const [skillsBundle, setSkillsBundle] = useState<SkillsBundleResponse | null>(null);
  const [starkRef, setStarkRef] = useState<ProjectStarkReferenceResponse | null>(null);
  const [activeSkillRole, setActiveSkillRole] = useState<AgentRole>('orchestrator');
  const [simulationResult, setSimulationResult] = useState<MultiAgentSimulationResponse | null>(
    null
  );
  const [askQuestion, setAskQuestion] = useState<string>(PRESET_ENGINEER_QUESTIONS[0]);
  const [isPresetMenuOpen, setIsPresetMenuOpen] = useState<boolean>(false);
  const [askAnswer, setAskAnswer] = useState<AgentChatAnswerResponse | null>(null);
  const [agentFilter, setAgentFilter] = useState<string>('ALL');
  const [reviewFilter, setReviewFilter] = useState<string>('ALL');
  const [reviewerName, setReviewerName] = useState<string>('Broadcast Reviewer');
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [openCommentBoxes, setOpenCommentBoxes] = useState<Record<string, boolean>>({});
  const [savingRuleCode, setSavingRuleCode] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const [ytUrl, setYtUrl] = useState(
    'https://www.youtube.com/watch?v=T_uLlzfDCjI'
  );
  const [ytTitle, setYtTitle] = useState(
    'College Basketball Crown Championship: Oklahoma vs West Virginia'
  );
  const [processingMode, setProcessingMode] = useState<'agentic' | 'static'>('agentic');
  const [durationMinutes, setDurationMinutes] = useState<number>(60);
  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [simScenario, setSimScenario] = useState(
    '2nd Half, 01:48 remaining, Duke 74 - UNC 71. Duke drives baseline, finishes a contested dunk (+2) and draws an and-one shooting foul.'
  );

  const [isAuthChecking, setIsAuthChecking] = useState<boolean>(true);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [passwordInput, setPasswordInput] = useState<string>('');
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = useState<boolean>(false);

  const inspectorDialogRef = useRef<HTMLDialogElement | null>(null);
  const askComboboxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const status = await checkAuthStatus();
        setIsAuthenticated(status.authenticated);
        setIsAuthChecking(false);
        if (status.authenticated) {
          void loadInitialStudio();
        }
      } catch {
        setIsAuthChecking(false);
      }
    })();
  }, []);

  async function handlePasswordLogin(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!passwordInput.trim()) return;
    setIsSigningIn(true);
    setAuthError(null);
    try {
      await loginWithPassword(passwordInput);
      setPasswordInput('');
      setShowPassword(false);
      setIsSigningIn(false);
      setIsAuthenticated(true);
      void loadInitialStudio();
    } catch (err) {
      setAuthError(err instanceof Error ? err.message : 'Invalid access password.');
      setIsSigningIn(false);
    }
  }

  async function handleLogout() {
    await logoutSession();
    setVideos([]);
    setVideoDetail(null);
    setSelectedEvent(null);
    setRules([]);
    setSkillsBundle(null);
    setStarkRef(null);
    setAskAnswer(null);
    setSimulationResult(null);
    setIsAuthenticated(false);
    window.location.replace('/');
  }

  useEffect(() => {
    function handleOutsideClick(e: MouseEvent) {
      if (askComboboxRef.current && !askComboboxRef.current.contains(e.target as Node)) {
        setIsPresetMenuOpen(false);
      }
    }
    function handleUnauthorized() {
      setIsAuthenticated(false);
      setIsAuthChecking(false);
    }
    document.addEventListener('mousedown', handleOutsideClick);
    window.addEventListener('cv-unauthorized', handleUnauthorized);
    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
      window.removeEventListener('cv-unauthorized', handleUnauthorized);
    };
  }, []);

  async function loadInitialStudio() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const list = await fetchVideos();
      setVideos(list);
      if (list.length > 0) {
        const firstId = list[0].id;
        setSelectedVideoId(firstId);
        const [detail, loadedRules, skills, stark] = await Promise.all([
          fetchVideoDetail(firstId),
          fetchEditorRules(),
          fetchAgentSkills(),
          fetchProjectStarkReference(),
        ]);
        setVideoDetail(detail);
        setSelectedEvent(detail.events[0] ?? null);
        setRules(loadedRules);
        setSkillsBundle(skills);
        setStarkRef(stark);
        void askBroadcastAgent(PRESET_ENGINEER_QUESTIONS[0])
          .then((initialQa) => setAskAnswer(initialQa))
          .catch(() => {});
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to initialize');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAskAgent(questionText?: string) {
    const query = (questionText ?? askQuestion).trim();
    if (!query) return;
    setAskQuestion(query);
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await askBroadcastAgent(query);
      setAskAnswer(res);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Agent Q&A failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSelectVideo(videoId: string, targetTimestampMmss?: string) {
    setSelectedVideoId(videoId);
    setIsLoading(true);
    try {
      const detail = await fetchVideoDetail(videoId);
      setVideoDetail(detail);
      if (targetTimestampMmss) {
        const matched = detail.events.find((e) => e.timestamp_mmss === targetTimestampMmss);
        setSelectedEvent(matched ?? detail.events[0] ?? null);
      } else {
        setSelectedEvent(detail.events[0] ?? null);
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to load video');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAnalyzeYoutube(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const detail = await analyzeYoutubeBroadcast({
        youtube_url: ytUrl,
        title: ytTitle,
        processing_mode: processingMode,
        duration_minutes: durationMinutes,
      });
      const [updatedVideos, updatedRules, updatedSkills] = await Promise.all([
        fetchVideos(),
        fetchEditorRules(),
        fetchAgentSkills(),
      ]);
      setVideos(updatedVideos);
      setSelectedVideoId(detail.id);
      setVideoDetail(detail);
      setSelectedEvent(detail.events[0] ?? null);
      setRules(updatedRules);
      setSkillsBundle(updatedSkills);
      setActiveTab('telemetry');
      setStatusMessage(`Loaded ${detail.title}`);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'YouTube analysis failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleAnalyzeUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!uploadFile) {
      setErrorMessage('Select a .mp4 or .mov file first.');
      return;
    }
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const detail = await analyzeUploadedBroadcast({
        file: uploadFile,
        title: uploadFile.name.replace(/\.[^.]+$/, ''),
        processing_mode: processingMode,
        duration_minutes: durationMinutes,
      });
      const [updatedVideos, updatedRules, updatedSkills] = await Promise.all([
        fetchVideos(),
        fetchEditorRules(),
        fetchAgentSkills(),
      ]);
      setVideos(updatedVideos);
      setSelectedVideoId(detail.id);
      setVideoDetail(detail);
      setSelectedEvent(detail.events[0] ?? null);
      setRules(updatedRules);
      setSkillsBundle(updatedSkills);
      setActiveTab('telemetry');
      setStatusMessage(`Uploaded ${detail.title}`);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRunShadowEvolution() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const result = await runShadowModeEvolution();
      const [updatedRules, updatedSkills] = await Promise.all([
        fetchEditorRules(),
        fetchAgentSkills(),
      ]);
      setRules(updatedRules);
      setSkillsBundle(updatedSkills);
      setStatusMessage(
        `Added ${result.evolved_rules_added.length} rules (${(
          result.shadow_agreement_before * 100
        ).toFixed(0)}% -> ${(result.shadow_agreement_after * 100).toFixed(0)}% agreement)`
      );
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Evolution failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRunSimulation() {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await simulateBroadcastAgents({
        scenario_name: 'Late Game Sequence',
        game_clock: '01:48',
        period: '2ND',
        shot_clock: 14,
        home_team: 'DUKE',
        away_team: 'UNC',
        home_score: 74,
        away_score: 71,
        play_stream_description: simScenario,
      });
      setSimulationResult(res);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSaveRuleReview(
    rule: EditorRule,
    nextStatus: ReviewStatus,
    commentText?: string
  ) {
    const code = rule.rule_code;
    const effectiveComment =
      commentText !== undefined
        ? commentText
        : commentDrafts[code] ?? rule.reviewer_comment ?? '';

    if (nextStatus === 'partially_agree' || nextStatus === 'disagree') {
      setOpenCommentBoxes((prev) => ({ ...prev, [code]: true }));
    }

    setSavingRuleCode(code);
    setErrorMessage(null);
    try {
      const res = await submitRuleReview(code, {
        review_status: nextStatus,
        reviewer_comment: effectiveComment,
        reviewer_name: reviewerName.trim() || 'Broadcast Reviewer',
      });
      setRules((prev) =>
        prev.map((item) => (item.rule_code === code ? res.rule : item))
      );
      setCommentDrafts((prev) => ({
        ...prev,
        [code]: res.rule.reviewer_comment ?? '',
      }));
      const updatedSkills = await fetchAgentSkills();
      setSkillsBundle(updatedSkills);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save rule review');
    } finally {
      setSavingRuleCode(null);
    }
  }

  function openEventInspector(ev: BroadcastTimelineEvent) {
    setSelectedEvent(ev);
    if (inspectorDialogRef.current && !inspectorDialogRef.current.open) {
      inspectorDialogRef.current.showModal();
    }
  }

  function handleDialogBackdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === inspectorDialogRef.current) {
      inspectorDialogRef.current?.close();
    }
  }

  const currentEvent = selectedEvent ?? videoDetail?.events[0] ?? null;
  const activeSpotlightCodes: readonly string[] =
    agentFilter === 'ALL'
      ? ALL_CATEGORY_TOP_INSIGHTS
      : CATEGORY_TOP_INSIGHTS[agentFilter] ?? AGENT_TOP_INSIGHTS[agentFilter] ?? [];

  const sortedRules = [...rules].sort((a, b) => {
    const aSpot = activeSpotlightCodes.indexOf(a.rule_code);
    const bSpot = activeSpotlightCodes.indexOf(b.rule_code);
    if (aSpot !== -1 || bSpot !== -1) {
      if (aSpot === -1) return 1;
      if (bSpot === -1) return -1;
      return aSpot - bSpot;
    }
    const aMacro = a.rule_code.startsWith('STORY-') ? 0 : 1;
    const bMacro = b.rule_code.startsWith('STORY-') ? 0 : 1;
    if (aMacro !== bMacro) return aMacro - bMacro;
    return a.rule_code.localeCompare(b.rule_code);
  });
  const engPrefixes = ['AUD-', 'CAM-', 'CNT-', 'ARB-', 'LYT-', 'BRK-', 'REL-'];
  const categoryFilteredRules =
    agentFilter === 'ALL'
      ? sortedRules
      : agentFilter === 'MACRO'
      ? sortedRules.filter((r) => r.rule_code.startsWith('STORY-'))
      : agentFilter === 'SHOT'
      ? sortedRules.filter(
          (r) =>
            !r.rule_code.startsWith('STORY-') &&
            !engPrefixes.some((p) => r.rule_code.startsWith(p))
        )
      : engPrefixes.includes(agentFilter)
      ? sortedRules.filter((r) => r.rule_code.startsWith(agentFilter))
      : sortedRules.filter((r) => r.agent_role === agentFilter);

  const reviewCounts = {
    all: categoryFilteredRules.length,
    agree: categoryFilteredRules.filter((r) => r.review_status === 'agree').length,
    partially_agree: categoryFilteredRules.filter((r) => r.review_status === 'partially_agree')
      .length,
    disagree: categoryFilteredRules.filter((r) => r.review_status === 'disagree').length,
    unreviewed: categoryFilteredRules.filter(
      (r) => !r.review_status || r.review_status === 'unreviewed'
    ).length,
    commented: categoryFilteredRules.filter((r) => Boolean(r.reviewer_comment?.trim())).length,
  };

  const filteredRules =
    reviewFilter === 'ALL'
      ? categoryFilteredRules
      : reviewFilter === 'commented'
      ? categoryFilteredRules.filter((r) => Boolean(r.reviewer_comment?.trim()))
      : reviewFilter === 'unreviewed'
      ? categoryFilteredRules.filter(
          (r) => !r.review_status || r.review_status === 'unreviewed'
        )
      : categoryFilteredRules.filter((r) => r.review_status === reviewFilter);
  const selectedSkillPkg =
    skillsBundle?.packages.find((p) => p.agent_role === activeSkillRole) ??
    skillsBundle?.packages[0] ??
    null;

  if (isAuthChecking) {
    return (
      <div className="auth-gate-shell">
        <div className="brand-row">
          <div className="brand-badge">CV</div>
          <div className="brand-title">
            <h1>CourtVision</h1>
          </div>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="auth-gate-shell">
        <form className="auth-gate-card" onSubmit={(e) => void handlePasswordLogin(e)}>
          <div className="brand-row">
            <div className="brand-badge">CV</div>
            <div className="brand-title">
              <h1>CourtVision</h1>
            </div>
          </div>

          <div className="form-field">
            <label htmlFor="access-password-input">Access Password</label>
            <div className="auth-password-row">
              <input
                id="access-password-input"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                enterKeyHint="done"
                required
                value={passwordInput}
                onChange={(e) => setPasswordInput(e.target.value)}
                autoFocus
              />
              <button
                type="button"
                className="auth-visibility-btn"
                aria-pressed={showPassword}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword((prev) => !prev)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </div>

          {authError && (
            <div className="auth-error-text" role="alert">
              {authError}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary"
            disabled={isSigningIn}
            style={{ justifyContent: 'center' }}
          >
            <Lock size={14} aria-hidden="true" />
            {isSigningIn ? 'Signing In...' : 'Sign In'}
          </button>
        </form>
      </main>
    );
  }

  return (
    <div className="studio-shell">
      {/* Minimal Top Bar */}
      <header className="studio-header">
        <div className="brand-row">
          <div className="brand-badge">CV</div>
          <div className="brand-title">
            <h1>CourtVision</h1>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          {currentEvent && (
            <div className="score-strip">
              <span>
                <strong>{currentEvent.scorebug.away_team}</strong> {currentEvent.scorebug.away_score}
              </span>
              <span>-</span>
              <span>
                <strong>{currentEvent.scorebug.home_team}</strong> {currentEvent.scorebug.home_score}
              </span>
              <span className="score-dot" />
              <span>
                {currentEvent.scorebug.period} {currentEvent.scorebug.game_clock}
              </span>
              <span className="score-dot" />
              <span>Shot {currentEvent.scorebug.shot_clock}s</span>
            </div>
          )}

          <select
            aria-label="Select Game"
            className="select-minimal"
            value={selectedVideoId}
            onChange={(e) => void handleSelectVideo(e.target.value)}
          >
            {videos.map((v) => (
              <option key={v.id} value={v.id}>
                {v.title}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="btn"
            onClick={() => void handleLogout()}
          >
            <Lock size={14} aria-hidden="true" />
            Lock
          </button>
        </div>
      </header>

      {(statusMessage || errorMessage) && (
        <div className="toast-banner">
          <span>{errorMessage || statusMessage}</span>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setStatusMessage(null);
              setErrorMessage(null);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Segmented Navigation */}
      <div className="nav-bar-row">
        <nav className="nav-tabs" aria-label="Modules">
          <button
            type="button"
            className={`tab-btn ${activeTab === 'telemetry' ? 'active' : ''}`}
            onClick={() => setActiveTab('telemetry')}
          >
            <Tv size={15} />
            Edits
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'ask-agent' ? 'active' : ''}`}
            onClick={() => setActiveTab('ask-agent')}
          >
            <MessageSquare size={15} />
            Ask Agent
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'knowledge-base' ? 'active' : ''}`}
            onClick={() => setActiveTab('knowledge-base')}
          >
            <BookOpen size={15} />
            Rules ({rules.length})
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'project-stark' ? 'active' : ''}`}
            onClick={() => setActiveTab('project-stark')}
          >
            <FileText size={15} />
            Shadow Mode
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'skills-studio' ? 'active' : ''}`}
            onClick={() => setActiveTab('skills-studio')}
          >
            <Sparkles size={15} />
            Skills
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'control-room' ? 'active' : ''}`}
            onClick={() => setActiveTab('control-room')}
          >
            <Cpu size={15} />
            Simulator
          </button>
          <button
            type="button"
            className={`tab-btn ${activeTab === 'ingest' ? 'active' : ''}`}
            onClick={() => setActiveTab('ingest')}
          >
            <Upload size={15} />
            Add Video
          </button>
        </nav>

        {videoDetail?.source_uri.startsWith('https://') && (
          <a
            href={videoDetail.source_uri}
            target="_blank"
            rel="noreferrer"
            className="btn"
            style={{ textDecoration: 'none' }}
          >
            <ExternalLink size={14} />
            Watch on YouTube
          </a>
        )}
      </div>

      {/* TAB 1: EDITS */}
      {activeTab === 'telemetry' && videoDetail && (
        <div className="ResponsiveGridContainer">
          <div className="studio-grid">
            <div className="panel-card">
              <div className="panel-header">
                <h2>
                  <Film size={16} />
                  Game Moments ({videoDetail.events.length})
                </h2>
              </div>
              <div className="event-list">
                {videoDetail.events.map((ev, idx) => {
                  const isSelected =
                    currentEvent?.timestamp_mmss === ev.timestamp_mmss &&
                    currentEvent?.editor_decision === ev.editor_decision;
                  return (
                    <div
                      key={`${ev.timestamp_mmss}-${idx}`}
                      className={`event-row ${isSelected ? 'selected' : ''}`}
                      onClick={() => setSelectedEvent(ev)}
                    >
                      <div className="event-row-top">
                        <span className="time-code">
                          Timestamp: {ev.timestamp_mmss} · Game Clock: {ev.scorebug.game_clock} ({ev.scorebug.period})
                        </span>
                        <span className="agent-badge">{formatAgentRoleLabel(ev.agent_domain)}</span>
                      </div>
                      <div style={{ fontWeight: 500, fontSize: '0.88rem' }}>
                        {ev.game_action_trigger}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="panel-card">
              <div className="panel-header">
                <h2>
                  Selected Moment
                  {currentEvent && (
                    <span style={{ fontWeight: 400, color: 'var(--text-secondary)', fontSize: '0.82rem', marginLeft: '0.5rem' }}>
                      Timestamp: {currentEvent.timestamp_mmss} · Game Clock: {currentEvent.scorebug.game_clock} ({currentEvent.scorebug.period})
                    </span>
                  )}
                </h2>
                {currentEvent && (
                  <button
                    type="button"
                    className="btn"
                    onClick={() => openEventInspector(currentEvent)}
                  >
                    JSON
                  </button>
                )}
              </div>

              {currentEvent && (
                <div className="detail-stack">
                  <div className="detail-block">
                    <div className="detail-label">Court Event</div>
                    <div className="detail-text">{currentEvent.game_action_trigger}</div>
                  </div>

                  <div className="detail-block">
                    <div className="detail-label">
                      Human Edit ({currentEvent.duration_seconds}s)
                    </div>
                    <div className="detail-text">{currentEvent.editor_decision}</div>
                  </div>

                  <div className="detail-block">
                    <div className="detail-label">Learned Rule ({formatAgentRoleLabel(currentEvent.agent_domain)})</div>
                    <div className="detail-text" style={{ color: 'var(--text-secondary)' }}>
                      {currentEvent.editor_rationale}
                    </div>
                  </div>

                  <div>
                    <div className="detail-label" style={{ marginBottom: '0.5rem' }}>
                      Active Camera
                    </div>
                    <div className="camera-wall">
                      {CAMERA_FEEDS.map((cam) => {
                        const isProgram =
                          currentEvent.camera_angle
                            .toLowerCase()
                            .includes(cam.id.slice(0, 6).toLowerCase()) ?? false;
                        return (
                          <div
                            key={cam.id}
                            className={`camera-tile ${isProgram ? 'active-program' : ''}`}
                          >
                            <div className="camera-tile-header">
                              <span>{cam.id}</span>
                              <span className={isProgram ? 'pgm-badge' : 'pvw-badge'}>
                                {isProgram ? 'ON AIR' : 'IDLE'}
                              </span>
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {cam.name}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 1B: ASK AGENT (ENGINEER Q&A + YOUTUBE CLIP EXAMPLES) */}
      {activeTab === 'ask-agent' && (
        <div className="detail-stack">
          <form
            className="panel-card ask-unified-card"
            onSubmit={(e) => {
              e.preventDefault();
              setIsPresetMenuOpen(false);
              void handleAskAgent();
            }}
          >
            <label htmlFor="engineer-question-input" className="ask-combobox-label">
              <MessageSquare size={15} aria-hidden="true" />
              <span>Ask Agent</span>
            </label>

            <div className="ask-unified-row">
              <div className="ask-combobox-wrapper" ref={askComboboxRef}>
                <input
                  id="engineer-question-input"
                  name="question"
                  type="text"
                  className="ask-combobox-input"
                  placeholder="Type a question or click the arrow for presets..."
                  value={askQuestion}
                  onChange={(e) => setAskQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                      setIsPresetMenuOpen(false);
                    }
                  }}
                />
                <button
                  type="button"
                  className="ask-combobox-chevron"
                  aria-label="Choose a preset broadcast question"
                  aria-expanded={isPresetMenuOpen}
                  onClick={() => setIsPresetMenuOpen((prev) => !prev)}
                >
                  <ChevronDown size={16} aria-hidden="true" />
                </button>

                {isPresetMenuOpen && (
                  <ul className="ask-combobox-menu" role="listbox" aria-label="Preset broadcast questions">
                    {PRESET_ENGINEER_QUESTIONS.map((q) => (
                      <li key={q} role="option" aria-selected={askQuestion === q}>
                        <button
                          type="button"
                          className={`ask-combobox-option ${askQuestion === q ? 'selected' : ''}`}
                          onClick={() => {
                            setAskQuestion(q);
                            setIsPresetMenuOpen(false);
                            void handleAskAgent(q);
                          }}
                        >
                          {q}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <button type="submit" className="btn btn-primary ask-submit-btn" disabled={isLoading}>
                {isLoading ? 'Asking...' : 'Ask Agent'}
              </button>
            </div>
          </form>

          {askAnswer && (
            <div className="ResponsiveGridContainer">
              <div className="studio-grid">
                <div className="panel-card">
                  <div className="panel-header">
                    <h2>Agent Action & Rule</h2>
                    <div style={{ display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                      <span className="time-code">{askAnswer.matched_rule_code}</span>
                      <span className="agent-badge">{formatAgentRoleLabel(askAnswer.primary_agent)}</span>
                    </div>
                  </div>

                  <div className="detail-stack">
                    <div className="detail-block">
                      <div className="detail-label">Question Answered</div>
                      <div className="detail-text" style={{ fontWeight: 600 }}>
                        {askAnswer.question}
                      </div>
                    </div>

                    <div className="detail-block">
                      <div className="detail-label">
                        Rule Applied ({(askAnswer.confidence * 100).toFixed(0)}% Confidence · {askAnswer.observed_count} Broadcast Examples)
                      </div>
                      <div className="detail-text" style={{ fontWeight: 600 }}>
                        {askAnswer.matched_rule_title}
                      </div>
                    </div>

                    <div className="detail-block">
                      <div className="detail-label">What the Agent Should Do</div>
                      <div className="detail-text" style={{ whiteSpace: 'pre-line', lineHeight: 1.58 }}>
                        {askAnswer.what_agent_should_do}
                      </div>
                    </div>

                    <div className="detail-block">
                      <div className="detail-label">Timing & Override Constraint</div>
                      <div
                        className="detail-text"
                        style={{ color: 'var(--text-secondary)', whiteSpace: 'pre-line', lineHeight: 1.5 }}
                      >
                        {askAnswer.timing_and_override}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="panel-card">
                  <div className="panel-header">
                    <h2>
                      <Film size={16} />
                      YouTube Reference Clips ({askAnswer.youtube_examples.length})
                    </h2>
                  </div>

                  <div className="detail-stack">
                    {askAnswer.youtube_examples.map((clip, idx) => (
                      <div
                        key={`${clip.video_id}-${clip.timestamp_mmss}-${idx}`}
                        className="detail-block"
                      >
                        <div className="event-row-top" style={{ marginBottom: '0.5rem' }}>
                          <span className="time-code">
                            Timestamp: {clip.timestamp_mmss} · Game Clock: {clip.game_clock} ({clip.period})
                          </span>
                          <span className="agent-badge">{clip.camera_angle}</span>
                        </div>

                        <div style={{ fontWeight: 600, fontSize: '0.88rem', marginBottom: '0.55rem' }}>
                          {clip.broadcast_title}
                        </div>

                        <div
                          style={{
                            borderRadius: '8px',
                            overflow: 'hidden',
                            border: '1px solid var(--border-subtle)',
                            marginBottom: '0.65rem',
                            background: '#000',
                          }}
                        >
                          <iframe
                            title={`${clip.broadcast_title} at ${clip.timestamp_mmss}`}
                            src={clip.youtube_embed_url}
                            width="100%"
                            height="215"
                            style={{ border: 0, display: 'block' }}
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                          />
                        </div>

                        <div style={{ fontSize: '0.82rem', marginBottom: '0.3rem' }}>
                          <strong>Court Trigger:</strong> {clip.court_trigger}
                        </div>
                        <div style={{ fontSize: '0.82rem', marginBottom: '0.3rem' }}>
                          <strong>Human Cut:</strong> {clip.human_editor_cut}
                        </div>
                        <div
                          style={{
                            fontSize: '0.8rem',
                            color: 'var(--text-secondary)',
                            marginBottom: '0.65rem',
                          }}
                        >
                          <strong>Why This Example:</strong> {clip.why_this_clip_explains_it}
                        </div>

                        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                          <a
                            href={clip.youtube_watch_url}
                            target="_blank"
                            rel="noreferrer"
                            className="btn btn-primary"
                            style={{ textDecoration: 'none' }}
                          >
                            <ExternalLink size={13} />
                            Watch Clip on YouTube (@ {clip.timestamp_mmss})
                          </a>
                          <button
                            type="button"
                            className="btn"
                            onClick={() => {
                              void handleSelectVideo(clip.video_id, clip.timestamp_mmss);
                              setActiveTab('telemetry');
                            }}
                          >
                            Open Moment in Edits
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: RULES */}
      {activeTab === 'knowledge-base' && (
        <div className="panel-card">
          <div className="panel-header">
            <h2>Extracted Rules ({filteredRules.length})</h2>
            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
              {[
                { id: 'ALL', label: 'All Rules' },
                { id: 'MACRO', label: 'Game Storytelling' },
                { id: 'SHOT', label: 'Shot Transitions' },
                { id: 'AUD-', label: 'Audio & Commentary' },
                { id: 'CAM-', label: 'Camera Motion' },
                { id: 'CNT-', label: 'Spatial Continuity' },
                { id: 'ARB-', label: 'Agent Arbitration' },
                { id: 'LYT-', label: 'Overlay Layout' },
                { id: 'BRK-', label: 'Breaks & Bumpers' },
                { id: 'REL-', label: 'Reliability & Fallbacks' },
                { id: 'orchestrator', label: 'Orchestrator' },
                { id: 'director', label: 'Director' },
                { id: 'replay', label: 'Replay' },
                { id: 'graphics_scorebug', label: 'Graphics & Scorebug' },
              ].map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={`btn ${agentFilter === item.id ? 'btn-primary' : ''}`}
                  onClick={() => setAgentFilter(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="rule-review-bar" style={{ marginBottom: '1.25rem' }}>
            <div className="rule-review-pills" role="group" aria-label="Filter rules by reviewer status">
              {[
                { id: 'ALL', label: `All Statuses (${reviewCounts.all})` },
                { id: 'agree', label: `Agreed (${reviewCounts.agree})` },
                { id: 'partially_agree', label: `Partially Agreed (${reviewCounts.partially_agree})` },
                { id: 'disagree', label: `Disagreed (${reviewCounts.disagree})` },
                { id: 'unreviewed', label: `Needs Review (${reviewCounts.unreviewed})` },
                { id: 'commented', label: `With Comments (${reviewCounts.commented})` },
              ].map((pill) => (
                <button
                  key={pill.id}
                  type="button"
                  className={`btn ${reviewFilter === pill.id ? 'btn-primary' : ''}`}
                  onClick={() => setReviewFilter(pill.id)}
                >
                  {pill.label}
                </button>
              ))}
            </div>

            <div className="reviewer-name-group">
              <label htmlFor="reviewer-name-input">Reviewer:</label>
              <input
                id="reviewer-name-input"
                type="text"
                className="reviewer-name-input"
                value={reviewerName}
                onChange={(e) => setReviewerName(e.target.value)}
                placeholder="Your name or role"
                maxLength={80}
              />
            </div>
          </div>

          <div className="pattern-grid">
            {filteredRules.map((rule) => {
              const isSpotlight = activeSpotlightCodes.includes(rule.rule_code);
              const isMacro = rule.rule_code.startsWith('STORY-');
              const catLabel = getRuleCategoryLabel(rule.rule_code);
              const currentStatus: ReviewStatus = rule.review_status ?? 'unreviewed';
              const savedComment = (rule.reviewer_comment ?? '').trim();
              const draftText = commentDrafts[rule.rule_code] ?? rule.reviewer_comment ?? '';
              const isCommentOpen = Boolean(
                openCommentBoxes[rule.rule_code] ||
                  currentStatus === 'partially_agree' ||
                  currentStatus === 'disagree'
              );
              const isSaving = savingRuleCode === rule.rule_code;
              const commentInputId = `rule-comment-${rule.rule_code}`;

              return (
                <div
                  key={rule.rule_code}
                  className={`pattern-card ${isSpotlight ? 'spotlight-card' : ''}`}
                >
                  <div className="event-row-top">
                    <span className="time-code">{rule.rule_code}</span>
                    <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center', flexWrap: 'wrap' }}>
                      {isSpotlight && (
                        <span className="agent-badge spotlight-badge">Top Insight</span>
                      )}
                      <span className="agent-badge">{catLabel}</span>
                      <span className="agent-badge">{formatAgentRoleLabel(rule.agent_role)}</span>
                    </div>
                  </div>
                  <h3>{rule.title}</h3>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-secondary)' }}>
                    <strong>{isMacro ? 'Storytelling Context:' : 'When:'}</strong> {rule.trigger_condition}
                  </div>
                  <div style={{ fontSize: '0.84rem', color: 'var(--text-main)' }}>
                    <strong>{isMacro ? 'Game-Level Policy:' : 'Action:'}</strong> {rule.editor_action}
                  </div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    <strong>Timing &amp; Guardrail:</strong> {rule.timing_constraint}
                  </div>
                  {rule.plain_english_tip && (
                    <div
                      style={{
                        fontSize: '0.75rem',
                        color: 'var(--accent-blue)',
                        background: 'rgba(66, 133, 244, 0.08)',
                        padding: '0.35rem 0.55rem',
                        borderRadius: '6px',
                      }}
                    >
                      <strong>Basketball Context:</strong> {rule.plain_english_tip}
                    </div>
                  )}
                  <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                    Observed {rule.observed_count}x · {(rule.confidence * 100).toFixed(0)}% Confidence
                    {rule.example_timestamps && rule.example_timestamps.length > 0
                      ? ` · Examples: ${rule.example_timestamps.slice(0, 4).join(', ')}`
                      : ''}
                  </div>

                  <div className="rule-review-section">
                    <div className="rule-review-actions">
                      <div className="rule-review-btn-group" role="group" aria-label={`Review ${rule.rule_code}`}>
                        <button
                          type="button"
                          className={`review-btn ${currentStatus === 'agree' ? 'active-agree' : ''}`}
                          aria-pressed={currentStatus === 'agree'}
                          disabled={isSaving}
                          onClick={() =>
                            void handleSaveRuleReview(
                              rule,
                              currentStatus === 'agree' ? 'unreviewed' : 'agree'
                            )
                          }
                        >
                          <CheckCircle2 size={13} aria-hidden="true" />
                          Agree
                        </button>

                        <button
                          type="button"
                          className={`review-btn ${
                            currentStatus === 'partially_agree' ? 'active-partial' : ''
                          }`}
                          aria-pressed={currentStatus === 'partially_agree'}
                          disabled={isSaving}
                          onClick={() =>
                            void handleSaveRuleReview(
                              rule,
                              currentStatus === 'partially_agree' ? 'unreviewed' : 'partially_agree'
                            )
                          }
                        >
                          <AlertCircle size={13} aria-hidden="true" />
                          Partially Agree
                        </button>

                        <button
                          type="button"
                          className={`review-btn ${
                            currentStatus === 'disagree' ? 'active-disagree' : ''
                          }`}
                          aria-pressed={currentStatus === 'disagree'}
                          disabled={isSaving}
                          onClick={() =>
                            void handleSaveRuleReview(
                              rule,
                              currentStatus === 'disagree' ? 'unreviewed' : 'disagree'
                            )
                          }
                        >
                          <XCircle size={13} aria-hidden="true" />
                          Disagree
                        </button>

                        <button
                          type="button"
                          className="review-btn"
                          aria-expanded={isCommentOpen}
                          aria-controls={commentInputId}
                          onClick={() =>
                            setOpenCommentBoxes((prev) => ({
                              ...prev,
                              [rule.rule_code]: !isCommentOpen,
                            }))
                          }
                        >
                          <MessageSquare size={13} aria-hidden="true" />
                          {savedComment ? 'Edit Comment' : 'Comment'}
                        </button>
                      </div>

                      {currentStatus !== 'unreviewed' && (
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {isSaving
                            ? 'Saving...'
                            : `Saved · ${rule.reviewer_name || 'Broadcast Reviewer'}`}
                        </span>
                      )}
                    </div>

                    {savedComment && !isCommentOpen && (
                      <div className="review-saved-comment">
                        <strong>Reviewer Note ({rule.reviewer_name || 'Broadcast Reviewer'}):</strong>{' '}
                        {savedComment}
                      </div>
                    )}

                    {isCommentOpen && (
                      <div className="review-comment-editor">
                        <label
                          htmlFor={commentInputId}
                          style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}
                        >
                          {currentStatus === 'partially_agree'
                            ? 'Partially Agree: add conditions, exceptions, or refinements:'
                            : currentStatus === 'disagree'
                            ? 'Disagree: explain why this rule should be modified or removed:'
                            : 'Reviewer comment or production note:'}
                        </label>
                        <textarea
                          id={commentInputId}
                          className="review-comment-textarea"
                          value={draftText}
                          onChange={(e) =>
                            setCommentDrafts((prev) => ({
                              ...prev,
                              [rule.rule_code]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (
                              (e.metaKey || e.ctrlKey) &&
                              e.key === 'Enter' &&
                              !e.nativeEvent.isComposing
                            ) {
                              e.preventDefault();
                              const targetStatus: ReviewStatus =
                                currentStatus === 'unreviewed' ? 'partially_agree' : currentStatus;
                              void handleSaveRuleReview(rule, targetStatus, draftText);
                            }
                          }}
                          placeholder="Add your feedback, edge-case exceptions, or timing adjustments..."
                          maxLength={1000}
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                            Persisted to SQLite & exported SKILL.md
                          </span>
                          <div style={{ display: 'flex', gap: '0.4rem' }}>
                            <button
                              type="button"
                              className="btn"
                              onClick={() =>
                                setOpenCommentBoxes((prev) => ({
                                  ...prev,
                                  [rule.rule_code]: false,
                                }))
                              }
                            >
                              Hide Box
                            </button>
                            <button
                              type="button"
                              className="btn btn-primary"
                              disabled={isSaving}
                              onClick={() => {
                                const targetStatus: ReviewStatus =
                                  currentStatus === 'unreviewed' && draftText.trim()
                                    ? 'partially_agree'
                                    : currentStatus;
                                void handleSaveRuleReview(rule, targetStatus, draftText);
                              }}
                            >
                              {isSaving ? 'Saving...' : 'Save Feedback'}
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 3: SHADOW MODE */}
      {activeTab === 'project-stark' && starkRef && (
        <div className="ResponsiveGridContainer">
          <div className="studio-grid">
            <div className="panel-card">
              <div className="panel-header">
                <h2>PRD Guardrails ({starkRef.backlog.length})</h2>
              </div>
              <div className="event-list">
                {starkRef.backlog.map((item) => (
                  <div key={item.id} className="event-row">
                    <div className="event-row-top">
                      <span className="time-code">{item.cuj}</span>
                      <span className="agent-badge">{formatAgentRoleLabel(item.agent_owner)}</span>
                    </div>
                    <div style={{ fontWeight: 600, fontSize: '0.88rem', marginBottom: '0.25rem' }}>
                      {item.feature}
                    </div>
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                      {item.manual_rule_from_prd}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="panel-card">
              <div className="panel-header">
                <h2>Shadow Mode Diffs</h2>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void handleRunShadowEvolution()}
                  disabled={isLoading}
                >
                  Evolve Skills
                </button>
              </div>

              {starkRef.shadow_mode_batches.map((batch) => (
                <div key={batch.batch_id} className="event-list">
                  {batch.discrepancies_detected.map((d) => (
                    <div key={d.timestamp_mmss} className="event-row">
                      <div className="event-row-top">
                        <span className="time-code">{d.timestamp_mmss}</span>
                        <span className="agent-badge">
                          {d.emergent_rule_synthesized.rule_code}
                        </span>
                      </div>
                      <div
                        style={{
                          fontSize: '0.82rem',
                          color: 'var(--text-muted)',
                          marginBottom: '0.3rem',
                        }}
                      >
                        <strong>Static Rule:</strong> {d.what_static_if_else_did}
                      </div>
                      <div
                        style={{
                          fontSize: '0.82rem',
                          color: 'var(--text-secondary)',
                          marginBottom: '0.4rem',
                        }}
                      >
                        <strong>Human Cut:</strong> {d.what_human_director_actually_did}
                      </div>
                      <div style={{ fontSize: '0.84rem', fontWeight: 500 }}>
                        <strong>Learned:</strong> {d.emergent_rule_synthesized.title}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: SKILLS */}
      {activeTab === 'skills-studio' && skillsBundle && (
        <div className="ResponsiveGridContainer">
          <div className="studio-grid">
            <div className="panel-card">
              <div className="panel-header">
                <h2>Agent SKILL.md</h2>
                {selectedSkillPkg && (
                  <a
                    href={`/api/skills/download/${selectedSkillPkg.skill_name}`}
                    className="btn"
                    style={{ textDecoration: 'none' }}
                  >
                    <Download size={14} />
                    Download
                  </a>
                )}
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: '0.4rem',
                  flexWrap: 'wrap',
                  marginBottom: '1rem',
                }}
              >
                {skillsBundle.packages.map((pkg) => (
                  <button
                    key={pkg.agent_role}
                    type="button"
                    className={`btn ${activeSkillRole === pkg.agent_role ? 'btn-primary' : ''}`}
                    onClick={() => setActiveSkillRole(pkg.agent_role)}
                  >
                    {formatAgentRoleLabel(pkg.agent_role)} ({pkg.rule_count})
                  </button>
                ))}
              </div>

              {selectedSkillPkg && (
                <pre className="code-viewer">{selectedSkillPkg.skill_markdown}</pre>
              )}
            </div>

            <div className="panel-card">
              <div className="panel-header">
                <h2>
                  <Layers size={16} />
                  Antigravity SDK Runner
                </h2>
              </div>
              <pre className="code-viewer">{skillsBundle.antigravity_runner_code}</pre>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: SIMULATOR */}
      {activeTab === 'control-room' && (
        <div className="panel-card">
          <div className="panel-header">
            <h2>Control Room Simulator</h2>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => void handleRunSimulation()}
              disabled={isLoading}
            >
              <Play size={14} />
              Run Agents
            </button>
          </div>

          <div className="form-field" style={{ marginBottom: '1.25rem' }}>
            <label htmlFor="scenario-input">Live Game Scenario</label>
            <input
              id="scenario-input"
              type="text"
              value={simScenario}
              onChange={(e) => setSimScenario(e.target.value)}
            />
          </div>

          {simulationResult && (
            <div className="event-list">
              {simulationResult.edl_steps.map((step) => (
                <div key={step.step_order} className="event-row">
                  <div className="event-row-top">
                    <span className="time-code">
                      +{step.offset_sec}s · {step.game_clock} · {step.matched_kb_rule_code}
                    </span>
                    <span className="agent-badge">{formatAgentRoleLabel(step.invoked_agent)}</span>
                  </div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', marginBottom: '0.25rem' }}>
                    {step.action_command} ({step.camera_or_channel})
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                    {step.reasoning}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 6: ADD VIDEO */}
      {activeTab === 'ingest' && (
        <div className="ResponsiveGridContainer">
          <div className="studio-grid">
            <form className="panel-card" onSubmit={(e) => void handleAnalyzeYoutube(e)}>
              <div className="panel-header">
                <h2>YouTube Broadcast</h2>
              </div>
              <div className="form-grid">
                <div className="form-field">
                  <label htmlFor="yt-url">YouTube URL</label>
                  <input
                    id="yt-url"
                    type="url"
                    required
                    value={ytUrl}
                    onChange={(e) => setYtUrl(e.target.value)}
                  />
                </div>
                <div className="form-field">
                  <label htmlFor="yt-title">Title</label>
                  <input
                    id="yt-title"
                    type="text"
                    required
                    value={ytTitle}
                    onChange={(e) => setYtTitle(e.target.value)}
                  />
                </div>
                <div className="form-field">
                  <label htmlFor="duration-select">Duration</label>
                  <select
                    id="duration-select"
                    value={durationMinutes}
                    onChange={(e) => setDurationMinutes(Number(e.target.value))}
                  >
                    <option value={30}>30 Minutes</option>
                    <option value={45}>45 Minutes</option>
                    <option value={60}>60 Minutes</option>
                  </select>
                </div>
                <div className="form-field">
                  <label htmlFor="proc-mode">Mode</label>
                  <select
                    id="proc-mode"
                    value={processingMode}
                    onChange={(e) => setProcessingMode(e.target.value as 'agentic' | 'static')}
                  >
                    <option value="agentic">Agentic Video Understanding</option>
                    <option value="static">Static Clipping</option>
                  </select>
                </div>
              </div>
              <button type="submit" className="btn btn-primary" disabled={isLoading}>
                Analyze YouTube Video
              </button>
            </form>

            <form className="panel-card" onSubmit={(e) => void handleAnalyzeUpload(e)}>
              <div className="panel-header">
                <h2>Local File (.mp4 / .mov)</h2>
              </div>
              <div className="form-field" style={{ marginBottom: '1.25rem' }}>
                <label htmlFor="video-file-input">Video File</label>
                <input
                  id="video-file-input"
                  type="file"
                  accept="video/mp4,video/quicktime,.mp4,.mov"
                  onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
                />
              </div>
              <button type="submit" className="btn btn-primary" disabled={isLoading}>
                Upload & Analyze
              </button>
            </form>
          </div>

          <div className="panel-card" style={{ marginTop: '1.25rem' }}>
            <div className="panel-header">
              <h2>Analyzed Videos Log ({videos.length})</h2>
              <span className="agent-badge">
                Additive KB ({rules.length} Active Rules · Conflicts Generalized)
              </span>
            </div>
            <div className="table-wrap" style={{ maxHeight: '440px', overflowY: 'auto' }}>
              <table className="clean-table">
                <thead>
                  <tr>
                    <th>Broadcast</th>
                    <th>Source</th>
                    <th>Duration</th>
                    <th>Moments</th>
                    <th>Rule Sync</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.map((v) => (
                    <tr key={v.id}>
                      <td style={{ fontWeight: 600 }}>{v.title}</td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        {v.source_uri}
                      </td>
                      <td>{Math.round(v.duration_seconds / 60)}m</td>
                      <td>
                        <span className="agent-badge">
                          {v.event_count ?? (videoDetail?.id === v.id ? videoDetail.events.length : 99)} Moments
                        </span>
                      </td>
                      <td style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                        Merged into KB
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => {
                            setSelectedVideoId(v.id);
                            setActiveTab('telemetry');
                          }}
                        >
                          Open Edits
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Native HTML <dialog closedby="any"> Modal */}
      <dialog
        ref={inspectorDialogRef}
        closedby="any"
        className="studio-dialog"
        onClick={handleDialogBackdropClick}
      >
        <div className="panel-header">
          <h2>Event JSON</h2>
          <button
            type="button"
            className="btn"
            onClick={() => inspectorDialogRef.current?.close()}
          >
            Close
          </button>
        </div>
        {selectedEvent && (
          <pre className="code-viewer">{JSON.stringify(selectedEvent, null, 2)}</pre>
        )}
      </dialog>
    </div>
  );
}
