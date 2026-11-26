# Workflow Inspection: api_ImageGenerationWorkflow.json

Source: `comfy_ui_workflows_ref/api_ImageGenerationWorkflow.json` (read-only reference)
Inspected against: ComfyUI 0.46.0 on thor128-2 (`http://127.0.0.1:8188/object_info`)

## Validity

- Valid ComfyUI **API-format** JSON (node ID → `{inputs, class_type, _meta}`).
- Executable via `POST /prompt` without modification.

## Node inventory

| Node ID | Class | Title | Role |
|---|---|---|---|
| 3 | KSamplerAdvanced | KSampler (Advanced) | Sampler |
| 4 | VAELoader | Load VAE | VAE loader |
| 11 | VAEDecode | VAE Decode | Decode latents |
| 13 | SaveImageAdvanced | Save Image (Advanced) | **Output** |
| 15 | EmptyLatentImage | Empty Latent Image | Resolution / batch |
| 16 | TextEncodeQwenImageEdit | Text Encode Qwen Image Edit | **Positive prompt** |
| 25 | CLIPTextEncode | CLIP Text Encode (Prompt) | **Negative prompt** |
| 26 | CLIPLoaderGGUF | CLIP Loader (GGUF) ⚡ | Text encoder loader |
| 28 | UnetLoaderGGUF | UNET Loader (GGUF) ⚡ | Diffusion model loader |

- Image-loading nodes: **none** (pure text-to-image).
- Output node: **13** (SaveImageAdvanced, `images` output).
- Prompt inputs: **16** `prompt` (positive, currently empty), **25** `text` (negative, currently empty).
- Seed: **3** `noise_seed` (INT, control_after_generate).
- Resolution: **15** `width` / `height` (currently 800×1024), `batch_size` (currently **2**).
- Sampler settings: steps=4, cfg=1, euler / simple, add_noise=enable, start=0, end=10000, return_with_leftover_noise=disable.

## Model dependencies (verified present)

| Node | Field | Model | Status |
|---|---|---|---|
| 28 | unet_name | qwen-image-edit-2511-uncensored-Q4_K_M.gguf | ✓ in UnetLoaderGGUF list |
| 26 | clip_name | Qwen2.5-VL-7B-Instruct-q4_0.gguf | ✓ in CLIPLoaderGGUF list |
| 4 | vae_name | qwen_image_vae.safetensors | ✓ in VAELoader list |

## Custom node dependencies (verified present)

| Pack | Nodes | Status |
|---|---|---|
| comfyui-gguf-loader | CLIPLoaderGGUF, UnetLoaderGGUF | ✓ |

## Proposed SceneForge mapping

| SceneForge input | Node ID | Class | Field | Type | Req/Opt | Default (in file) |
|---|---|---|---|---|---|---|
| prompt | 16 | TextEncodeQwenImageEdit | prompt | text | required | `""` (empty) |
| negative_prompt | 25 | CLIPTextEncode | text | text | optional | `""` (empty) |
| width | 15 | EmptyLatentImage | width | number (INT, step 8) | required (derived from aspect ratio) | 800 |
| height | 15 | EmptyLatentImage | height | number (INT, step 8) | required (derived from aspect ratio) | 1024 |
| batch_size | 15 | EmptyLatentImage | batch_size | number (INT) | optional | 2 |
| seed | 3 | KSamplerAdvanced | noise_seed | seed (INT) | optional (randomize) | 493374140594327 |
| steps | 3 | KSamplerAdvanced | steps | number (INT) | optional | 4 |
| cfg | 3 | KSamplerAdvanced | cfg | number (FLOAT) | optional | 1 |
| sampler_name | 3 | KSamplerAdvanced | sampler_name | combo | optional | euler |
| scheduler | 3 | KSamplerAdvanced | scheduler | combo | optional | simple |

Not mapped (fixed in template): add_noise, start_at_step, end_at_step,
return_with_leftover_noise, model loaders (4, 26, 28), filename_prefix/format (13).

## Output retrieval

- Primary: node **13** `images` (SavedImages → `/view?type=output`).

## Notes / open questions

1. `batch_size` is **2** in the file → each run produces 2 images. Confirm whether
   to keep 2 as default or expose it (proposed: expose, default from file).
2. Positive prompt node is the Qwen-Edit encoder (16), negative is a plain
   CLIPTextEncode (25). This is how the workflow was built; mapping is
   unambiguous but confirm.
3. This workflow uses the Qwen-Image-**Edit** GGUF model for plain
   text-to-image (no image input connected to node 16's optional `image`).
