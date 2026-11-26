# Architecture

## Overview

```
Browser
   |
   v
React Frontend (SPA, served as static files by the backend)
   |
   v
FastAPI Backend
   +---- SQLite (metadata, history, settings)
   +---- Asset storage (/var/lib/sceneforge)
   +---- Pillow (thumbnails, JPEG conversion, validation)
   +---- ComfyUI client (HTTP + WebSocket, localhost only)
              |
              v
           ComfyUI (inference engine, untouched by SceneForge)
```

The frontend never talks to ComfyUI directly. All ComfyUI traffic goes through
the backend.

## Key decisions

- **Single host.** The application runs only on thor128-2, next to ComfyUI.
  Backend-to-ComfyUI communication uses `127.0.0.1`.
- **Static serving.** The production React build is served by FastAPI with an
  SPA fallback, so one port (8080) serves both UI and API.
- **SQLite** stores all metadata; original uploaded images are never
  overwritten and live under `/var/lib/sceneforge`, separate from the
  repository and from ComfyUI's input/output directories.
- **Workflow adapter (Phase 3).** Each registered workflow keeps its
  API-format JSON template plus declarative input/output mappings in
  configuration. Execution deep-copies the template, applies mappings,
  validates node IDs and input names, then submits via `POST /prompt` with a
  unique client ID. Progress is tracked over
  `ws://127.0.0.1:8188/ws?clientId=...` using real ComfyUI events only —
  never simulated.
- **Settings precedence.** Values saved in the Settings UI (SQLite) override
  environment defaults from `/opt/sceneforge/.env`.
- **Resilience.** SceneForge starts and stays usable when ComfyUI is down;
  connection status is polled by the UI and the backend client reconnects
  lazily on each request.

## Backend modules

| Module | Responsibility |
|---|---|
| `app/config.py` | Environment settings, data directory layout |
| `app/database/` | SQLAlchemy engine/session, DB bootstrap |
| `app/models/` | ORM models (settings; assets/jobs/workflows in later phases) |
| `app/schemas/` | Pydantic request/response schemas |
| `app/api/` | HTTP routers (`/api/...`) |
| `app/comfyui/` | ComfyUI HTTP/WebSocket client and workflow adapter |
| `app/services/` | Domain logic (settings resolution, later: assets, jobs) |
| `app/main.py` | App factory, lifespan, SPA static serving |

## Data

```
/var/lib/sceneforge/
├── database/       SQLite (sceneforge.db)
├── assets/         permanent originals (characters/, scenes/)
├── thumbnails/     generated thumbnails
├── generated/      saved generation outputs (JPEG)
├── temporary/      transient files
├── backups/        consistent backups (Phase 8)
└── logs/
```

Persistent data never lives inside the repository. Upgrades and reboots must
not lose it.
