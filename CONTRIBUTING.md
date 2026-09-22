# Contributing

English and Chinese contributions are welcome. Start with a focused issue for a behavior change, platform support or a new model profile. Bug fixes and documentation corrections can be proposed directly.

## Development environment

Use Python 3.12 on Linux for the full application:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-test.txt
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
.venv/bin/python -m playwright install chromium
.venv/bin/python tests/browser_restore.py
.venv/bin/python scripts/review_pro_workbench.py
```

The model downloader is independent of the application and can be tested on Windows using `py -3 -m unittest discover -s tests -p test_model_install.py`.

See [testing.md](docs/testing.md) before running GPU tests. Use a separate data/output directory. Tests must not cancel someone else's tasks or upload private galleries.

## Pull requests

Explain the concrete problem, resulting behavior, and relevant validation. Keep parameter schema and workflow mapping in sync. Preserve idempotent submission, exact-task cancellation, independent drafts, and backward compatibility with saved records.

Do not add model weights, environments, user outputs, SQLite databases, credentials or diagnostic bundles. Run `python scripts/check_release.py` against staged files before committing. Screenshots must use a clean demonstration dataset.

## Internationalization

English and Simplified Chinese UI are implemented. Follow [i18n.md](docs/i18n.md): use stable semantic message IDs, do not translate user prompts or API enums, and test language switches during active jobs. Documentation translations should preserve platform limitations and model-license distinctions.

## Licensing

By submitting a contribution, you confirm that you have the right to provide it under this project's applicable license. Identify copied/adapted third-party code and include its attribution and license. Model materials and upstream components retain their own terms; see `THIRD_PARTY_NOTICES.md`.

## 中文说明

欢迎提交小而明确的PR，说明问题、最终行为和验证。普通测试不需要GPU；真实出图测试会写入任务与作品，请使用独立测试数据目录。不要提交个人作品、任务库、模型、凭据或日志。翻译时保留支持范围和模型许可说明，不改动用户提示词、种子或幂等请求ID。
