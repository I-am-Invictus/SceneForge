from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.settings import router as settings_router
from app.api.status import router as status_router
from app.comfyui import comfyui_client
from app.config import get_settings
from app.database.db import init_db

FRONTEND_DIST = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().ensure_data_dirs()
    init_db()
    yield
    await comfyui_client.close()


app = FastAPI(title="SceneForge Studio", version="0.1.0", lifespan=lifespan)

app.include_router(status_router)
app.include_router(settings_router)

if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets", StaticFiles(directory=assets_dir), name="frontend-assets"
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str, request: Request):
        if full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = (FRONTEND_DIST / full_path).resolve()
        if (
            full_path
            and candidate.is_file()
            and str(candidate).startswith(str(FRONTEND_DIST.resolve()))
        ):
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
