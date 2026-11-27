import hashlib
import io
from pathlib import Path

from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MIME_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
DEFAULT_JPEG_QUALITY = 85
DEFAULT_THUMB_MAX_DIM = 320


class ImageError(ValueError):
    pass


def validate_image_bytes(data: bytes) -> tuple[int, int]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ImageError(f"File exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
            return img.size
    except ImageError:
        raise
    except Exception as exc:
        raise ImageError(f"Invalid or corrupted image: {exc}") from exc


def make_thumbnail(
    source: Path,
    dest: Path,
    max_dim: int = DEFAULT_THUMB_MAX_DIM,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> None:
    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img)
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        rgb = img.convert("RGB")
        dest.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(dest, "JPEG", quality=quality)


def safe_extension(filename: str | None) -> str:
    if not filename:
        raise ImageError("Missing filename")
    name = Path(filename).name
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ImageError(f"Unsupported file type: {ext or 'none'}")
    return ext


def display_name_from_filename(filename: str) -> str:
    name = Path(Path(filename).name).stem
    name = " ".join(name.split())
    return name[:200] if name else "Untitled"


def media_token(rel_path: str | None) -> str:
    """Short per-file token derived from the stored path, for cache-busting.

    Media is served under the database primary key, which SQLite recycles once
    the highest rowid is deleted. Keying the browser cache on that id alone lets
    a reused id serve a previously deleted image. The stored path is unique per
    file and is never reused, so a token derived from it keeps each media URL's
    cache entry unambiguous for the file's lifetime.
    """
    if not rel_path:
        return "0"
    return hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]
