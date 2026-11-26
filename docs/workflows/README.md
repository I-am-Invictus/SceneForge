# Workflow Inspection Reports

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

## Open questions (need owner decision before registration)

1. **Person swap / second character:** the export contains no second-character
   node (only scene + character 1 are wired to the encoder, and prompt
   templates reference only `<image1>`/`<image2>`). Options:
   - a) register as one-character workflow now, or
   - b) re-export the workflow with the "Second character" nodes enabled
     (Ctrl+B in ComfyUI) and provide the new file.
2. **Image edit output:** the workflow ends in a `PreviewImage` node
   (history output type `temp`), not `SaveImage` (type `output`). Accept
   preview outputs, or add a SaveImage node to the registered copy
   (reference file untouched)?
3. **Image generation batch:** the file has `batch_size: 2` (two images per
   run). Keep as default or set to 1?
