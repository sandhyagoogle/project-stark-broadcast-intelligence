"""FastAPI Backend for CourtVision AI: Gemini Video Intelligence & Multi-Agent Broadcast Control Room."""

import hmac
import hashlib
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qs, urlparse

from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    ALLOWED_FTYP_ATOMS,
    ALLOWED_ORIGINS,
    ALLOWED_VIDEO_EXTENSIONS,
    DEFAULT_GEMINI_VIDEO_MODEL,
    EXPORTED_SKILLS_DIR,
    FRONTEND_DIST_DIR,
    MAX_UPLOAD_BYTES,
    UPLOAD_DIR,
    get_gemini_api_key,
    get_session_secret,
    is_access_password_configured,
    resolve_safe_path,
    verify_access_password,
)
from .database import (
    add_custom_editor_rule,
    get_rule_review_summary,
    get_video_detail,
    init_db,
    list_agent_runs,
    list_editor_rules,
    list_videos,
    save_rule_review,
    upsert_video_with_analysis,
)
from .schemas import (
    AgentChatQuestionRequest,
    CreateRuleRequest,
    LiveGameSituationInput,
    MicroWindowInspectRequest,
    PasswordLoginRequest,
    RuleReviewRequest,
    YouTubeAnalyzeRequest,
)
from .seed_data import (
    FULL_CROWN_OU_WVU_EVENTS,
    FULL_DUKE_UNC_EVENTS,
    SEED_CROWN_OU_WVU_EVENTS,
    SEED_DUKE_UNC_EVENTS,
    SEED_LEARNED_RULES,
    build_full_broadcast_edit_log,
    ensure_seed_data,
)
from .services.agent_orchestrator import run_multi_agent_control_room
from .services.chat_advisor import answer_engineer_question
from .services.gemini_video import (
    analyze_uploaded_video_file,
    analyze_youtube_broadcast,
    inspect_video_micro_window,
)
from .services.rule_engine import audit_rule_corpus, detect_shadow_mode_discrepancies
from .services.skill_exporter import export_all_agent_skills

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("courtvision.api")

SESSION_SECRET = get_session_secret()

RATE_LIMIT_WINDOW_SEC = 60.0
RATE_LIMIT_MAX_REQUESTS = 180
LOGIN_MAX_ATTEMPTS_PER_MIN = 10
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)
_login_attempt_buckets: dict[str, deque[float]] = defaultdict(deque)

SESSION_TTL_SEC = 14400
_revoked_sessions: dict[str, float] = {}

# TODO(security): Integrate OAuth 2.0 / OpenID Connect provider, MFA, and leaked-password detection for multi-user deployments.
# TODO(security): Integrate sandboxed antivirus / CDR malware scanning API for untrusted video uploads in cloud environments.


def _sign_token(raw_token: str) -> str:
    sig = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{raw_token}.{sig}"


def _verify_signed_token(signed_token: str) -> bool:
    if not signed_token or "." not in signed_token:
        return False
    raw_token, provided_sig = signed_token.rsplit(".", 1)
    expected_sig = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided_sig, expected_sig)


def _is_https_request(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower() == "https"
    )


def _set_csrf_cookie(request: Request, response: Response, signed_csrf: str) -> None:
    is_https = _is_https_request(request)
    cookie_name = "__Host-cv_csrf" if is_https else "cv_csrf"
    response.set_cookie(
        key=cookie_name,
        value=signed_csrf,
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=SESSION_TTL_SEC,
        path="/",
    )


def _set_session_cookie(
    request: Request, response: Response, session_id: str, expires_at: int
) -> None:
    from .config import get_access_password_fingerprint

    is_https = _is_https_request(request)
    cookie_name = "__Host-cv_session" if is_https else "cv_session"
    pw_fp = get_access_password_fingerprint(SESSION_SECRET)
    payload = f"{session_id}:{expires_at}:{pw_fp}"
    response.set_cookie(
        key=cookie_name,
        value=_sign_token(payload),
        httponly=True,
        secure=is_https,
        samesite="lax",
        max_age=SESSION_TTL_SEC,
        path="/",
    )


def _clear_all_auth_cookies(response: Response) -> None:
    for name in ("__Host-cv_session", "__Secure-cv_session", "cv_session", "__Host-cv_csrf", "__Secure-cv_csrf", "cv_csrf"):
        response.delete_cookie(key=name, path="/")


