# User guide · Orion Image Workbench

[Installation](installation.md) · [Workbench](workbench.md) · [Suggested workflow](workflow.md)

After installation, run `./start.sh` and open http://127.0.0.1:7860. Choose a template, edit the description and click **Generate image**. Select **English** or **简体中文** in the navigation bar. The choice persists across pages; switching language does not translate your prompt or alter a task.

The professional page at http://127.0.0.1:7860/pro adds sequential batches, parameter experiments, ordered references, recipe revisions and A/B comparison.

Example prompt: `An orange cat sitting on a wooden table by a window, soft morning sunlight, realistic photography, natural fur detail, no text.`

Start with a 768×768 preview, 20 steps and CFG=1. Pick a composition, then load the result's actual seed before comparing parameters. The current draft is independent of the selected result and submitted jobs.

Model weights are not distributed in Git. Use `python3 scripts/download_models.py --list` to inspect sources, the same command without `--list` to download, and `--check` to verify installed files.

Full application validation covers the documented Linux NVIDIA environment. Windows application support remains planned; only the independent downloader is tested on Windows. Consult the installation guide for runtime requirements, data locations and model licensing.
