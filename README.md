# Orion Image Workbench

**Local image generation, sequential batches, and reproducible workflow experiments.**

[简体中文](README.zh-CN.md) · [Installation](docs/en/installation.md) · [Workbench guide](docs/PRO_GUIDE.md) · [Contributing](CONTRIBUTING.md)

A lightweight browser workbench for ComfyUI, initially supporting **Qwen-Image-2.1**. Create images, edit references, produce transparent PNGs, compare fixed-seed experiments, and keep the parameters behind each result.

![Orion Image Workbench](docs/media/workbench-demo.png)

UI preview with the bundled synthetic example and demonstration state; no private gallery.

[![CI](https://github.com/orionarch26/orion-image-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/orionarch26/orion-image-workbench/actions/workflows/ci.yml)

## What it does

- Simple creation studio and a professional parameter workbench.
- Text-to-image, reference editing and transparent output.
- Sequential batches of 2–5 images; consecutive seeds or a single controlled parameter change.
- Persistent task tracking, idempotent submission retries, targeted cancellation and batch records.
- A/B comparison, 100% / 200% detail inspection and synchronized scrolling.
- Reusable recipes, JSON import/export and the last ten saved preset revisions.
- A model downloader with pinned revisions, SHA-256 verification and resumable downloads.

## Current support

| Area | Status |
|---|---|
| Linux + NVIDIA | Tested on an RTX 4070 Laptop with 8GB VRAM and 16GB RAM |
| Windows model downloader | Independent downloader with a Windows/Linux CI matrix (Python 3.10 / 3.12) |
| Full Windows application | Planned; application locking/process management still requires Linux |
| Language | Application UI: Chinese. README/install instructions: English and Chinese. Complete UI i18n is planned |
| Backend | Requires the documented ComfyUI and custom-node setup |

This is an initial source release. Downloading the models alone does **not** install ComfyUI, PyTorch, CUDA support or custom nodes. Use the [installation guide](docs/en/installation.md) to prepare the backend. No hosted inference API key is required; model licenses apply separately.

## Quick start: prepared Linux backend

Prerequisites: Git, Python 3.12, compatible NVIDIA driver, the documented ComfyUI environment at `ComfyUI/.venv`, and required custom nodes. See [fresh checkout setup](docs/en/installation.md).

```bash
git clone https://github.com/orionarch26/orion-image-workbench.git
cd orion-image-workbench

# First prepare ComfyUI and its Python environment as described in the guide.
# Inspect download sources, sizes and license without downloading:
python3 scripts/download_models.py --list

# Download only the model files. The terminal asks you to review the license.
python3 scripts/download_models.py

# Verify installed files; no downloads:
python3 scripts/download_models.py --check

# Install the lightweight web application into the prepared backend environment:
ComfyUI/.venv/bin/python -m pip install -r requirements-app.lock
./start.sh
```

Open **http://127.0.0.1:7860** for the studio or **http://127.0.0.1:7860/pro** for the workbench. If the managed backend is stopped and default model files are missing, an interactive startup offers to download them. A running backend is checked through its API; missing models there produce a diagnostic rather than modifying that environment automatically.

## Model downloads

The three files total approximately **11.19 GB** (10.42 GiB), excluding the backend and Python dependencies.

| Component | File | Size |
|---|---|---:|
| Diffusion model | `qwen_image_2.1-Q4_K.gguf` | 4.20 GB |
| Text encoder | `qwen3vl_8b_w4a8.safetensors` | 6.31 GB |
| VAE | `qwen_image_2.1_vae_bf16.safetensors` | 0.68 GB |

Download to another ComfyUI installation:

```bash
python3 scripts/download_models.py --models-dir /path/to/ComfyUI/models
```

Windows PowerShell (model files only; Python 3.10+):

```powershell
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models'
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models' --check
```

After reading and accepting the linked model license, unattended installation can use `--accept-model-license`. Existing valid files are reused. Interrupted downloads remain as `.part` files and resume on rerun. A mismatched existing model is not replaced unless you specify `--replace-invalid`; the replacement is installed only after its SHA-256 passes. The installer never silently changes quantization or upgrades a model revision.

A normal startup checks for missing configured files, not the full hash of 11GB of weights. Use `--check` for integrity verification. Custom model filenames are not automatically substituted with this profile.

## First workflow

1. Start with a 768×768 image, 20 steps, Euler / Simple and CFG=1.
2. In the workbench choose consecutive-seed batches, count 3, seed -1.
3. Pick a result and load its parameters to keep the actual seed.
4. Compare steps 20 / 30 / 40 using a single-variable experiment.
5. Save the recipe that produces the result you prefer.

The five active-task slots are shared by the studio and workbench. Batches are executed sequentially by the backend, not concurrently on the GPU. More steps or a different sampler do not guarantee better images.

## Data and privacy

Outputs and task metadata are stored in `output/`; task state and presets are stored in `state/`. These directories, model weights, logs and uploaded references are not versioned. The application binds to loopback and has no usage telemetry. Installation contacts the dependency/model download services.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
```

Unit/API tests use fake inference clients and do not require a GPU or model downloads. Browser and manual GPU test instructions are in [testing.md](docs/testing.md).

## Licensing and credits

Independent application code: [Apache-2.0](LICENSE). Model materials: [Qwen Research License](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE), including its research/evaluation and separate commercial-permission requirements. See [third-party notices](THIRD_PARTY_NOTICES.md) for ComfyUI, GGUF and model sources.

Built on the work of Qwen, ComfyUI and ComfyUI-GGUF contributors. This project is independently maintained by the repository contributors.