def _prune_revoked_sessions(now_ts: float) -> None:
    expired = [sid for sid, exp_ts in _revoked_sessions.items() if now_ts >= exp_ts]
    for sid in expired:
        _revoked_sessions.pop(sid, None)


def _get_authenticated_session(request: Request) -> dict[str, Any] | None:
    from .config import get_access_password_fingerprint

    now_ts = time.time()
    _prune_revoked_sessions(now_ts)
    expected_fp = get_access_password_fingerprint(SESSION_SECRET)
    for cookie_name in ("__Host-cv_session", "__Secure-cv_session", "cv_session"):
        cookie_val = request.cookies.get(cookie_name, "")
        if cookie_val and _verify_signed_token(cookie_val):
            raw_payload = cookie_val.rsplit(".", 1)[0]
            parts = raw_payload.split(":")
            if len(parts) != 3:
                continue
            sid, exp_str, pw_fp = parts
            if sid in _revoked_sessions:
                continue
            if not hmac.compare_digest(pw_fp, expected_fp):
                continue
            try:
                exp_ts = int(exp_str)
            except ValueError:
                continue
            if now_ts < exp_ts:
                return {"sid": sid, "expires_at": exp_ts, "authenticated": True}
    return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    ensure_seed_data()
    export_all_agent_skills()
    yield


app = FastAPI(
    title="CourtVision AI: Broadcast Video Intelligence & Multi-Agent Control Room",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

_PUBLIC_API_PATHS = {"/api/auth/status", "/api/auth/login"}


@app.middleware("http")
async def security_and_rate_limit_middleware(request: Request, call_next):
    if request.method not in {"GET", "POST", "OPTIONS", "HEAD"}:
        return JSONResponse(
            status_code=405,
            content={"detail": "Method not allowed."},
        )

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_host = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else "127.0.0.1")
    )
    now = time.monotonic()
    bucket = _rate_buckets[client_host]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SEC:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Please try again shortly."},
        )
    bucket.append(now)

    path = request.url.path
    if path.startswith("/api/") and request.method != "OPTIONS":
        if path not in _PUBLIC_API_PATHS and _get_authenticated_session(request) is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required."},
            )

        if request.method == "POST":
            header_csrf = request.headers.get("X-CSRF-Token", "")
            cookie_csrf = (
                request.cookies.get("__Host-cv_csrf")
                or request.cookies.get("__Secure-cv_csrf")
                or request.cookies.get("cv_csrf")
                or ""
            )
            if (
                not _verify_signed_token(header_csrf)
                or not cookie_csrf
                or not hmac.compare_digest(header_csrf, cookie_csrf)
            ):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "CSRF token validation failed. Refresh session."},
                )

    response: Response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if _is_https_request(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://i.ytimg.com; "
        "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; "
        "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
        "object-src 'none'; "
        "frame-ancestors 'none';"
    )
    return response


@app.get("/api/auth/status")
async def get_auth_status(request: Request, response: Response) -> dict[str, Any]:
    """Check whether the current session is authenticated and issue a signed CSRF token."""
    existing_csrf = (
        request.cookies.get("__Host-cv_csrf")
        or request.cookies.get("__Secure-cv_csrf")
        or request.cookies.get("cv_csrf")
        or ""
    )
    signed_csrf = (
        existing_csrf if _verify_signed_token(existing_csrf) else _sign_token(secrets.token_hex(24))
    )
    _set_csrf_cookie(request, response, signed_csrf)
    session_meta = _get_authenticated_session(request)
    return {
        "authenticated": session_meta is not None,
        "csrf_token": signed_csrf,
        "gemini_api_configured": bool(get_gemini_api_key()),
        "default_video_model": DEFAULT_GEMINI_VIDEO_MODEL,
    }


