from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Setting

SETTING_KEYS = ("comfyui_http_url", "comfyui_ws_url")


def _defaults() -> dict[str, str]:
    settings = get_settings()
    return {
        "comfyui_http_url": settings.comfyui_http_url,
        "comfyui_ws_url": settings.comfyui_ws_url,
    }


def get_effective_settings(db: Session) -> dict[str, str]:
    """DB values take precedence over environment defaults."""
    values = _defaults()
    rows = db.query(Setting).filter(Setting.key.in_(SETTING_KEYS)).all()
    for row in rows:
        if row.key in values:
            values[row.key] = row.value
    return values


def update_settings(db: Session, updates: dict[str, str]) -> dict[str, str]:
    for key, value in updates.items():
        if key not in SETTING_KEYS:
            continue
        row = db.get(Setting, key)
        if row is None:
            row = Setting(key=key, value=value)
            db.add(row)
        else:
            row.value = value
    db.commit()
    return get_effective_settings(db)


def validate_url(value: str, scheme: str) -> str | None:
    """Return an error message, or None if the value looks like a valid URL."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(value)
    except ValueError:
        return "Unparseable URL"
    if parsed.scheme != scheme or not parsed.netloc:
        return f"Expected a {scheme}:// URL with a host"
    return None
