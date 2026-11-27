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
- **Phase 5 (image modification UI) + generated-image deletion + move-to-library:** DONE, verified live (mode-aware source picker over Characters/Scenes, upload, before/after comparison with real sources, output deletion, move results into either library, live ComfyUI jobs). See "Phase 5 implementation" below.
- **Asset management (edit metadata + reference-safe delete) for Scenes/Characters:** DONE, verified live. See "Asset management" below.
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
- **Source selection** (`SourceImagePicker.tsx`, kind-aware): the picker shows
  the library matching the current mode — Scene mode lists/uploads the **Scenes**
  library, Character mode lists/uploads the **Characters** library (Phase 2
  APIs, no separate picker). Upload destination follows the mode. Source is
  referenced by `asset_file_id` and never modified; any asset file (either
  library) is a valid source for the edit workflow.
- **Form inputs:** source, prompt, negative_prompt, size (auto = match source
  via `auto: "source"`, or custom ×8-rounded W/H), batch_size 1–8, denoise
  0–1, steps, seed (random/fixed).
- **Original resolution for comparison:** `job.inputs.source_image.asset_file_id`
  → map of asset files from **both** libraries → `/media/assets/{id}` passed as
  `original` to `JobResultViewer` → `ImageComparison`. Missing source (deleted
  asset or failed load) degrades to generated-only without breaking the gallery.
- **Multiple outputs:** `batch_size > 1` yields multiple images on node 30 →
  output picker + "Result i of n" label + prev/next; all against the same
  original.
- **Output capture fix:** `generation.retrieve_outputs` now only stores outputs
  for nodes the workflow spec declares (image edit: node 30 only) — previously
  the `PreviewImage` node 6 was stored as a duplicate result.