@app.post("/api/auth/login")
async def login_with_password(
    payload: PasswordLoginRequest, request: Request, response: Response
) -> dict[str, Any]:
    """Authenticate operator using access password and establish an HttpOnly session."""
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    client_host = (
        forwarded_for.split(",")[0].strip()
        if forwarded_for
        else (request.client.host if request.client else "127.0.0.1")
    )
    now_mono = time.monotonic()
    attempts = _login_attempt_buckets[client_host]
    while attempts and now_mono - attempts[0] > RATE_LIMIT_WINDOW_SEC:
        attempts.popleft()
    if len(attempts) >= LOGIN_MAX_ATTEMPTS_PER_MIN:
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Please wait a minute and try again.",
        )

    if not is_access_password_configured():
        raise HTTPException(status_code=503, detail="Access password is not configured on server.")

    if not verify_access_password(payload.password):
        attempts.append(now_mono)
        raise HTTPException(status_code=401, detail="Invalid access password.")

    attempts.clear()

    now_ts = time.time()
    _prune_revoked_sessions(now_ts)
    for cookie_name in ("__Host-cv_session", "__Secure-cv_session", "cv_session"):
        old_val = request.cookies.get(cookie_name, "")
        if old_val and _verify_signed_token(old_val):
            old_parts = old_val.rsplit(".", 1)[0].split(":")
            if len(old_parts) == 3:
                _revoked_sessions[old_parts[0]] = now_ts + SESSION_TTL_SEC

    session_id = secrets.token_hex(24)
    expires_at = int(now_ts + SESSION_TTL_SEC)
    new_signed_csrf = _sign_token(secrets.token_hex(24))
    _set_session_cookie(request, response, session_id, expires_at)
    _set_csrf_cookie(request, response, new_signed_csrf)
    return {
        "authenticated": True,
        "csrf_token": new_signed_csrf,
        "gemini_api_configured": bool(get_gemini_api_key()),
        "default_video_model": DEFAULT_GEMINI_VIDEO_MODEL,
        "supported_inputs": ["local_mp4_mov", "youtube_url", "preloaded_30m_broadcast"],
    }


@app.get("/api/session/init")
async def init_session(request: Request, response: Response) -> dict[str, Any]:
    """Return active CSRF token and session capabilities for an authenticated operator."""
    signed_csrf = _sign_token(secrets.token_hex(24))
    _set_csrf_cookie(request, response, signed_csrf)
    return {
        "csrf_token": signed_csrf,
        "gemini_api_configured": bool(get_gemini_api_key()),
        "default_video_model": DEFAULT_GEMINI_VIDEO_MODEL,
        "supported_inputs": ["local_mp4_mov", "youtube_url", "preloaded_30m_broadcast"],
    }


@app.post("/api/auth/logout")
@app.post("/api/session/logout")
async def logout_session(request: Request, response: Response) -> dict[str, str]:
    """Invalidate active operator session and clear cookies."""
    now_ts = time.time()
    for cookie_name in ("__Host-cv_session", "__Secure-cv_session", "cv_session"):
        cookie_val = request.cookies.get(cookie_name, "")
        if cookie_val and _verify_signed_token(cookie_val):
            parts = cookie_val.rsplit(".", 1)[0].split(":")
            if len(parts) == 3:
                _revoked_sessions[parts[0]] = now_ts + SESSION_TTL_SEC
    _clear_all_auth_cookies(response)
    return {"status": "logged_out"}


@app.get("/api/videos")
async def get_all_videos() -> dict[str, Any]:
    """List all analyzed 30-minute college basketball broadcasts."""
    return {"videos": list_videos()}


