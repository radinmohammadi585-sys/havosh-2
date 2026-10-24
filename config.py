"""Central configuration — env only, no secrets hardcoded."""
from __future__ import annotations
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "kavosh.db"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


load_env_file(ROOT / ".env")

PORT = int(os.getenv("PORT", "3000"))
API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip()
SITE_URL = os.getenv("SITE_URL", "https://example.com").strip()
SITE_NAME = os.getenv("SITE_NAME", "Kavosh AI 2").strip()
SESSION_TTL = 8 * 60 * 60
STUDENT_MAX = 3000
WINDOW_SECONDS, MAX_REQUESTS = 60, 30
LOGIN_WINDOW, LOGIN_MAX = 300, 8
COOKIE_NAME = "kavosh_session"
CSRF_COOKIE = "kavosh_csrf"
