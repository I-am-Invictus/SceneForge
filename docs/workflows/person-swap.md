# Workflow Inspection: api_PersonSwapWorkflow.json

Source: `comfy_ui_workflows_ref/api_PersonSwapWorkflow.json` (read-only reference)
Inspected against: ComfyUI 0.46.0 on thor128-2 (`http://127.0.0.1:8188/object_info`)

## Validity

- Valid ComfyUI **API-format** JSON.
- Node IDs include namespaced IDs (`15:20`, `16:40`, …) — legal in API format.
- Executable via `POST /prompt` after scene + character images are uploaded and mapped.

## Node inventory

| Node ID | Class | Title | Role |
|---|---|---|---|
| 1 | AUSBOSS_NODES_WorkflowNote | 🆎 AusBoss | Documentation note (no execution effect) |
| 2 | LoadImage | Load Image - Scene picture | **Scene image** |
| 3 | LoadImage | Load Image - Character 1 | **Character 1** |
| 4 | AUSBOSS_NODES_Text | Text - Who to replace | **Composition prompt** |
| 5 | PrimitiveBoolean | Boolean - Swap the whole body | **Swap mode** (true=body, false=head) |
| 6 | AUSBOSS_NODES_Seed | Seed | **Seed** |
| 7 | CLIPLoader | Text encoder | Model loader |
| 8 | VAELoader | VAE | Model loader |
| 9 | UNETLoader | Diffusion model | Model loader |
| 10 | AUSBOSS_NODES_LoraLoader | LoRA Loader - Body swap LoRA | LoRA stack (body) |
| 11 | AUSBOSS_NODES_LoraLoader | LoRA Loader - Head swap LoRA | LoRA stack (head) |
| 17 | AUSBOSS_NODES_Compare | Image Compare A/B - Before and after | Before/after preview |
| 18 | AUSBOSS_NODES_SaveImage | Save Image | **Output** |
| 19 | AUSBOSS_NODES_RunTimer | Run Timer | Timing helper |
| 51 | AUSBOSS_NODES_ShowText | Show Text - Request sent to Qwen | Debug display |
| 53 | AUSBOSS_NODES_Integer | Integer - Steps | **Steps** (25) |
| 15:20 | StringFormat | Whole body request | Prompt template (body) |
| 15:21 | StringFormat | Head only request | Prompt template (head) |
| 15:23 | ComfySwitchNode | Body or head request | Selects prompt template |
| 15:24 | RegexReplace | Empty who: one-person wording | Prompt cleanup |
| 16:40 | AUSBOSS_NODES_ImageResize | Scene to 2 MP | Scene pre-resize |
| 16:41 | AUSBOSS_NODES_ImageResize | Character 1 to 0.59 MP | Character pre-resize |
| 16:43 | ComfySwitchNode | Body or head model | Selects LoRA stack |
| 16:44 | QwenImage21Cache | Reference cache | Model cache |
| 16:46 | TextEncodeQwenImage21 | Encode the pictures and the request | Encodes prompt + 2 images |
| 16:48 | KSampler | Sampler | Sampler |
| 16:49 | VAEDecode | Decode | Decode latents |
| 16:50 | SplitImageWithAlpha | Drop the alpha channel | Post-processing |

- Image-loading nodes: **2** (scene), **3** (character 1).
- **No second-character LoadImage exists in this export.** See note 1.
- Output node: **18** (AUSBOSS_NODES_SaveImage, prefix `qwen21_person_swap`).
- Secondary visual: **17** Compare (before=generated, after=scene) — UI-only preview.
- Prompt: **4** `text` — a short "who to replace" phrase
  (e.g. "the woman on the left"). The full request is assembled internally by
  nodes 15:20/15:21 + 15:23 + 15:24. SceneForge supplies only the phrase.
- Swap mode: **5** `value` boolean (true = whole body, false = head only).
- Seed: **6** `seed`. Steps: **53** `value` (25).
- Resolution: scene resized to 2 MP (**16:40**), character to 0.59 MP
  (**16:41**); `resolution` on 16:46 is 0 (auto).

## Model dependencies (verified present)