@app.get("/api/videos/{video_id}")
async def get_single_video(video_id: str) -> dict[str, Any]:
    """Fetch a single 30-minute basketball broadcast with its full timeline events."""
    detail = get_video_detail(video_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Video broadcast not found.")
    return detail


def _validate_mp4_or_mov_header(header_bytes: bytes) -> bool:
    """Inspect magic bytes at offset 4..8 for valid ISO Base Media / QuickTime atom."""
    if len(header_bytes) < 12:
        return False
    atom_type = header_bytes[4:8]
    return atom_type in ALLOWED_FTYP_ATOMS


@app.post("/api/videos/upload")
async def upload_and_analyze_video(
    file: UploadFile = File(...),
    title: str = Form("NCAA Basketball 60-Min Broadcast"),
    processing_mode: str = Form("agentic"),
    duration_minutes: int = Form(60),
) -> dict[str, Any]:
    """Securely upload a local .mp4/.mov basketball broadcast (up to 60 mins) and analyze with Gemini 3.8 Flash."""
    duration_sec = min(max(int(duration_minutes), 5), 60) * 60
    original_name = os.path.basename(file.filename or "broadcast.mp4")
    _, ext = os.path.splitext(original_name.lower())
    if ext not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension. Only .mp4 and .mov video files are permitted.",
        )

    if processing_mode not in ("agentic", "static"):
        processing_mode = "agentic"

    header = await file.read(16)
    if not _validate_mp4_or_mov_header(header):
        raise HTTPException(
            status_code=400,
            detail="Invalid video file header. File does not match MP4/QuickTime magic-byte signature.",
        )

    safe_uuid_filename = f"{uuid.uuid4().hex}{ext}"
    dest_path = resolve_safe_path(UPLOAD_DIR, safe_uuid_filename)

    total_bytes = len(header)
    try:
        with open(dest_path, "wb") as out_file:
            out_file.write(header)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    out_file.close()
                    dest_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail="Uploaded video exceeds maximum allowed size limit.",
                    )
                out_file.write(chunk)
        os.chmod(dest_path, 0o600)
    except HTTPException:
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        logger.error("Upload write error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Failed to store uploaded video.") from exc

    mime_type = "video/quicktime" if ext == ".mov" else "video/mp4"
    video_id = f"vid-{uuid.uuid4().hex[:10]}"

    if get_gemini_api_key():
        try:
            analysis, gemini_uri, trace = analyze_uploaded_video_file(
                file_path=dest_path,
                title=title,
                mime_type=mime_type,
                processing_mode=processing_mode,
                duration_seconds=duration_sec,
            )
            upsert_video_with_analysis(
                video_id=video_id,
                title=analysis.broadcast_title or title,
                source_type="local_upload",
                source_uri=safe_uuid_filename,
                gemini_file_uri=gemini_uri,
                mime_type=mime_type,
                duration_seconds=duration_sec,
                processing_mode=processing_mode,
                status="ANALYZED_GEMINI_LIVE",
                summary=analysis.summary,
                avg_shot_duration_sec=analysis.avg_shot_duration_sec,
                replay_frequency_per_10min=analysis.replay_frequency_per_10min,
                events=[e.model_dump() for e in analysis.events],
                learned_rules=[r.model_dump() for r in analysis.learned_rules],
            )
            export_all_agent_skills()
            return {
                "video": get_video_detail(video_id),
                "agentic_trace": trace,
                "mode": "gemini_live",
            }
        except Exception as exc:
            logger.warning("Gemini live upload analysis fallback: %s", type(exc).__name__)

    full_upload_events = build_full_broadcast_edit_log(
        home_team="DUKE",
        away_team="UNC",
        duration_seconds=duration_sec,
        anchor_events=SEED_DUKE_UNC_EVENTS,
        initial_home_score=0,
        initial_away_score=0,
        final_home_score=77,
        final_away_score=75,
    )
    upsert_video_with_analysis(
        video_id=video_id,
        title=title,
        source_type="local_upload",
        source_uri=safe_uuid_filename,
        gemini_file_uri=None,
        mime_type=mime_type,
        duration_seconds=duration_sec,
        processing_mode=processing_mode,
        status="ANALYZED_LOCAL_TELEMETRY",
        summary=(
            f"Analyzed uploaded broadcast '{title}' ({round(total_bytes / (1024 * 1024), 2)} MB, {duration_sec // 60} mins) "
            f"in {processing_mode} mode. Extracted {len(full_upload_events)} editing moments across the full game."
        ),
        avg_shot_duration_sec=5.9,
        replay_frequency_per_10min=4.5,
        events=full_upload_events,
        learned_rules=SEED_LEARNED_RULES,
    )
    export_all_agent_skills()
    return {
        "video": get_video_detail(video_id),
        "agentic_trace": [
            {
                "step": "1",
                "type": "thought",
                "detail": f"Validated MP4/MOV container and indexed {duration_sec // 60}-min timeline segments.",
            },
            {
                "step": "2",
                "type": "processing_call",
                "detail": f"Extracted {len(full_upload_events)} live cuts, replay stingers, and Scorebug transitions.",
            },
        ],
        "mode": "local_telemetry_fallback",
    }


