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
- **Phase 6 (character swap UI):** DONE, verified live. See "Phase 6 implementation" below.
- **Gallery Collections + gallery image viewer + reference-management generalization:** DONE, verified live (backend 80 tests + production smoke/acceptance). See "Gallery Collections (this session)" below.
- **Phase 7 (workflow management):** DONE, verified live (101 backend tests + production acceptance on thor128-2). See "Phase 7 implementation" below.
- Phase 8 (unified generation history): not started.

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

## Monitor reliability fixes (this session)

Two backend defects in `app/services/monitor.py` were found and fixed, both
live-verified on thor128-2.

- **Submit-window race** — `submit_generation` commits a job as `queued`
  *before* `comfyui_client.submit_prompt` returns its `comfyui_prompt_id`
  (the id is assigned and committed afterwards). The 8s resync failed any
  `queued` job with no prompt_id as "Prompt was never submitted to ComfyUI",
  so a resync landing in that window (observed under 3 concurrent submits)
  falsely marked a job failed even though the prompt actually landed and the
  job later completed. Fix: `SUBMIT_GRACE_SECONDS = 15.0` — a freshly-queued
  job without a prompt_id younger than the grace is skipped; genuinely stuck
  jobs (crash mid-submit) still fail after the grace. Tests:
  `test_resync_skips_fresh_queued_job_without_prompt_id`,
  `test_resync_fails_old_queued_job_without_prompt_id`.
- **Outputs before completed** — `_complete` marked a job `completed` and
  committed *before* `retrieve_outputs` stored its images, so a reader (the UI
  polls every 2.5s) could catch a completed job with no outputs and show "no
  image outputs" until a refresh. Fix: `_complete` now awaits
  `retrieve_outputs` first, then flips to `completed`, so a job reads
  `completed` only once its images are stored. Test:
  `test_complete_retrieves_outputs_before_marking_completed`.

## Add-to-Library consolidation

The move-to-library behavior (pending target, `POST .../move` call, job-list
upsert) lived inline in `ImageModification.tsx` and was missing entirely from
`GeneralGeneration.tsx`. It is now a shared hook,
`frontend/src/hooks/useMoveToLibrary.ts`, used identically by General
Generation, Image Modification, and Character Swapping — so all three show the
same "Move to library" action on gallery cards and in the result viewer, and
behave identically.

## Width/height mapping investigation

Reported symptom: General Generation portrait 768×1024 (width 768, height
1024) came back landscape 1024×768. **Not reproduced** — no inversion exists in
the pipeline, so no swap fix was added (no speculative swaps). Evidence:
- Frontend (`GeneralGeneration.tsx`): width/height are separate fields;
  presets are correct (e.g. `3:4` = 896×1152 portrait). Sends
  `inputs.width` / `inputs.height` independently.
- Config (`qwen_image_gen_v1/config.json`): `width→node15.width`,
  `height→node15.height` (node 15 = `EmptyLatentImage`). No swap.
- Adapter (`WorkflowAdapter._coerce`): width/height coerced independently.
- Live (deployed code, ComfyUI 0.46.0): portrait 768×1024 → **768×1024**,
  landscape 1024×768 → **1024×768**, square 1024×1024 → **1024×1024**. Output
  dims equal the `EmptyLatentImage` dims (VAEDecode decodes the sampler's
  latent directly), confirming node 15 received the correct width/height.
  Historical 832×1216 portrait jobs also returned 832×1216.

## Phase 6 implementation (character swap)

**Page:** `frontend/src/pages/CharacterSwap.tsx` at `/swap` (replaces the
placeholder). Drives `qwen_person_swap_v1` (category `character_swap`), a
faithful copy of `comfy_ui_workflows_ref/api_PersonSwapWorkflow.json` (AusBoss
"Qwen Image 2.1 Person Swap"; output node 18 = `AUSBOSS_NODES_SaveImage`,
prefix `qwen21_person_swap`). Reuses the shared job polling, `JobGallery`,
`JobResultViewer` + `ImageComparison` (before = **scene**, after = result),
`useMoveToLibrary`, and output deletion — no new infra.

