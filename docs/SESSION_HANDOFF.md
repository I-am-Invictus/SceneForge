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
- **Phase 4 (general generation UI):** DONE, verified live (form, live progress, cancel, results gallery, generated-only comparison).
- **Phase 5 (image modification UI) + generated-image deletion:** DONE, verified live (source picker/upload, Scene/Character editing modes, before/after comparison with real sources, output deletion, live ComfyUI jobs). See "Phase 5 implementation" below.
- **Phase 6 (character swap UI):** NOT STARTED.
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

## Phase 5 implementation (current state)

**Image Modification (`/modify`, `frontend/src/pages/ImageModification.tsx`)**
uses `qwen_image_edit_v1` (category `image_modification`) — a faithful copy of
`comfy_ui_workflows_ref/api_imageEditWorkflow.json` + added SaveImage node `30`
(verified node-for-node against the reference; executed ComfyUI prompts contain
the edit workflow's node set: `TextEncodeQwenImageEditPlus` ×2, `LoadImage`,
`KSampler`/`sa_solver`, `VAEDecode`, `SaveImage`). It is NOT the general
generation workflow.

- **Editing modes (UI only):** Scene and Character chips above the prompt.
  The workflow is a single instruction-based editor, so the mode only changes
  the prompt label/placeholder/guidance text — it is not a workflow input and
  is not sent to the backend (do not invent controls for it).
- **Source selection** (`SourceImagePicker.tsx`): upload a new image (stored in
  the Scenes library, Phase 2 APIs) or pick an existing scene file. Source is
  referenced by `asset_file_id` and never modified.
- **Form inputs:** source, prompt, negative_prompt, size (auto = match source
  via `auto: "source"`, or custom ×8-rounded W/H), batch_size 1–8, denoise
  0–1, steps, seed (random/fixed).
- **Original resolution for comparison:** `job.inputs.source_image.asset_file_id`
  → scene file map → `/media/assets/{id}` passed as `original` to
  `JobResultViewer` → `ImageComparison`. Missing source (deleted asset or
  failed load) degrades to generated-only without breaking the gallery.
- **Multiple outputs:** `batch_size > 1` yields multiple images on node 30 →
  output picker + "Result i of n" label + prev/next; all against the same
  original.
- **Output capture fix:** `generation.retrieve_outputs` now only stores outputs
  for nodes the workflow spec declares (image edit: node 30 only) — previously
  the `PreviewImage` node 6 was stored as a duplicate result.
- **Generated-image deletion:** `DELETE /api/jobs/{client_id}/outputs/{output_id}`
  → `app/services/job_outputs.py`. Safety: path must resolve inside
  `/var/lib/sceneforge` (else 400); file removed only if no other `JobOutput`
  references it; DB row committed before file unlink (storage failure can't
  corrupt the DB); missing files tolerated. UI: trash on gallery cards +
  "Delete image" in the viewer, both behind `ConfirmDialog`; state updates
  immediately from the returned `JobOut`. Source assets and sibling outputs are
  never touched.

**Workflow input/output mapping (`qwen_image_edit_v1`):**
source_image→8(image), prompt→3(prompt), negative_prompt→4(prompt),
width/height→9 (auto: source), batch_size→9, seed/steps/denoise→2;
outputs: images→30 (SaveImage, `filename_prefix: sceneforge_edit`).

**Live verification actually executed (thor128-2, ComfyUI 0.46.0):**
- Real Scene-edit job and Character-edit job: both completed (~18s), 1 output
  each (node 30, 872×872); executed prompt node-sets confirmed = image-edit
  workflow; full/thumbnail/source media all 200.
- Deletion: 200 then 404 on repeat; deleted media 404; sibling output and
  source asset file (on disk + `/media/assets/2`) intact.
- Phase 4 regression: new general-generation job completed with output.
- Backend: 49 pytest tests executed green. Frontend: `tsc && vite build` clean.
- Browser-side visuals (mode chips, slider drag, confirm dialog) were
  deployed but confirmed by the user in-browser only if reported.

## Conventions

- Backend: FastAPI + SQLAlchemy 2.0 sync sessions (`SessionLocal`), Pydantic schemas in `app/schemas/`, services in `app/services/`. Tests in `backend/tests/` (pytest, `conftest.py` sets a temp `SCENEFORGE_DATA_DIR`).
- Frontend: React 18 + TS + Vite 5, react-router-dom 6. No test runner; `npm run build` (`tsc && vite build`) is the gate. Pages in `src/pages/`, components in `src/components/`, API clients in `src/services/`, types in `src/types/`. Dark theme via CSS variables in `src/styles.css` (see existing classes: `.page`, `.settings-card`, `.field`, `.btn`, `.asset-grid`, `.dialog`, `.form-error`).
- API shape for jobs: `JobOut` (`client_id` is the job's public id; `outputs[].thumbnail_url` / `original_url`), `WorkflowOut` (inputs with `type`/`required`/`default`/`auto`).
- ComfyUI input values: `seed: "random"` for random; numbers coerced by the adapter; image inputs are `{"asset_file_id": <id>}`.

## Known open items

- Reboot survival of `sceneforge.service` never explicitly verified (restart survival is).
- ComfyUI `server.client_id` is global last-write-wins; if the user's ComfyUI UI submits prompts concurrently, SceneForge WS events may miss — the periodic resync covers this (jobs still complete, possibly slightly later).
