from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    sceneforge_host: str = "0.0.0.0"
    sceneforge_port: int = 8080
    comfyui_http_url: str = "http://127.0.0.1:8188"
    comfyui_ws_url: str = "ws://127.0.0.1:8188/ws"
    sceneforge_data_dir: str = "/var/lib/sceneforge"
    jpeg_quality: int = 85
    thumb_max_dim: int = 320

    @property
    def data_dirs(self) -> dict[str, Path]:
        base = Path(self.sceneforge_data_dir)
        return {
            "base": base,
            "database": base / "database",
            "assets": base / "assets",
            "characters": base / "assets" / "characters",
            "scenes": base / "assets" / "scenes",
            "thumbnails": base / "thumbnails",
            "generated": base / "generated",
            "temporary": base / "temporary",
            "backups": base / "backups",
            "logs": base / "logs",
        }

    def ensure_data_dirs(self) -> None:
        for path in self.data_dirs.values():
            path.mkdir(parents=True, exist_ok=True)

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dirs['database'] / 'sceneforge.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
