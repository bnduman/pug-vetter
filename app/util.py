"""Small helpers with no external dependencies (easy to unit-test)."""
import re


def slugify_realm(realm: str) -> str:
    """Turn a human realm name into the slug Warcraft Logs expects.

    "Spineshatter"   -> "spineshatter"
    "Living Flame"   -> "living-flame"
    "Nek'rosh"       -> "nekrosh"
    """
    s = (realm or "").strip().lower().replace("'", "")
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s