- **Inputs:** scene (`scene_image`, required), character (`character_1`,
  required), who-to-replace (`composition_prompt`, may be blank for a single
  person — the workflow's `RegexReplace` node 15:24 rewrites empty "who" to
  one-person wording), whole-body/head-only (`swap_mode` bool, default whole
  body), seed (random/fixed), steps (default 25).
- **Scene/character selection:** two `SourceImagePicker`s — the scene picker
  lists/uploads the **Scenes** library, the character picker the **Characters**
  library. Comparison original resolves from
  `job.inputs.scene_image.asset_file_id`.
- **Single character only:** the API export contains one character `LoadImage`
  (node 3); the author's "Second character" nodes are bypassed in the UI and
  absent from the API JSON, so a second character is **not supported** (no
  misleading control is added). One reference image per character.

**Workflow mapping (`qwen_person_swap_v1`):**
scene_image→2(image), character_1→3(image), composition_prompt→4(text),
swap_mode→5(value, bool), seed→6(seed), steps→53(value, number, default 25);
outputs: images→18 (SaveImage). The workflow itself resizes the scene to ~2 MP
(node 16:40) and the character to ~0.59 MP (node 16:41); the model is selected
by `swap_mode` (body LoRA node 10 vs head LoRA node 11) via `ComfySwitchNode`
16:43.

## Gallery Collections (this session)

Explicit, user-named collections of **generated** images, separate from the
asset libraries and from Starred. An image is a `JobOutput`; a gallery never
copies or owns image bytes — membership is a pure DB relationship, so the same
image can sit in several galleries at once.

**Data model** (`backend/app/models/gallery.py`): `galleries` (id, name,
created_at, updated_at) + `gallery_images` (id, `gallery_id` FK→galleries
CASCADE, `job_output_id` FK→job_outputs CASCADE, added_at,
`UniqueConstraint(gallery_id, job_output_id)`). Both FKs cascade (and
`PRAGMA foreign_keys=ON` is on every connection), so deleting a gallery or an
output removes its memberships automatically. New tables are created by
`init_db()` (`create_all`) on the next service start — no `ALTER` migration
needed.

**API** (`backend/app/api/galleries.py`, registered in `main.py`):
`GET/POST /api/galleries`, `GET/PATCH/DELETE /api/galleries/{id}`,
`GET /api/galleries/{id}/images`, `DELETE /api/galleries/{id}/images/{output_id}`,
`GET /api/job-outputs/{output_id}/galleries`,
`PUT /api/job-outputs/{output_id}/galleries` (syncs the **exact** set of
galleries an image belongs to — idempotent, unknown ids ignored). The list/get
responses compute `image_count` + a `cover` (most-recent member's thumbnail)
server-side. `delete_output` also calls
`gallery_service.cleanup_output_memberships` explicitly (pragma-independent
guarantee on top of the FK cascade).

**Original resolution** (`gallery_service.resolve_original`): for a gallery
image, the before/after "original" is resolved by job category —
`image_modification`→`inputs.source_image`, `character_swap`→`inputs.scene_image`,
`general_generation`→none. Returns the asset's `/media/assets/{id}` url (and
degrades to `null` if the source no longer exists), so the gallery viewer shows
the same before/after the job pages do.

**Frontend:**
- `types/galleries.ts`, `services/galleries.ts` (standard `request` pattern).
- `AddToGalleryDialog` + `hooks/useAddToGallery`: lists galleries, toggles
  membership, creates a new gallery inline, then `PUT` syncs. Wired into
  `JobResultViewer` (new `onAddToGallery` prop) and `JobGallery` (new
  `onAddToGallery` card action) and all three pages
  (GeneralGeneration / ImageModification / CharacterSwap) — same wiring shape as
  the existing `useMoveToLibrary`.
- `pages/Gallery.tsx` (`/galleries`): grid of gallery cards (cover + name +
  count) + create. `pages/GalleryDetail.tsx` (`/galleries/:id`): rename (inline),
  delete-gallery, per-image **Add to library / Add to gallery / Remove from
  this gallery / Delete image**, and a grid of thumbnails.
