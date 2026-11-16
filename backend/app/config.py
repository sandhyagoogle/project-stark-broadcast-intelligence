"""Secure configuration and path boundaries for CourtVision AI."""

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger("courtvision.config")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
STORAGE_DIR = (BASE_DIR / "storage").resolve()
UPLOAD_DIR = (STORAGE_DIR / "uploads").resolve()
DB_PATH = (STORAGE_DIR / "courtvision.db").resolve()
EXPORTED_SKILLS_DIR = (BASE_DIR / "exported_skills").resolve()
FRONTEND_DIST_DIR = (BASE_DIR / "frontend" / "dist").resolve()

# Ensure isolated storage directories exist with restricted permissions (0o700)
for directory in (STORAGE_DIR, UPLOAD_DIR, EXPORTED_SKILLS_DIR):
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

# Allowed video extensions and magic-byte signatures for MP4 / QuickTime MOV
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov"}
# ISO Base Media File Format / QuickTime atoms at offset 4..8
ALLOWED_FTYP_ATOMS = {b"ftyp", b"moov", b"wide", b"mdat", b"free", b"skip"}

# Maximum upload size: 500 MB default for local standalone safety (configurable)
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))

# Allowed origins for strict CORS policy (never wildcard *)
_EXTRA_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip() and origin.strip() != "*"
]
ALLOWED_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
    "http://127.0.0.1:8000",
    *_EXTRA_ORIGINS,
]

# Gemini models (strictly current SDK models; never legacy 2.5/2.0/1.5)
DEFAULT_GEMINI_VIDEO_MODEL = "gemini-3.8-flash"
REASONING_GEMINI_MODEL = "gemini-4-argon"


_EXTERNAL_ENV_KEYS = frozenset(os.environ.keys())


def _read_dotenv_value(target_key: str) -> str | None:
    dotenv_path = BASE_DIR / ".env"
    if not dotenv_path.is_file():
        return None
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == target_key:
                cleaned = val.strip().strip('"').strip("'")
                return cleaned if cleaned else None
    except OSError:
        return None
    return None


def _load_dotenv_if_present() -> None:
    """Load local gitignored .env key-value pairs without overriding existing environment variables."""
    dotenv_path = BASE_DIR / ".env"
    if not dotenv_path.is_file():
        return
    try:
        for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            clean_key = key.strip()
            clean_val = val.strip().strip('"').strip("'")
            if clean_key and clean_key not in os.environ:
                os.environ[clean_key] = clean_val
    except OSError:
        pass


_load_dotenv_if_present()


def get_session_secret() -> str:
    """Resolve session/CSRF signing secret without hardcoded literals."""
    env_secret = os.getenv("COURTVISION_SESSION_SECRET")
    if env_secret:
        return env_secret
    secret_file = STORAGE_DIR / "session_secret.txt"
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    logger.warning(
        "Generating ephemeral session secret. Instance-isolated for local standalone mode!"
    )
    return secrets.token_hex(32)


def _read_configured_access_password() -> str | None:
    """Resolve operator access password from environment or isolated local file (never hardcoded)."""
    env_pw = os.getenv("COURTVISION_ACCESS_PASSWORD")
    if env_pw and env_pw.strip() and (
        "COURTVISION_ACCESS_PASSWORD" in _EXTERNAL_ENV_KEYS or not (BASE_DIR / ".env").is_file()
    ):
        return env_pw.strip()
    dotenv_pw = _read_dotenv_value("COURTVISION_ACCESS_PASSWORD")
    if env_pw and env_pw.strip() and dotenv_pw and env_pw.strip() != dotenv_pw:
        # Respect runtime monkeypatch overrides (e.g. pytest) when os.environ differs from initial .env load
        return env_pw.strip()
    if dotenv_pw:
        return dotenv_pw
    if env_pw and env_pw.strip():
        return env_pw.strip()
    pw_file = STORAGE_DIR / "access_password.txt"
    if pw_file.is_file():
        val = pw_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    return None


def is_access_password_configured() -> bool:
    """Return True when an access password is configured in environment or secret storage."""
    return _read_configured_access_password() is not None


def get_access_password_fingerprint(signing_secret: str) -> str:
    """Return short HMAC fingerprint of the active access password so rotating the password invalidates prior cookies."""
    import hashlib
    import hmac

    expected = _read_configured_access_password() or ""
    return hmac.new(
        signing_secret.encode("utf-8"),
        f"pw-fp:{expected}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:16]


def verify_access_password(candidate: str) -> bool:
    """Verify candidate password using memory-hard scrypt and constant-time comparison (fail-closed)."""
    import hashlib
    import hmac

    expected = _read_configured_access_password()
    if not expected:
        return False
    provided = (candidate or "").strip()
    if not provided:
        return False
    salt = secrets.token_bytes(16)
    expected_dk = hashlib.scrypt(
        expected.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    provided_dk = hashlib.scrypt(
        provided.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32
    )
    return hmac.compare_digest(provided_dk, expected_dk)


def get_gemini_api_key() -> str | None:
    """Read GEMINI_API_KEY from environment only (never hardcoded)."""
    key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if key and key.strip():
        return key.strip()
    return None


def resolve_safe_path(base_dir: Path, filename: str) -> Path:
    """Strictly sanitize a filename and enforce directory boundary."""
    clean_name = os.path.basename(filename)
    if not clean_name or clean_name in {".", ".."}:
        raise ValueError("Invalid filename.")
    resolved_base = os.path.realpath(str(base_dir))
    resolved_target = os.path.realpath(os.path.join(resolved_base, clean_name))
    if not resolved_target.startswith(resolved_base + os.sep):
        raise ValueError("Directory traversal blocked.")
    return Path(resolved_target)
