# Changelog

## Unreleased

Changes after v0.2.0 will be listed here.

## 0.2.0 — 2026-09-22

- Added English / Simplified Chinese UI and persistent language selection across creation, workbench and guides.
- Localized navigation, parameters, batches, recipe history, comparison, task stages and known validation messages.
- Preserved user text, references, drafts, pending request IDs and active tasks during language switches.
- Added English in-app guides, stable API error descriptors and translation catalog checks.
- Added browser regression coverage for both languages, active/pending tasks and mobile layouts.

Full Windows application support and LLM assistance are not included. The original v0.1.0 baseline remains available unchanged.

## 0.1.0 — 2026-09-22

- Imported the creation studio, professional workbench and durable ComfyUI task manager.
- Added sequential batches, controlled parameter experiments, A/B detail viewing and preset history.
- Added pinned model downloads with resumption, SHA-256 verification and startup guidance.
- Added English/Chinese README and installation documentation, contributor files and CI definitions.

Current limits: full app Linux only; Windows model-installer checks are separate from full Windows app support; full UI i18n and clean GPU-runtime reconstruction remain planned. This release freezes the initial public source baseline; it does not bundle a GPU runtime or model weights.
