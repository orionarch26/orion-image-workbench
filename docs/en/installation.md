# Installation

This initial version runs the application on Linux with a local NVIDIA-backed ComfyUI installation. The model downloader also has a Windows-compatible implementation; Windows application support and Windows GPU validation are not complete.

## 1. Prepare ComfyUI

Use Python 3.12 and a working NVIDIA driver. Check the driver with `nvidia-smi`. This project does not install or replace system drivers.

The tested backend is ComfyUI commit `c194dd00cd42aa18d9dbf27d977bf6b85d9ea565`, with city96/ComfyUI-GGUF commit `6ea2651e7df66d7585f6ffee804b20e92fb38b8a` and the included compatibility patch. Model filenames are configured in `studio.toml`.

If you already have that compatible environment, place it at `ComfyUI/` or create a Linux symlink to it from the project root:

```bash
ln -s /absolute/path/to/your/ComfyUI ComfyUI
```

The launcher expects `ComfyUI/.venv/bin/python`. Do not point this at an unrelated environment and allow dependency changes without reviewing them. To keep another installation untouched, prepare a separate directory instead.

For a fresh source setup, the backend source steps are:

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git ComfyUI
git -C ComfyUI checkout c194dd00cd42aa18d9dbf27d977bf6b85d9ea565
git clone https://github.com/city96/ComfyUI-GGUF.git ComfyUI/custom_nodes/ComfyUI-GGUF
git -C ComfyUI/custom_nodes/ComfyUI-GGUF checkout 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
git -C ComfyUI/custom_nodes/ComfyUI-GGUF apply --check ../../../docs/gguf-local.patch
git -C ComfyUI/custom_nodes/ComfyUI-GGUF apply ../../../docs/gguf-local.patch
python3.12 -m venv ComfyUI/.venv
```

Install a mutually compatible CUDA-enabled PyTorch, torchvision and torchaudio combination using the [official PyTorch installer](https://pytorch.org/get-started/locally/), targeting `ComfyUI/.venv/bin/python`. The existing Linux test environment used PyTorch 2.14.0 with CUDA 13.0. A Linux package snapshot is not a Windows dependency lock.

Then install the backend/node/application dependencies:

```bash
ComfyUI/.venv/bin/python -m pip install -r ComfyUI/requirements.txt
ComfyUI/.venv/bin/python -m pip install -r ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt
ComfyUI/.venv/bin/python -m pip install -r requirements-app.lock
```

The source/patch and model combination was validated in the existing Linux environment. Rebuilding every GPU dependency from a clean virtual environment is a separate release-validation task; this initial release does not claim a turnkey cross-platform runtime installer.

## 2. Install model files

The downloader itself needs only Python 3.10+ and the standard library. It does not import torch or the web application.

```bash
python3 scripts/download_models.py --list
python3 scripts/download_models.py
python3 scripts/download_models.py --check
```

Read the model license shown by the installer. For unattended execution after accepting those terms, append `--accept-model-license`.

Expect approximately 11.19GB of model files plus backend dependencies and output space. Downloads use exact Hugging Face revisions and SHA-256 values from `runtime/models.json`. The downloader supports retries, HTTP Range resumption, per-file locking and atomic installation after validation.

If a server ignores Range, the partial file is restarted safely. Checksum failures are quarantined as `.invalid-*` files; inspect and remove these if disk space is needed. Existing mismatched target files are preserved unless `--replace-invalid` is explicitly supplied. No alternate model or mirror is chosen automatically.

To install weights for an external backend, use `--models-dir /path/to/ComfyUI/models`. This changes the downloader destination only; it does not change the application's backend directory or `studio.toml`.

## 3. Launch

```bash
./start.sh doctor
./start.sh
```

Open http://127.0.0.1:7860 or http://127.0.0.1:7860/pro . An existing compatible backend is reused. An application-started backend receives `--disable-comfy-compiler`, needed by the tested configuration. If another running backend lacks required capabilities, the app reports the incompatibility rather than stopping it.

Interactive startup can offer installation of missing default model files before starting a stopped backend. In unattended sessions it exits with instructions instead of prompting or unexpectedly downloading 11GB.

## 4. Stop and upgrade

Ctrl+C closes the application observer; backend computation is not cancelled. Reopen the UI to recover tracking. When the backend queue is empty, `./start.sh stop-backend` can stop the backend process owned by this launcher.

Before upgrades, back up configuration, `state/`, `output/` and `ComfyUI/input/`. Stop the observer before copying its SQLite database, or use SQLite's backup mechanism. Do not update the backend/plugin/model revisions during active tasks.

## Troubleshooting

| Symptom | Action |
|---|---|
| Missing `ComfyUI/.venv` | Prepare the backend environment in step 1 |
| CUDA unavailable | Verify driver and the PyTorch installation in the backend environment |
| Missing GGUF architecture | Verify the pinned plugin revision and patch |
| `aimdo memory compile` | Check that the backend uses `--disable-comfy-compiler` |
| Download interrupted | Rerun the same downloader command to resume |
| SHA-256 mismatch | Keep the existing model; inspect the quarantined download and source |
| Disk full | Leave space for incomplete downloads, existing targets and environment dependencies |
| OOM | Try 768×768, one reference, reference size 512, CFG=1; close other GPU workloads |
| Submission response lost | Retry the same submission ID through the UI; do not create a duplicate job |

## Windows model download

```powershell
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models'
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models' --check
```

This installs weights for an existing Windows ComfyUI installation. It does not make this version's Linux-oriented application launcher run on Windows.
