# SceneForge Studio — Session Handoff

Read this first after any context compaction. It captures durable project state,
the standing gallery comparison requirement, and operational workflows.

## Objective

Locally hosted web app on **thor128-2** that manages and executes the user's
existing ComfyUI workflows: general image generation (Phase 4), image
modification (Phase 5), character swapping (Phase 6), plus asset libraries,
history, and workflow management.

## Machines & paths

| Thing | Where |
|---|---|
| Dev repo (OpenCode runs here) | `~/code/SceneForge` on **thor128** (192.168.0.115, user `nmc220`) |
| Runtime repo | `~/code/SceneForge` on **thor128-2** (192.168.0.123) |
| Production app | `/opt/sceneforge/` on thor128-2 (backend `.venv`, frontend `dist`) |
| Persistent data | `/var/lib/sceneforge/` (`assets/`, `thumbnails/`, `generated/<job_client_id>/`, `sceneforge.db`) |
| ComfyUI 0.46.0 | `http://127.0.0.1:8188` on thor128-2 (`comfyui.service`), source `/opt/ai/comfyui` |
| SceneForge service | `sceneforge.service` on thor128-2, `0.0.0.0:8080`, runs as **nmc220** |
| Git remote | `git@github.com:I-am-Invictus/SceneForge.git`, branch `main` |
| Registered workflows | `workflows/{general_generation,image_modification,character_swap}/<id>/{workflow.json,config.json}` |
| Reference workflows (read-only) | `comfy_ui_workflows_ref/` — never modify |

**Never deploy or mutate production on thor128.** Frontend never talks to
ComfyUI directly; everything goes through the backend over localhost.

## Deploy / verify workflow

1. Develop + test on thor128: `backend/.venv/bin/python -m pytest tests` (from `backend/`), `npm run build` (from `frontend/`).
2. `git add/commit/push origin main`.
3. On thor128-2: `git -C ~/code/SceneForge pull && bash ~/code/SceneForge/scripts/deploy.sh` (rsync → `/opt/sceneforge`, refresh venv, build frontend).
4. **User** runs `sudo systemctl restart sceneforge` (sudo needs a password).
5. Verify live via `curl http://127.0.0.1:8080/api/...` over ssh; ask the user to visually confirm in a browser.

## Phase status

- **Phase 1 (foundation/deployment):** DONE. Service active+enabled, crash-recovery verified.
- **Phase 2 (asset library):** DONE, verified in production (characters/scenes, folders, refs, favorites, thumbnails).
- **Phase 3 (ComfyUI integration):** DONE, verified live. Registry (`app/comfyui/registry.py`), adapter, jobs + WS monitor (`app/services/monitor.py`), output retrieval, `POST /api/generate/{id}`, `GET /api/jobs[/{id}]`, cancel, media endpoints. 42 backend tests.
  - Critical monitor facts: one stable `comfyui_client.monitor_client_id` is used both as the WS `clientId` **and** the prompt `client_id` (ComfyUI routes `execution_start/success/error` to the submitting client_id, not broadcast). Periodic resync (8s) + 30s lost-grace as safety net. `/queue` items are `[number, prompt_id, ...]` under keys `queue_running`/`queue_pending`.
- **Phase 4 (general generation UI):** IN PROGRESS — see below.
- **Phase 5 (image modification UI), Phase 6 (character swap UI):** NOT STARTED. Blocked on Phase 4.
- Phase 7/8: workflow management UI, unified generation history (placeholder pages exist).

## STANDING REQUIREMENT — Gallery before/after comparison (Phases 4–6)

A **single reusable image-comparison component** for the generation gallery,
used by Image Modification (Phase 5) and Character Swapping (Phase 6) — and
architecturally present from Phase 4. Requirements:

- Draggable **vertical before/after slider**; original image on the **left**,
  generated image on the **right**.
- **CSS clipping-based overlay** (clip the top layer, both layers in the same
  frame) to maintain identical alignment.
- **Side-by-side** comparison mode.
- **Original-only** and **generated-only** modes.
- **Mouse and touchscreen** support (pointer events).
- **Previous/next navigation** between generated results.
- **Preserve comparison mode during navigation** and **reset the slider to
  midpoint** for each new result.
- **Maintain original/generated image associations** per result.
- **Handle multiple outputs from the same source** (e.g. batch / multiple
  save-image nodes) — selectable, all against the same original.
- **Gracefully handle missing original images** (e.g. general generation has
  no original → generated-only, no broken controls).

Integration rule: it belongs to the **gallery experience** (the results area of
each generation workspace + later the unified History page), **not** an
isolated workspace. One component for all generation modes.

Implementation in Phase 4: `frontend/src/components/ImageComparison.tsx`
(props: `original?: CompareImage | null`, `generated: CompareImage`,
`resultKey` (drives slider reset), `onPrev/onNext/canPrev/canNext`).
`JobResultViewer`/`JobGallery` wrap it for job-based galleries; Phases 5/6
pass a resolved `original` (asset file media URL) and reuse them unchanged.

## Phase 4 scope (current authorization)

- General Generation page (`/generate`) only: prompt/negative/size presets/
  seed/steps/cfg form → `POST /api/generate/qwen_image_gen_v1`, live progress
  via `GET /api/jobs/{client_id}` polling, cancel, results gallery with the
  comparison component (generated-only mode for now).
- Do NOT build Phase 5/6 forms. Keep `/modify` and `/swap` as placeholders.
- Stop after Phase 4 and await approval.

## Conventions

- Backend: FastAPI + SQLAlchemy 2.0 sync sessions (`SessionLocal`), Pydantic schemas in `app/schemas/`, services in `app/services/`. Tests in `backend/tests/` (pytest, `conftest.py` sets a temp `SCENEFORGE_DATA_DIR`).
- Frontend: React 18 + TS + Vite 5, react-router-dom 6. No test runner; `npm run build` (`tsc && vite build`) is the gate. Pages in `src/pages/`, components in `src/components/`, API clients in `src/services/`, types in `src/types/`. Dark theme via CSS variables in `src/styles.css` (see existing classes: `.page`, `.settings-card`, `.field`, `.btn`, `.asset-grid`, `.dialog`, `.form-error`).
- API shape for jobs: `JobOut` (`client_id` is the job's public id; `outputs[].thumbnail_url` / `original_url`), `WorkflowOut` (inputs with `type`/`required`/`default`/`auto`).
- ComfyUI input values: `seed: "random"` for random; numbers coerced by the adapter; image inputs are `{"asset_file_id": <id>}`.

## Known open items

- Reboot survival of `sceneforge.service` never explicitly verified (restart survival is).
- ComfyUI `server.client_id` is global last-write-wins; if the user's ComfyUI UI submits prompts concurrently, SceneForge WS events may miss — the periodic resync covers this (jobs still complete, possibly slightly later).