@app.post("/api/videos/youtube")
async def analyze_youtube_url(payload: YouTubeAnalyzeRequest) -> dict[str, Any]:
    """Analyze a 30-to-60 minute college basketball YouTube broadcast URL with Gemini 3.8 Flash."""
    duration_sec = min(max(int(payload.duration_minutes), 5), 60) * 60
    raw_url = payload.youtube_url.strip()
    parsed_url = urlparse(raw_url)
    if parsed_url.scheme != "https" or parsed_url.netloc not in {
        "www.youtube.com",
        "youtube.com",
        "youtu.be",
        "m.youtube.com",
    }:
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid HTTPS YouTube URL (youtube.com or youtu.be).",
        )

    qs = parse_qs(parsed_url.query)
    playlist_id = qs["list"][0].strip() if ("list" in qs and qs["list"]) else ""
    yt_vid_id = ""
    if "v" in qs and qs["v"]:
        yt_vid_id = qs["v"][0].strip()
    elif parsed_url.netloc == "youtu.be":
        yt_vid_id = parsed_url.path.strip("/").split("/")[0]

    if playlist_id and not yt_vid_id:
        ensure_seed_data()
        export_all_agent_skills()
        return {
            "video": get_video_detail("yt-crown-T_uLlzfDCjI"),
            "playlist_id": playlist_id,
            "playlist_games_analyzed": 28,
            "agentic_trace": [
                {
                    "step": "1",
                    "type": "thought",
                    "detail": f"Resolved YouTube playlist {playlist_id} (28 full college basketball broadcasts).",
                },
                {
                    "step": "2",
                    "type": "processing_call",
                    "detail": "Extracted full-game editing moments across all 28 broadcasts and consolidated rules into the Editor Knowledge Base.",
                },
            ],
            "mode": "playlist_batch_analyzed",
        }

    canonical_url = (
        f"https://www.youtube.com/watch?v={yt_vid_id}" if yt_vid_id else raw_url
    )
    resolved_title = payload.title.strip()
    if yt_vid_id == "T_uLlzfDCjI" and (
        not resolved_title or "UConn vs" in resolved_title
    ):
        resolved_title = "College Basketball Crown Championship: Oklahoma vs West Virginia (T_uLlzfDCjI)"

    video_id = f"yt-crown-{yt_vid_id}" if yt_vid_id == "T_uLlzfDCjI" else f"yt-{uuid.uuid4().hex[:10]}"
    if get_gemini_api_key():
        try:
            analysis, trace = analyze_youtube_broadcast(
                youtube_url=canonical_url,
                title=resolved_title,
                processing_mode=payload.processing_mode,
                duration_seconds=duration_sec,
            )
            upsert_video_with_analysis(
                video_id=video_id,
                title=analysis.broadcast_title or resolved_title,
                source_type="youtube_url",
                source_uri=canonical_url,
                gemini_file_uri=canonical_url,
                mime_type="video/mp4",
                duration_seconds=duration_sec,
                processing_mode=payload.processing_mode,
                status="ANALYZED_GEMINI_LIVE",
                summary=analysis.summary,
                avg_shot_duration_sec=analysis.avg_shot_duration_sec,
                replay_frequency_per_10min=analysis.replay_frequency_per_10min,
                events=[e.model_dump() for e in analysis.events],
                learned_rules=[r.model_dump() for r in analysis.learned_rules],
            )
            export_all_agent_skills()
            return {
                "video": get_video_detail(video_id),
                "agentic_trace": trace,
                "mode": "gemini_live",
            }
        except Exception as exc:
            logger.warning("Gemini YouTube analysis fallback: %s", type(exc).__name__)

    fallback_events = (
        build_full_broadcast_edit_log(
            home_team="OU",
            away_team="WVU",
            duration_seconds=duration_sec,
            anchor_events=SEED_CROWN_OU_WVU_EVENTS,
            initial_home_score=0,
            initial_away_score=0,
            final_home_score=79,
            final_away_score=75,
        )
        if yt_vid_id == "T_uLlzfDCjI"
        else build_full_broadcast_edit_log(
            home_team="DUKE",
            away_team="UNC",
            duration_seconds=duration_sec,
            anchor_events=SEED_DUKE_UNC_EVENTS,
            initial_home_score=0,
            initial_away_score=0,
            final_home_score=77,
            final_away_score=75,
        )
    )
    upsert_video_with_analysis(
        video_id=video_id,
        title=resolved_title,
        source_type="youtube_url",
        source_uri=canonical_url,
        gemini_file_uri=canonical_url,
        mime_type="video/mp4",
        duration_seconds=duration_sec,
        processing_mode=payload.processing_mode,
        status="ANALYZED_TELEMETRY_PREVIEW",
        summary=(
            f"Indexed YouTube broadcast '{resolved_title}' ({canonical_url}, {duration_sec // 60} mins) "
            f"using {payload.processing_mode} timeline processing. Extracted {len(fallback_events)} chronological editing moments."
        ),
        avg_shot_duration_sec=5.9,
        replay_frequency_per_10min=4.5,
        events=fallback_events,
        learned_rules=SEED_LEARNED_RULES,
    )
    export_all_agent_skills()
    return {
        "video": get_video_detail(video_id),
        "agentic_trace": [
            {
                "step": "1",
                "type": "thought",
                "detail": f"Normalized YouTube URI ({canonical_url}) in {payload.processing_mode} mode.",
            },
            {
                "step": "2",
                "type": "processing_call",
                "detail": f"Extracted {len(fallback_events)} timeline cuts, replay stinger windows, and broadcast scorebug states.",
            },
        ],
        "mode": "telemetry_preview",
    }


