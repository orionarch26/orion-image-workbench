# Testing

## No GPU required

Python 3.12 is the application test baseline:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_restore.py
.venv/bin/python scripts/review_pro_workbench.py
```

On Linux CI, install browser system packages with Playwright's `--with-deps` option. Tests use fake inference clients or mocked browser endpoints. They check workflow mapping, idempotency, atomic batch capacity, cancellation isolation, metadata persistence, reference validation and browser recovery/races. Model-installer tests use in-memory responses and small temporary files.

Windows CI runs the independent model-installer suite only. Passing it does not imply that the full application or GPU inference works on Windows.

## Real application / GPU tests

`tests/browser_pro.py` expects a running prepared application and existing gallery data. Its default mode modifies a test preset and uploads a fixture but does not generate a new GPU image. `tests/browser_batch.py --generate` creates a real two-image batch and verifies the resulting files. Use an isolated application/data environment before invoking these scripts.

The older `browser_smoke.py`, `browser_creation.py` and `runtime_smoke.py` are manual integration scripts that may generate images or modify task state. They are not ordinary CI checks.

Record model hashes, backend/plugin revisions, GPU/driver, resolution, sampler, steps, seed, cache hits and timing when reporting performance. Do not publish personal job records or gallery screenshots.

## Release hygiene

After staging the proposed commit, run:

```bash
python3 scripts/check_release.py
```

Review `git diff --cached --stat` and staged files. CI runs the same repository-boundary checks. A passing test suite is not a model-license review or a cross-platform GPU certification.