| Node | Field | Model | Status |
|---|---|---|---|
| 9 | unet_name | qwen_image_2.1_int8_convrot.safetensors | ✓ in UNETLoader list |
| 7 | clip_name | qwen3vl_8b_int8_convrot.safetensors | ✓ in CLIPLoader list |
| 8 | vae_name | qwen_image_2.1_vae_bf16.safetensors | ✓ in VAELoader list |
| 10 | loras (enabled row) | bfs_body_swap_v1.0_qwen_2.1.safetensors | ✓ in models/loras |
| 11 | loras (enabled row) | bfs_head_v1.1_qwen_2.1.safetensors | ✓ in models/loras |
| 10, 11 | loras (disabled row) | p_qwen_image_2.1_8step_v0.1-comfyui-T8.safetensors | ✓ in models/loras (disabled) |

## Custom node dependencies (verified present)

| Pack | Nodes | Status |
|---|---|---|
| ausboss-nodes | WorkflowNote, Text, Seed, LoraLoader ×2, Compare, SaveImage, RunTimer, ShowText, Integer, ImageResize ×2 | ✓ all in object_info |
| comfy-core (0.38+) | StringFormat, RegexReplace, ComfySwitchNode ×2, QwenImage21Cache, TextEncodeQwenImage21, SplitImageWithAlpha | ✓ all in object_info |

## Proposed SceneForge mapping

| SceneForge input | Node ID | Class | Field | Type | Req/Opt | Default (in file) |
|---|---|---|---|---|---|---|
| scene_image | 2 | LoadImage | image | image (upload) | required | `87777820_015_3373.jpg` |
| character_1 | 3 | LoadImage | image | image (upload) | required | `0010-10_w600.jpg` |
| character_2 | — | — | — | image (upload) | **unsupported in this export** | — |
| composition_prompt ("who to replace") | 4 | AUSBOSS_NODES_Text | text | text | required | "Replace the women in the car" |
| swap_mode (whole body / head only) | 5 | PrimitiveBoolean | value | boolean | optional | true (whole body) |
| seed | 6 | AUSBOSS_NODES_Seed | seed | seed (INT) | optional (randomize) | 128379130583501 |
| steps | 53 | AUSBOSS_NODES_Integer | value | number (INT) | optional | 25 |
| scene_megapixels (advanced) | 16:40 | AUSBOSS_NODES_ImageResize | megapixels | number (FLOAT) | optional | 2 |
| character_megapixels (advanced) | 16:41 | AUSBOSS_NODES_ImageResize | megapixels | number (FLOAT) | optional | 0.59 |
| speed_lora (advanced) | 10, 11 | AUSBOSS_NODES_LoraLoader | loras (JSON string) | boolean → rewrites enabled flag of `p_qwen_image_2.1_8step…` row | optional | disabled (use with steps=8) |

Not mapped (fixed in template): model loaders (7, 8, 9), prompt assembly chain
(15:20, 15:21, 15:23, 15:24), resize geometry fields, LoRA stack contents
(except optional speed row), 16:43, 16:44, 16:46 (negative_prompt, resolution),
16:48 (cfg=1, euler/simple, denoise=1), 16:49, 16:50, UI helpers (1, 19, 51).

## Output retrieval

- Primary: node **18** `images` (AUSBOSS_NODES_SaveImage → `/view?type=output`).

## Notes / open questions

1. **Second character is NOT in this export.** The note node (1) describes a
   "Second character" feature toggled with Ctrl+B, but the API JSON contains
   no second LoadImage, and the prompt templates (15:20/15:21) only reference
   `<image1>` (scene) and `<image2>` (character 1). `TextEncodeQwenImage21`
   accepts growable `images` (image_1…image_n), but nothing in the templates
   references `<image3>`, so a third image would not be addressed by the prompt.
   → Two-character swapping requires a re-export with the second character
     nodes enabled, or a new workflow. Until then SceneForge registers this
     workflow with **character_1 only** (required), no character_2.
2. The composition prompt is a *replacement target phrase*, not a free
   layout description (per the note: "the woman on the left", "the man's head
   and hair"). The Phase 6 UI should label it accordingly.
3. Swap mode (node 5) switches both the prompt template and the LoRA stack —
   a single boolean is sufficient; no separate head/body workflows needed.
4. Steps default 25; the note recommends 8 when the Speed LoRA row is enabled.
