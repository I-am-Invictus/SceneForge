# Workflow Inspection: api_imageEditWorkflow.json

Source: `comfy_ui_workflows_ref/api_imageEditWorkflow.json` (read-only reference)
Inspected against: ComfyUI 0.46.0 on thor128-2 (`http://127.0.0.1:8188/object_info`)

## Validity

- Valid ComfyUI **API-format** JSON.
- Executable via `POST /prompt` after the source image is uploaded and mapped.

## Node inventory

| Node ID | Class | Title | Role |
|---|---|---|---|
| 1 | CheckpointLoaderSimple | Load Checkpoint | Model stack loader |
| 2 | KSampler | KSampler | Sampler |
| 3 | TextEncodeQwenImageEditPlus | …Input Prompt | **Edit instruction** (takes image2) |
| 4 | TextEncodeQwenImageEditPlus | …Negative (leave blank) | **Negative prompt** |
| 5 | VAEDecode | VAE Decode | Decode latents |
| 6 | PreviewImage | Preview Image | **Output (preview)** |
| 8 | LoadImage | Optional Input Image | **Source image** |
| 9 | EmptyLatentImage | Final Image Size | Resolution / batch |

- Image-loading node: **8** (LoadImage, currently `4098.jpg`).
- Output node: **6** (PreviewImage). ⚠️ See note 1.
- Prompt inputs: **3** `prompt` (instruction; currently "Make the background
  white and make him naked"), **4** `prompt` (negative, empty).
- Seed: **2** `seed` (INT, control_after_generate).
- Resolution: **9** `width` / `height` (1200×1200), `batch_size` (1).
- Sampler: steps=4, cfg=1, sa_solver / beta, denoise=1.

## Model dependencies (verified present)

| Node | Field | Model | Status |
|---|---|---|---|
| 1 | ckpt_name | Qwen-Rapid-AIO-NSFW-v23.safetensors | ✓ in CheckpointLoaderSimple list |

## Custom node dependencies (verified present)

| Class | Status |
|---|---|
| TextEncodeQwenImageEditPlus | ✓ in object_info |

All other nodes are ComfyUI core.

## Proposed SceneForge mapping

| SceneForge input | Node ID | Class | Field | Type | Req/Opt | Default (in file) |
|---|---|---|---|---|---|---|
| source_image | 8 | LoadImage | image | image (upload) | required | `4098.jpg` |
| prompt (instruction) | 3 | TextEncodeQwenImageEditPlus | prompt | text | required | "Make the background white and make him naked" |
| negative_prompt | 4 | TextEncodeQwenImageEditPlus | prompt | text | optional | `""` |
| width | 9 | EmptyLatentImage | width | number (INT, step 8) | optional (preserve source size by default) | 1200 |
| height | 9 | EmptyLatentImage | height | number (INT, step 8) | optional (preserve source size by default) | 1200 |
| batch_size | 9 | EmptyLatentImage | batch_size | number (INT) | optional | 1 |
| seed | 2 | KSampler | seed | seed (INT) | optional (randomize) | 65454653 |
| steps | 2 | KSampler | steps | number (INT) | optional | 4 |
| cfg | 2 | KSampler | cfg | number (FLOAT) | optional | 1 |
| denoise | 2 | KSampler | denoise | number (FLOAT 0–1) | optional | 1 |
| sampler_name | 2 | KSampler | sampler_name | combo | optional | sa_solver |
| scheduler | 2 | KSampler | scheduler | combo | optional | beta |

Not mapped (fixed in template): checkpoint (1), vae routing, denoise chain.

## Output retrieval

- Node **6** is a **PreviewImage**, not a SaveImage. Its output appears in
  `/history/{prompt_id}` under `outputs` with `type: "temp"`. It is retrievable
  via `GET /view?filename=…&subfolder=…&type=temp`.
- ⚠️ Preview images may be lower quality / resized depending on ComfyUI
  settings. Recommend confirming output quality with a test run (or adding a
  SaveImage node to a *copy* of the workflow if quality is insufficient — the
  reference file stays untouched).

## Notes / open questions

1. Output is PreviewImage (temp type). Acceptable, or should the registered
   (copied) template gain a SaveImage node?
2. Width/height default 1200×1200 regardless of source aspect. Per spec,
   SceneForge should preserve source dimensions by default → plan to set
   width/height from the uploaded image's dimensions at execution time
   (rounded to step 8), overridable by explicit values.
3. Instruction prompt node (3) also receives the source image via `image2` —
   no SceneForge input needed for that; it is wired internally.
