# Workflow Inspection Reports

## Status — Phase 7 (implemented)

The three reference workflows below are now **registered, versioned, and
managed in the app** (Workflows page). Workflows and every version are stored
under the persistent data dir (`/var/lib/sceneforge/workflows/`), not the app
dir, so deploys (which rsync the app dir with `--delete`) never wipe them:

```
{category}/{id}/config.json          -> {id, name, description, category, active_version}
{category}/{id}/versions/{N}/config.json    -> {version, inputs, outputs}
{category}/{id}/versions/{N}/workflow.json  -> raw ComfyUI API graph
```

- The three built-ins in the repo `workflows/` dir are an immutable **seed**;
  on first start they are migrated (idempotently) into the versioned layout as
  `v1`. `comfy_ui_workflows_ref/` remains read-only.
- The app performs **node inspection** (`object_info`-backed node classes,
  per-node inputs, image loaders, output nodes, custom-node dependencies,
  referenced models), **mapping editing**, **validation** (blocking errors vs
  warnings, incl. type compatibility), a **real test generation** (submits a
  monitored job; success only after it completes with outputs), **enable/disable**
  (disabled workflows block new jobs but existing jobs are unaffected), and
  **version management** (add immutable versions, switch the active one). Jobs
  record the exact `workflow_version` they ran and capture outputs with that
  version's mappings, so an uploaded revision cannot change past results.

The per-workflow inspection reports below were produced against the live
ComfyUI 0.46.0 installation on thor128-2 and match what the app's live node
inspection shows for the seeded `v1` of each workflow.

---

## Original reference inspection

Inspection of the three reference workflows in
`comfy_ui_workflows_ref/` (kept read-only), performed against the live
ComfyUI 0.46.0 installation on thor128-2.

| Report | Workflow | Category | Status |
|---|---|---|---|
| [image-generation.md](image-generation.md) | api_ImageGenerationWorkflow.json | general_generation | all nodes + models verified |
| [image-edit.md](image-edit.md) | api_imageEditWorkflow.json | image_modification | all nodes + models verified; output is PreviewImage |
| [person-swap.md](person-swap.md) | api_PersonSwapWorkflow.json | character_swap | all nodes + models verified; no second-character support in export |

## Verification summary

- All three files are valid ComfyUI **API-format** JSON.
- All 34 distinct node classes used across the three workflows exist in
  `/object_info` on thor128-2.
- All referenced models (checkpoints, GGUF UNet/CLIP, VAEs, LoRAs) resolve in
  the corresponding loaders' model lists.
- Custom packs in use: `comfyui-gguf-loader`, `ausboss-nodes` — both present.

## Resolved registration decisions

These were resolved when the workflows were registered for Phase 7:

1. **Person swap / second character:** registered as a **one-character**
   workflow (`scene_image` + `character_1`). A second character can be added
   later as a new version if a re-export with the "Second character" nodes is
   provided.
2. **Image edit output:** the registered copy maps its terminal image node
   (the `PreviewImage` output) as the `images` output, so results are captured
   and returned to the app.
3. **Image generation batch:** `batch_size` is exposed as an optional numeric
   input (default from the template); the UI does not force a specific value.

Each decision is editable without code changes: adjust the input/output mapping
or upload a new version from the Workflows page.