- `components/GalleryImageViewer.tsx`: a focused overlay that **reuses
  `ImageComparison`** — one instance stays mounted while `index` changes, which
  is what keeps the user's selected comparison mode across images. Prev/next +
  filmstrip + keyboard (Arrow/Esc) navigation, with the key handler guarded so
  it never fights the compare-slider grip (`[role="slider"]`) or text fields.
- `Sidebar`: "Galleries" link in the Library section; new `galleries` icon
  (2×2 grid) in `icons.tsx`. Routes in `App.tsx`.

**Reference management generalization (Feature 3):** `services/assets.py
add_reference` no longer restricts multi-reference to characters — scenes and
characters now behave identically (add / set-default / remove). The per-file
set-default/remove actions and the "Add reference" button in
`AssetDetailPage` are no longer gated on `isCharacter`; `SourceImagePicker`
gains the same inline management (set-default/remove per file + "Add reference"
for the expanded asset) so it can be done without leaving the workflow. Scenes
still work (verified: a 2nd reference to a scene now returns 201, previously
409; single-file scenes unaffected).

**Tests / verification:** `backend/tests/test_galleries.py` (11 tests: CRUD,
get-by-id, multi-membership, idempotent dedup, remove-from-one, delete-gallery
keeps images, delete-output cleans memberships, membership persists in DB,
original resolution for mod vs gen). Backend **80 pytest green**; `tsc && vite
build` clean. Live on thor128-2 after `sudo systemctl restart sceneforge`:
service active on :8080, both tables created, 23-check gallery acceptance
(create/list/get/delete, multi-membership, dedup, remove-from-one, original
resolution gen→null / mod→resolved+media-200, delete-gallery-keeps-outputs) all
PASS, plus a scene multi-reference check (201). Regression: `/api/health` +
`/api/comfyui/status` 200 (ComfyUI connected v0.46.0); workflows/jobs/libraries
200. All live-test galleries/outputs/assets were cleaned up (nothing left
behind this session).

## Stage 1–5 regression gate (this session)

Executed live on thor128-2 (ComfyUI 0.46.0), all PASS:
- **Stage 1 (monitor):** 3 concurrent general-generation submits → all
  completed with outputs, **zero** false "never submitted" failures (race fix).
  A person-swap job's first read as `completed` already had its output stored
  (outputs-before-completed fix).
- **Stage 2 (workflow integrity):** `POST /api/workflows/{id}/test` → all three
  workflows `ok: true` (connectivity + node registration against ComfyUI).
- **Stage 3 (asset integrity):** 4-combo move-to-library below — each moved
  output's bytes landed in `assets/{kind}/...`, the asset file and the job
  output share the stored path (refcount 1), files exist on disk.
- **Stage 4 (comparison):** before/after media 200 for a person-swap
  (scene + result) and an image-mod (source + result).
- **Stage 5 (gen + mod):** general-generation and image-modification jobs run
  to completion with captured outputs.

**Add-to-Library 4-combo live test (real generated outputs), all PASS:**
Gen→Characters, Gen→Scenes, Mod→Characters, Mod→Scenes — each moved image
appeared in the correct library (count +1, correct kind), stayed in the job's
results (`/media/job-assets/{id}` 200), and its bytes were in the right
`assets/{kind}/` folder.

Backend: **69 pytest tests green** (66 + 2 submit-race tests + 1
outputs-before-completed test). Frontend: `tsc && vite build` clean.

Note: live testing created a handful of throwaway jobs/outputs and 4 moved
library assets in production (intentionally left for inspection — see
generation history / the Characters and Scenes libraries); no existing data was
reset.

## Phase 7 implementation (workflow management)

