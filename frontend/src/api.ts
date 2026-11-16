import type {
  AgentChatAnswerResponse,
  EditorRule,
  MultiAgentSimulationResponse,
  ProjectStarkReferenceResponse,
  ReviewStatus,
  ShadowEvolveResult,
  SkillsBundleResponse,
  VideoDetail,
  VideoSummary,
} from './types';

// Stored strictly in memory (never in localStorage/sessionStorage) per secure coding rules
let csrfTokenMemory: string | null = null;

export async function checkAuthStatus(): Promise<{ authenticated: boolean }> {
  const res = await fetch('/api/auth/status', { credentials: 'include' });
  if (!res.ok) {
    return { authenticated: false };
  }
  const data = (await res.json()) as { authenticated: boolean; csrf_token?: string };
  if (data.csrf_token) {
    csrfTokenMemory = data.csrf_token;
  }
  return { authenticated: Boolean(data.authenticated) };
}

export async function ensureCsrfToken(): Promise<string> {
  if (csrfTokenMemory) {
    return csrfTokenMemory;
  }
  const res = await fetch('/api/auth/status', { credentials: 'include' });
  if (!res.ok) {
    throw new Error('Failed to initialize broadcast session');
  }
  const data = (await res.json()) as { csrf_token: string };
  csrfTokenMemory = data.csrf_token;
  return csrfTokenMemory;
}

export async function loginWithPassword(password: string): Promise<void> {
  const token = await ensureCsrfToken();
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token,
    },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const err = (await res.json().catch(() => ({ detail: 'Invalid access password.' }))) as {
      detail?: string;
    };
    throw new Error(err.detail || 'Invalid access password.');
  }
  const data = (await res.json()) as { csrf_token: string };
  csrfTokenMemory = data.csrf_token;
}

export async function logoutSession(): Promise<void> {
  const token = await ensureCsrfToken().catch(() => '');
  await fetch('/api/auth/logout', {
    method: 'POST',
    credentials: 'include',
    headers: token ? { 'X-CSRF-Token': token } : {},
  });
  csrfTokenMemory = null;
}

function handleUnauthorizedIfNeeded(res: Response): void {
  if (res.status === 401) {
    csrfTokenMemory = null;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('cv-unauthorized'));
    }
  }
}

export async function fetchVideos(): Promise<VideoSummary[]> {
  const res = await fetch('/api/videos', { credentials: 'include' });
  handleUnauthorizedIfNeeded(res);
  if (!res.ok) throw new Error('Failed to load 30-min basketball videos');
  const data = (await res.json()) as { videos: VideoSummary[] };
  return data.videos;
}

export async function fetchVideoDetail(videoId: string): Promise<VideoDetail> {
  const res = await fetch(`/api/videos/${encodeURIComponent(videoId)}`, {
    credentials: 'include',
  });
  handleUnauthorizedIfNeeded(res);
  if (!res.ok) throw new Error('Failed to load video timeline telemetry');
  return res.json();
}

export async function fetchEditorRules(agentRole?: string): Promise<EditorRule[]> {
  const query = agentRole ? `?agent_role=${encodeURIComponent(agentRole)}` : '';
  const res = await fetch(`/api/knowledge-base/rules${query}`, {
    credentials: 'include',
  });
  handleUnauthorizedIfNeeded(res);
  if (!res.ok) throw new Error('Failed to load Editor Knowledge Base rules');
  const data = (await res.json()) as { rules: EditorRule[] };
  return data.rules;
}

export async function fetchAgentSkills(): Promise<SkillsBundleResponse> {
  const res = await fetch('/api/skills', { credentials: 'include' });
  handleUnauthorizedIfNeeded(res);
  if (!res.ok) throw new Error('Failed to load compiled SKILL.md packages');
  return res.json();
}

export async function fetchProjectStarkReference(): Promise<ProjectStarkReferenceResponse> {
  const res = await fetch('/api/project-stark/reference', { credentials: 'include' });
  handleUnauthorizedIfNeeded(res);
  if (!res.ok) throw new Error('Failed to load Project Stark PRD & Feature Backlog');
  return res.json();
}

export async function runShadowModeEvolution(): Promise<ShadowEvolveResult> {
  const token = await ensureCsrfToken();
  const res = await fetch('/api/learning/shadow-evolve', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'X-CSRF-Token': token,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Shadow Mode evolution failed' }));
    throw new Error(err.detail || 'Shadow Mode evolution failed');
  }
  return res.json();
}

export async function simulateBroadcastAgents(params: {
  scenario_name: string;
  game_clock: string;
  period: string;
  shot_clock: number;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  play_stream_description: string;
}): Promise<MultiAgentSimulationResponse> {
  const token = await ensureCsrfToken();
  const res = await fetch('/api/agents/simulate', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token,
    },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Agent simulation failed' }));
    throw new Error(err.detail || 'Agent simulation failed');
  }
  return res.json();
}

export async function analyzeYoutubeBroadcast(params: {
  youtube_url: string;
  title: string;
  processing_mode: 'agentic' | 'static';
  duration_minutes: number;
}): Promise<VideoDetail> {
  const token = await ensureCsrfToken();
  const res = await fetch('/api/videos/youtube', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token,
    },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'YouTube broadcast analysis failed' }));
    throw new Error(err.detail || 'YouTube broadcast analysis failed');
  }
  const data = (await res.json()) as { video: VideoDetail };
  return data.video;
}

export async function analyzeUploadedBroadcast(params: {
  file: File;
  title: string;
  processing_mode: 'agentic' | 'static';
  duration_minutes: number;
}): Promise<VideoDetail> {
  const token = await ensureCsrfToken();
  const formData = new FormData();
  formData.append('file', params.file);
  formData.append('title', params.title);
  formData.append('processing_mode', params.processing_mode);
  formData.append('duration_minutes', String(params.duration_minutes));

  const res = await fetch('/api/videos/upload', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'X-CSRF-Token': token,
    },
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Video upload analysis failed' }));
    throw new Error(err.detail || 'Video upload analysis failed');
  }
  const data = (await res.json()) as { video: VideoDetail };
  return data.video;
}

export async function askBroadcastAgent(question: string): Promise<AgentChatAnswerResponse> {
  const token = await ensureCsrfToken();
  const res = await fetch('/api/agents/ask', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': token,
    },
    body: JSON.stringify({ question }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Agent question failed' }));
    throw new Error(err.detail || 'Agent question failed');
  }
  return res.json();
}

export async function submitRuleReview(
  ruleCode: string,
  payload: {
    review_status: ReviewStatus;
    reviewer_comment: string;
    reviewer_name?: string;
  }
): Promise<{ rule: EditorRule; review_summary: Record<string, number>; skills_updated: boolean }> {
  const token = await ensureCsrfToken();
  const res = await fetch(
    `/api/knowledge-base/rules/${encodeURIComponent(ruleCode)}/review`,
    {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': token,
      },
      body: JSON.stringify(payload),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Failed to save rule review' }));
    throw new Error(err.detail || 'Failed to save rule review');
  }
  return res.json();
}


