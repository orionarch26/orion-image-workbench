# 使用指南 · 本地画室

[安装 / Installation](docs/zh-CN/installation.md) · [English setup](docs/en/installation.md) · [专业工作台](docs/PRO_GUIDE.md)

安装完成后运行 `./start.sh`，打开 http://127.0.0.1:7860 。选择模板，修改描述，点击生成。

专业页 http://127.0.0.1:7860/pro 支持批量、参数实验、参考图排序、配方版本和A/B。

简单提示词示例：一只橘猫坐在窗边的木桌上，清晨柔和阳光，真实摄影，自然毛发细节，无文字。

先用768方图、20步、CFG=1挑选构图，选定作品后固定种子再比较其他参数。生成记录包含实际参数；草稿可以独立编辑。

模型文件不随Git仓库发布。运行 `python3 scripts/download_models.py --list` 查看来源，`python3 scripts/download_models.py` 下载，`--check` 完整校验。

所有支持状态、环境前提、数据位置及许可见README和安装说明。当前完整应用在Linux NVIDIA环境验证，Windows应用与完整双语UI仍在路线图中。
