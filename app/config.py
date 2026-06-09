"""Configuration, loaded from environment variables (optionally a .env file).

Kept deliberately dependency-free (no pydantic) so it installs cleanly on any
Python, including bleeding-edge versions.
"""
import os
from pathlib import Path

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE per line, # comments, optional quotes.

    Does not override variables already set in the real environment.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(_ENV_PATH)

WCL_CLIENT_ID = os.environ.get("WCL_CLIENT_ID", "")
WCL_CLIENT_SECRET = os.environ.get("WCL_CLIENT_SECRET", "")
WCL_TOKEN_URL = os.environ.get("WCL_TOKEN_URL", "https://www.warcraftlogs.com/oauth/token")
# The Classic site serves Classic/Era/Anniversary data; retail lives on www.
WCL_API_URL = os.environ.get("WCL_API_URL", "https://classic.warcraftlogs.com/api/v2/client")
DEFAULT_REGION = os.environ.get("DEFAULT_REGION", "US")
DEFAULT_REALM = os.environ.get("DEFAULT_REALM", "")
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", "600"))
