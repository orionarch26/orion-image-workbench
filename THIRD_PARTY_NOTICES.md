# Third-party notices

The root Apache-2.0 license covers this project's independent application code and documentation, except materials identified below. It does not relicense ComfyUI, model weights, or other third-party material.

## ComfyUI

- Source: https://github.com/comfyanonymous/ComfyUI
- Tested revision: `c194dd00cd42aa18d9dbf27d977bf6b85d9ea565`
- License: [GNU GPL v3](https://github.com/comfyanonymous/ComfyUI/blob/c194dd00cd42aa18d9dbf27d977bf6b85d9ea565/LICENSE)

ComfyUI is a separately installed backend process. Its source, Python environment and models are not distributed in this repository.

## ComfyUI-GGUF compatibility patch

- Source: https://github.com/city96/ComfyUI-GGUF
- Tested revision: `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`
- License: Apache-2.0; included in `licenses/ComfyUI-GGUF-Apache-2.0.txt`.
- Local modification: `docs/gguf-local.patch` adds Qwen-Image-2.1 architecture detection in `tools/convert.py`.

The patch contains upstream context and a project-specific modification. Apply it only to the documented revision after `git apply --check` succeeds; do not apply blindly to a newer plugin.

## Qwen-Image-2.1 model materials

Model weights are not included. The separately downloaded diffusion model, text encoder and VAE remain subject to their applicable model terms. The downloader identifies exact repositories, revisions, sizes and SHA-256 values in `runtime/models.json`.

Read the [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE). Its permitted non-commercial purposes are research and evaluation; commercial use requires a separate license. The application's Apache-2.0 license does not grant additional rights to the model materials.

This is an independent project, not an official Qwen or ComfyUI application.

## Example asset

`examples/input_cat.png` is a synthetic cat image generated during this project's local Qwen-Image-2.1 testing, supplied as a reference-input example. It is not a third-party stock photograph. Its presence does not grant additional rights to the model weights. Personal galleries and uploaded reference images are excluded from the repository.

## Python dependencies

Dependencies are installed separately. See their distributions for full notices:

- aiohttp: Apache-2.0 — https://github.com/aio-libs/aiohttp
- Pillow: HPND — https://github.com/python-pillow/Pillow
- markdown-it-py: MIT — https://github.com/executablebooks/markdown-it-py
- Playwright (tests only): Apache-2.0 — https://github.com/microsoft/playwright-python
