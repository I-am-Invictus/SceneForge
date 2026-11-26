from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Setting
from app.schemas import SettingsUpdate

SETTING_KEYS = (
    "comfyui_http_url",
    "comfyui_ws_url",
    "jpeg_quality",
    "thumb_max_dim",
)

_INT_RANGES = {
    "jpeg_quality": (10, 100),
    "thumb_max_dim": (64, 2048),
}


def _defaults() -> dict[str, str]:
    settings = get_settings()
    return {
        "comfyui_http_url": settings.comfyui_http_url,
        "comfyui_ws_url": settings.comfyui_ws_url,
        "jpeg_quality": str(settings.jpeg_quality),
        "thumb_max_dim": str(settings.thumb_max_dim),
    }


def get_effective_settings(db: Session) -> dict[str, str]:
    values = _defaults()
    rows = db.query(Setting).filter(Setting.key.in_(SETTING_KEYS)).all()
    for row in rows:
        if row.key in values:
            values[row.key] = row.value
    return values


def validate_value(key: str, value: str) -> str | None:
    from urllib.parse import urlparse

    if key in ("comfyui_http_url", "comfyui_ws_url"):
        scheme = "http" if key.endswith("http_url") else "ws"
        try:
            parsed = urlparse(value)
        except ValueError:
            return "Unparseable URL"
        if parsed.scheme != scheme or not parsed.netloc:
            return f"Expected a {scheme}:// URL with a host"
        return None
    if key in _INT_RANGES:
        try:
            number = int(value)
        except ValueError:
            return "Must be an integer"
        low, high = _INT_RANGES[key]
        if not low <= number <= high:
            return f"Must be between {low} and {high}"
        return None
    return None


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


def image_settings(db: Session) -> tuple[int, int]:
    values = get_effective_settings(db)
    return int(values["jpeg_quality"]), int(values["thumb_max_dim"])


def validate_update(update: SettingsUpdate) -> list[str]:
    errors = []
    for key, value in update.model_dump(exclude_none=True).items():
        error = validate_value(key, str(value))
        if error:
            errors.append(f"{key}: {error}")
    return errors