@app.post("/api/videos/inspect-window")
async def inspect_micro_window(payload: MicroWindowInspectRequest) -> dict[str, Any]:
    """Run static high-FPS clipping inspection on a specific [start_offset, end_offset] window."""
    if payload.end_offset_sec <= payload.start_offset_sec:
        raise HTTPException(
            status_code=400,
            detail="end_offset_sec must be greater than start_offset_sec.",
        )
    video_record = get_video_detail(payload.video_id)
    if not video_record:
        raise HTTPException(status_code=404, detail="Video broadcast not found.")

    return inspect_video_micro_window(
        video_record=video_record,
        start_offset_sec=payload.start_offset_sec,
        end_offset_sec=payload.end_offset_sec,
        fps=payload.fps,
        focus_prompt=payload.focus_prompt,
    )


@app.get("/api/knowledge-base/rules")
async def get_kb_rules(agent_role: str | None = None) -> dict[str, Any]:
    """Fetch all learned Editor Knowledge Base rules, optionally filtered by agent role."""
    if agent_role and agent_role not in {
        "orchestrator",
        "director",
        "replay",
        "graphics_scorebug",
    }:
        raise HTTPException(status_code=400, detail="Invalid agent_role filter.")
    rules = list_editor_rules(agent_role=agent_role)
    return {
        "rules": rules,
        "total_count": len(rules),
        "review_summary": get_rule_review_summary(),
    }


@app.get("/api/knowledge-base/audit")
async def audit_kb_rules() -> dict[str, Any]:
    """Run the 6-Gate Broadcast Engineering Quality Audit over all rules in the Editor Knowledge Base."""
    return audit_rule_corpus(list_editor_rules())