Workflows are now configurable/upgradeable in-app without touching source code.
101 backend tests (`80` prior + `21` new in `tests/test_workflow_management.py`);
frontend build clean. Deployed + live-accepted on thor128-2 (see "Phase 7 live
acceptance" below).

**Persistent, versioned storage** (`app/comfyui/registry.py`):
- Root = `config.data_dirs["workflows"]` = `/var/lib/sceneforge/workflows/`
  (added to `config.py`). Survives deploys (app dir is rsynced `--delete`).
- Layout: `{category}/{id}/config.json` (`{id,name,description,category,active_version}`)
  + `versions/{N}/config.json` (`{version,inputs,outputs}`) + `versions/{N}/workflow.json`.
  Each version dir is immutable.
- `migrate_workflows()` (idempotent, called lazily) seeds the persistent root
  from the repo `workflows/` seed (old single-dir layout) → versioned layout as
  `v1`, and defensively converts any persistent workflow still in the old layout.
  Repo seed + `comfy_ui_workflows_ref/` are never modified.
- `WorkflowSpec` gained `active_version` + `version_dir`; `get_spec(id, version=None)`,
  `list_versions`, `workflow_meta`, `save_new_workflow`, `save_new_version`,
  `save_mappings`, `set_active_version`, `update_meta`, `load_template` (reads
  `version_dir/workflow.json`). Existing validation helpers unchanged.

**Validation** (`app/comfyui/validation.py`): `validate_workflow(spec, template,
object_info) -> (errors, warnings)`. Errors block execution (template integrity,
missing custom nodes, invalid mappings, no output mapping, missing *core* models,
input-type/ComfyUI-field type incompatibility). Warnings are non-blocking
(missing LoRAs).

**Inspection** (`app/comfyui/inspection.py`): `inspect_workflow(template,
object_info)` → node report (per-node class + inputs with ComfyUI types/options,
image loaders, terminal output nodes via link analysis, custom + missing
classes, referenced models with found/missing, and name/type-based hints for
text/seed/dimension/number/boolean/combo). Node semantics are surfaced as
hints; mapping is always set explicitly by the user. `object_info=None` (ComfyUI
down) degrades gracefully.

**Generation** (`app/services/generation.py`): `get_spec(id, version=None)`
version-aware; `retrieve_outputs` uses the job's recorded `workflow_version`
(an uploaded revision cannot change which nodes past jobs capture);
`submit_generation(..., ignore_enabled=False)` (disabled check bypassed only for
tests); `test_workflow(id, version=None, test_inputs=None)` validates (errors +
warnings), then, if eligible, submits a real monitored job via
`submit_generation(..., ignore_enabled=True)` and returns `job_client_id` — the
client polls the job to completion; "success" is only after real inference +
output retrieval.

**API** (`app/api/workflows.py`): existing list/get/patch/test extended + new
`POST /api/workflows` (upload new workflow, disabled by default),
`GET/POST /{id}/versions`, `GET /{id}/versions/{v}` (inspection report + full
mappings), `GET /{id}/versions/{v}/template` (raw JSON, for new-version prefill),
`PUT /{id}/versions/{v}/mappings`, `POST /{id}/versions/{v}/validate`,
`POST /{id}/versions/{v}/activate`, `POST /{id}/test` (version-aware +
`test_inputs`). New schemas in `app/schemas/jobs.py` (`WorkflowVersionOut`,
`WorkflowUpload`, `WorkflowVersionUpload`, `WorkflowMappings`,
`WorkflowTestRequest`; `WorkflowOut` + `active_version`, `WorkflowTestResult` +
`warnings/submitted/job_client_id`). Node IDs stay **strings** (person-swap uses
`"15:20"`).

**Frontend** (`src/pages/Workflows.tsx`, `src/services/workflows.ts`,
`src/types/workflows.ts`): full management UI — workflow cards (category +
enabled badge + active version), detail view (version list + set-active, node
inspection panel, mapping editor with node/field dropdowns from the report,
validate → errors/warnings, real test generation with dynamic per-type form
incl. image asset picker + job polling), upload dialog (API-format JSON),
new-version dialog (prefilled from the current template + mappings), enable/disable,
edit name/description. New `.wf-*` styles in `src/styles.css`. The Gen/Mod/Swap
pages are unchanged (still resolve the enabled workflow by category).

**Key invariants:** no new DB tables (versions live on disk; `jobs` already
records `workflow_id`/`workflow_version`/`inputs_json`); disabling blocks *new*
jobs only; each version immutable; migration idempotent.

### Phase 7 live acceptance (thor128-2)

Verified against live ComfyUI 0.46.0 after deploy + service restart:

- **Migration:** all 3 built-ins seeded to `/var/lib/sceneforge/workflows/` in
  the versioned layout (`config.json` + `versions/1/{config.json,workflow.json}`);
  legacy top-level `workflow.json` removed; idempotent on restart.
- **Inspect + validate:** all 3 built-ins → `ok=true`, 0 errors, 0 warnings
  (node counts 9/9/28; correct output nodes; no missing classes/models).
- **Execute (real inference):** gen, image-edit, and person-swap each submitted a
  real job via `POST /api/workflows/{id}/test`, polled to `completed` with 1
  output; jobs recorded `workflow_version=1`.
- **Upload → validate → test:** a freshly uploaded workflow (201, disabled)
  validates and runs a real test to completion (version-aware retrieval).
- **Validation failure:** a workflow referencing a missing class reports
  `ok=false` with the missing-class error (+ "no output mapping").
- **Version management:** new version becomes active (`v2`), version list shows
  both, "set active v1" switches `active_version` back.
- **Disable gating:** disabling a workflow makes `POST /api/generate/{id}`
  return 409; re-enabling restores it. Existing jobs unaffected.
- **Regression gate:** health, comfyui status, workflows, jobs, scene/character
  libraries (incl. `?favorite=true`), galleries, settings all 200; index.html
  served; gen/mod/swap each resolve exactly one enabled workflow by category.

**Bugs found + fixed during live acceptance** (unit tests couldn't catch them —
they only manifest with real ComfyUI / same-session uploads):
1. `inspect_workflow` crashed on node classes whose `output` is a bare **list**
   of types (not a `{type,name}` dict) — normalized both forms.
2. `validate_version` called the async `object_info` helper without `await` and
   read `spec.template` instead of `load_template(spec)`.
3. Validation falsely flagged `image`→combo mappings; `LoadImage.image` is a
   combo file-picker, so `image` (and `combo`) are valid for combo fields.
4. `get_specs()` was `lru_cached`; `submit_generation` resolved the active spec
   from that cache, so a workflow uploaded in the same session was "Unknown" and
   testing a non-active version used the active template. `get_spec` now always
   reads from disk and threads the requested version through `submit_generation`.

## Conventions

- Backend: FastAPI + SQLAlchemy 2.0 sync sessions (`SessionLocal`), Pydantic schemas in `app/schemas/`, services in `app/services/`. Tests in `backend/tests/` (pytest; `tests/test_assets.py` sets a temp `SCENEFORGE_DATA_DIR` at import and other test modules import from it).
- Frontend: React 18 + TS + Vite 5, react-router-dom 6. No test runner; `npm run build` (`tsc && vite build`) is the gate. Pages in `src/pages/`, components in `src/components/`, API clients in `src/services/`, types in `src/types/`. Dark theme via CSS variables in `src/styles.css` (see existing classes: `.page`, `.settings-card`, `.field`, `.btn`, `.asset-grid`, `.dialog`, `.form-error`).
- API shape for jobs: `JobOut` (`client_id` is the job's public id; `outputs[].thumbnail_url` / `original_url`), `WorkflowOut` (inputs with `type`/`required`/`default`/`auto`).
- ComfyUI input values: `seed: "random"` for random; numbers coerced by the adapter; image inputs are `{"asset_file_id": <id>}`.

## Known open items

- Reboot survival of `sceneforge.service` never explicitly verified (restart survival is).
- ComfyUI `server.client_id` is global last-write-wins; if the user's ComfyUI UI submits prompts concurrently, SceneForge WS events may miss — the periodic resync covers this (jobs still complete, possibly slightly later).