- **Generated-image deletion:** `DELETE /api/jobs/{client_id}/outputs/{output_id}`
  → `app/services/job_outputs.py`. Safety: path must resolve inside
  `/var/lib/sceneforge` (else 400); file removed only if no other `JobOutput`
  **and no `AssetFile`** references it (moved outputs share the asset file's
  stored path — deleting such an output keeps the image in the library); DB row
  committed before file unlink (storage failure can't corrupt the DB); missing
  files tolerated. UI: trash on gallery cards + "Delete image" in the viewer,
  both behind `ConfirmDialog`; state updates immediately from the returned
  `JobOut`. Source assets and sibling outputs are never touched.
- **Move to library** (`POST /api/jobs/{client_id}/outputs/{output_id}/move`,
  body `{"folder": "character" | "scene"}`): relocates the generated image's
  bytes into `assets/{kind}/{uuid}/{uuid}{ext}` (fresh dir — no overwrite, no
  duplication) and registers it as a new `Asset` + `AssetFile` (name = job
  prompt, thumbnail regenerated via `images.make_thumbnail`). The
  `JobOutput.stored_path` is updated in place, so the image stays in the job's
  results and history; `/media/job-assets/{id}` keeps serving it. Re-moving
  replaces the previous library entry (old `Asset`/`AssetFile` removed, old
  thumbnail unlinked). The source asset is never touched. UI:
  `MoveToLibraryDialog` (Characters | Scenes) from a move action on gallery
  cards and in the result viewer toolbar.

**Workflow input/output mapping (`qwen_image_edit_v1`):**
source_image→8(image), prompt→3(prompt), negative_prompt→4(prompt),
width/height→9 (auto: source), batch_size→9, seed/steps/denoise→2;
outputs: images→30 (SaveImage, `filename_prefix: sceneforge_edit`).

## Asset management (edit metadata + reference-safe deletion)

**Metadata editing** — `Asset` gained `description` (TEXT) and `tags`
(TEXT, JSON array string) columns; `init_db()` applies an idempotent
`migrate_legacy_columns()` ALTER for pre-existing SQLite databases
(verified on production). `PATCH /api/libraries/{kind}/assets/{id}` now
accepts `name` / `description` ("" clears) / `tags` ([] clears; deduped,
max 20 × 50 chars) / `is_favorite` individually. UI: compact
`EditAssetDialog` (prepopulated) from a new Edit action on asset cards and
the detail page (supersedes the Rename dialog, which was removed); the
detail page renders description + tag chips. Saves never touch image files,
thumbnails, IDs, or references; changes persist across refresh and service
restart (live-verified).

**Reference-safe deletion** — `DELETE /api/libraries/{kind}/assets/{id}`
always removes the library records, but image bytes are only unlinked when
no other record references them:
- `JobOutput.stored_path` / `thumbnail_path` equal to the file's paths
  (moved outputs share the asset file's stored path);
- `Job.inputs_json` containing `"asset_file_id": <id>` (historical source
  associations for before/after comparisons).
Kept bytes stay servable via the job media endpoints; the asset's own
thumbnail is always removed (job outputs have their own). Path safety:
files outside the managed base are refused (logged, skipped); missing
files and unlink OSErrors are tolerated; unknown assets → 404. UI: delete
action on cards (with a confirmation dialog naming the asset and noting
job-used images are kept) — the detail-page delete predates this.

**Live verification (thor128-2), all PASS:** migration added the columns to
the production DB with rows intact; scene + character metadata edits
persisted after a service restart; throwaway scene + character deletes
unlinked files and left the libraries clean; a user browser-deletion of a
scene asset whose image was a moved job output (output 18) removed the
library entry while the file and `/media/job-assets/18` kept working;
Image Modification, general generation, history, and comparisons all
regression-checked. Backend: **66 pytest tests green** (58 + 8 new).
Frontend: `tsc && vite build` clean.
Note: during the first live run, two unreferenced orphan files appeared
after deletion (DB stayed consistent); not reproducible afterwards (4/4
clean deletes), the orphans were removed manually, and deletion now logs
outcomes (refusals/failures at WARNING) for future diagnosis.

**Live verification actually executed (thor128-2, ComfyUI 0.46.0) — latest
round, 43 API/byte-level checks, all PASS:**
- Uploads through the existing path: new scene image (201) and new character
  image (201).
- Existing sources: scene (Titanic still) for Scene mode, character
  (WonderWomen) for Character mode; both real edit jobs completed (~15s) and
  both executed ComfyUI prompts contained the image-edit workflow node set.
- Moves: scene result → Scenes, character result → Characters — bytes
  relocated (sha256 identical, old path gone), both listed in their libraries
  with original + thumbnail media 200; job results + history intact and
  serving; both source assets byte-identical and 200.
- Deletion: deleting a MOVED output kept the library image (ref-count fix);
  plain general-generation output delete 200 → 404 → media 404; a
  user-browser-moved output from an earlier round still served.
- Backend: **58 pytest tests executed green** (49 Phase 3/5 + 9 move tests +
  1 moved-deletion test). Frontend: `tsc && vite build` clean.
- Browser-side visuals (mode chips, picker per mode, move dialog, slider)
  deployed; the user has exercised the move action in-browser (one image
  already lives in Scenes from that).

## Conventions

- Backend: FastAPI + SQLAlchemy 2.0 sync sessions (`SessionLocal`), Pydantic schemas in `app/schemas/`, services in `app/services/`. Tests in `backend/tests/` (pytest; `tests/test_assets.py` sets a temp `SCENEFORGE_DATA_DIR` at import and other test modules import from it).
- Frontend: React 18 + TS + Vite 5, react-router-dom 6. No test runner; `npm run build` (`tsc && vite build`) is the gate. Pages in `src/pages/`, components in `src/components/`, API clients in `src/services/`, types in `src/types/`. Dark theme via CSS variables in `src/styles.css` (see existing classes: `.page`, `.settings-card`, `.field`, `.btn`, `.asset-grid`, `.dialog`, `.form-error`).
- API shape for jobs: `JobOut` (`client_id` is the job's public id; `outputs[].thumbnail_url` / `original_url`), `WorkflowOut` (inputs with `type`/`required`/`default`/`auto`).
- ComfyUI input values: `seed: "random"` for random; numbers coerced by the adapter; image inputs are `{"asset_file_id": <id>}`.

## Known open items

- Reboot survival of `sceneforge.service` never explicitly verified (restart survival is).
- ComfyUI `server.client_id` is global last-write-wins; if the user's ComfyUI UI submits prompts concurrently, SceneForge WS events may miss — the periodic resync covers this (jobs still complete, possibly slightly later).