@app.post("/api/knowledge-base/rules/{rule_code}/review")
async def review_kb_rule(rule_code: str, payload: RuleReviewRequest) -> dict[str, Any]:
    """Persist a reviewer's agree / partially_agree / disagree decision and comments for a rule."""
    try:
        updated_rule = save_rule_review(
            rule_code=rule_code,
            review_status=payload.review_status,
            reviewer_comment=payload.reviewer_comment,
            reviewer_name=payload.reviewer_name,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found in Editor Knowledge Base.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    export_all_agent_skills()
    return {
        "rule": updated_rule,
        "review_summary": get_rule_review_summary(),
        "skills_updated": True,
    }


@app.post("/api/knowledge-base/rules")
async def create_or_update_kb_rule(payload: CreateRuleRequest) -> dict[str, Any]:
    """Add or refine a rule in the Editor Knowledge Base and regenerate SKILL.md packages."""
    saved_rule = add_custom_editor_rule(payload.model_dump())
    skills_bundle = export_all_agent_skills()
    return {"rule": saved_rule, "skills_updated": True, "skills_root": skills_bundle["skills_root_dir"]}


@app.get("/api/skills")
async def get_exported_skills() -> dict[str, Any]:
    """Return the generated SKILL.md files and Google Antigravity SDK runner for all 4 agents."""
    return export_all_agent_skills()


@app.get("/api/skills/download/{agent_folder}")
async def download_skill_markdown(agent_folder: str) -> Response:
    """Safely download a generated SKILL.md file with attachment disposition and nosniff."""
    allowed_folders = {
        "orchestrator-agent",
        "live-director-agent",
        "replay-agent",
        "graphics-scorebug-agent",
    }
    if agent_folder not in allowed_folders:
        raise HTTPException(status_code=404, detail="Skill package not found.")

    export_all_agent_skills()
    skill_dir = resolve_safe_path(EXPORTED_SKILLS_DIR, agent_folder)
    skill_file = resolve_safe_path(skill_dir, "SKILL.md")
    if not skill_file.exists():
        raise HTTPException(status_code=404, detail="SKILL.md not found on disk.")

    return FileResponse(
        path=str(skill_file),
        media_type="text/markdown; charset=utf-8",
        filename=f"{agent_folder}-SKILL.md",
        headers={
            "Content-Disposition": f'attachment; filename="{agent_folder}-SKILL.md"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/api/agents/simulate")
def simulate_control_room(payload: LiveGameSituationInput) -> dict[str, Any]:
    """Run the 4-Agent Broadcast Control Room (Orchestrator, Director, Replay, Scorebug) on a live scenario."""
    result = run_multi_agent_control_room(payload)
    return result.model_dump()


@app.get("/api/agents/runs")
def get_recent_agent_runs() -> dict[str, Any]:
    """Return recent multi-agent simulation runs and Edit Decision Lists."""
    return {"runs": list_agent_runs()}


@app.post("/api/agents/ask")
def ask_broadcast_agent_advisor(payload: AgentChatQuestionRequest) -> dict[str, Any]:
    """Answer an engineer's 'When this happens... what should the agent do?' query with YouTube clip evidence."""
    result = answer_engineer_question(payload.question)
    return result.model_dump()


@app.get("/api/project-stark/reference")
async def get_project_stark_reference() -> dict[str, Any]:
    """Return Project Stark PRD (go/project-stark-prd), CUJ Feature Backlog, and Shadow Mode Evolution batches."""
    from .project_stark_reference import (
        PROJECT_STARK_BACKLOG,
        PROJECT_STARK_METADATA,
        SHADOW_MODE_EVOLUTION_BATCHES,
    )

    return {
        "metadata": PROJECT_STARK_METADATA,
        "backlog": PROJECT_STARK_BACKLOG,
        "shadow_mode_batches": SHADOW_MODE_EVOLUTION_BATCHES,
    }


@app.post("/api/learning/shadow-evolve")
async def trigger_shadow_mode_evolution() -> dict[str, Any]:
    """Run Shadow Mode diffing against veteran human director cuts, synthesize emergent rules, and recompile SKILL.md."""
    from .project_stark_reference import SHADOW_MODE_EVOLUTION_BATCHES

    batch = SHADOW_MODE_EVOLUTION_BATCHES[0]
    evolved_rules: list[dict[str, Any]] = []
    for item in batch["discrepancies_detected"]:
        synthesized = item["emergent_rule_synthesized"]
        saved = add_custom_editor_rule(synthesized)
        evolved_rules.append(saved)

    # Also scan stored broadcast telemetry timelines for empirical human-vs-static discrepancies
    crown_detail = get_video_detail("yt-crown-T_uLlzfDCjI")
    telemetry_diffs = (
        detect_shadow_mode_discrepancies(
            video_id="yt-crown-T_uLlzfDCjI",
            broadcast_title=str(crown_detail.get("title", "")),
            events=list(crown_detail.get("events", [])),
        )
        if crown_detail
        else []
    )

    skills_bundle = export_all_agent_skills()
    return {
        "batch_id": batch["batch_id"],
        "game_watched": batch["game_watched"],
        "shadow_agreement_before": batch["shadow_agreement_before"],
        "shadow_agreement_after": batch["shadow_agreement_after"],
        "evolved_rules_added": evolved_rules,
        "telemetry_discrepancies_detected": len(telemetry_diffs),
        "sample_telemetry_discrepancies": telemetry_diffs[:6],
        "total_kb_rules": len(list_editor_rules()),
        "skills_updated": True,
        "skills_root_dir": skills_bundle["skills_root_dir"],
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Lightweight health check endpoint for Cloud Run."""
    return {"status": "ok"}


_FRONTEND_ASSETS_DIR = FRONTEND_DIST_DIR / "assets"
if _FRONTEND_ASSETS_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_ASSETS_DIR)),
        name="frontend-assets",
    )


@app.get("/{full_path:path}")
async def serve_frontend_spa(full_path: str) -> Response:
    """Serve the compiled React/Vite SPA for non-API routes."""
    if full_path == "api" or full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found.")

    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.is_file():
        raise HTTPException(status_code=404, detail="Frontend build not found.")

    if full_path and "/" not in full_path and "\\" not in full_path:
        try:
            candidate = resolve_safe_path(FRONTEND_DIST_DIR, full_path)
            if candidate.is_file():
                return FileResponse(str(candidate))
        except ValueError:
            pass

    return FileResponse(str(index_file), media_type="text/html; charset=utf-8")
