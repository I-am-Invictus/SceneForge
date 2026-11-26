# SceneForge Studio

A locally hosted web application for managing and executing ComfyUI workflows:
general image generation, image modification, and character swapping (primary
feature), with character/scene asset libraries, workflow management, and
generation history.

ComfyUI remains the inference engine. SceneForge provides the interface, asset
management, workflow configuration, and generation management.

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation and deployment | in progress |
| 2 | Asset library | planned |
| 3 | ComfyUI integration | planned |
| 4 | General image generation | planned |
| 5 | Image modification | planned |
| 6 | Character swapping | planned |
| 7 | Workflow management | planned |
| 8 | History, reliability, finalization | planned |

See `docs/ARCHITECTURE.md` for system design and `docs/DEPLOYMENT.md` for
deployment and service management.

## Repository layout

```
frontend/          React + TypeScript + Vite SPA
backend/           FastAPI application (app/), tests/
workflows/         ComfyUI API-format workflow templates + mappings
scripts/           setup, deploy, and maintenance scripts
docs/              architecture, deployment, and operations documentation
requirements.txt   backend runtime dependencies
.env.example       environment configuration template
```

## Development

Backend (from `backend/`):

```bash
python3 -m venv .venv
.venv/bin/pip install -r ../requirements-dev.txt
.venv/bin/python -m pytest
```

Frontend (from `frontend/`):

```bash
npm install
npm run dev      # dev server with /api proxy to 127.0.0.1:8080
npm run build    # production build to frontend/dist
```

Configuration comes from environment variables (see `.env.example`). In
production the service reads `/opt/sceneforge/.env`; values saved in Settings
override the environment defaults.
