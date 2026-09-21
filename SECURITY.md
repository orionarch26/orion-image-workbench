# Security policy

This initial source version is designed for one local user. The UI listens on loopback, checks Host/Origin, and does not provide authentication suitable for a public multi-user deployment. Do not expose it directly to the internet.

## Reporting

Please use **Report a vulnerability** on the repository's [Security page](https://github.com/orionarch26/orion-image-workbench/security). Avoid public issues containing exploit details, credentials, personal images or prompt history. There is no guaranteed response-time SLA.

The current default branch is the supported development version. Release support periods will be documented when versioned releases exist.

## Boundaries

- ComfyUI, custom nodes, model repositories and Python dependencies are separate trust boundaries.
- Model files are fetched from pinned upstream revisions and verified against SHA-256 in the repository manifest. This checks file identity, not the safety of every upstream component.
- Browser API submission supports the known workflow schema rather than arbitrary Python execution.
- Keep task state and model directories writable only by the local account.
- Application telemetry is not collected. Download/install operations contact the corresponding upstream services.

中文：目前面向本机单用户，不应直接部署为公网服务。安全问题通过仓库Security页面私下报告，不在公开Issue中附带凭据、个人图片或完整任务库。
