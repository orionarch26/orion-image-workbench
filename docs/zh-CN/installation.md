# 安装说明

当前应用版本支持已验证的Linux本地NVIDIA环境。模型下载器采用跨平台实现；Windows应用适配与GPU真机验证尚未完成。

## 1. 准备后端

需要Python 3.12和可用的NVIDIA驱动，先运行 `nvidia-smi` 检查。项目不替换系统驱动。

已测试版本：ComfyUI `c194dd00cd42aa18d9dbf27d977bf6b85d9ea565`；city96/ComfyUI-GGUF `6ea2651e7df66d7585f6ffee804b20e92fb38b8a`，附带 `docs/gguf-local.patch`。

已有兼容环境时，将其放在项目的 `ComfyUI/`，或从项目根目录建立Linux软链接：

```bash
ln -s /你的绝对路径/ComfyUI ComfyUI
```

启动器要求 `ComfyUI/.venv/bin/python`。如果不希望影响另一套环境，建议单独准备ComfyUI目录。

从源码准备后端：

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git ComfyUI
git -C ComfyUI checkout c194dd00cd42aa18d9dbf27d977bf6b85d9ea565
git clone https://github.com/city96/ComfyUI-GGUF.git ComfyUI/custom_nodes/ComfyUI-GGUF
git -C ComfyUI/custom_nodes/ComfyUI-GGUF checkout 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
git -C ComfyUI/custom_nodes/ComfyUI-GGUF apply --check ../../../docs/gguf-local.patch
git -C ComfyUI/custom_nodes/ComfyUI-GGUF apply ../../../docs/gguf-local.patch
python3.12 -m venv ComfyUI/.venv
```

根据[PyTorch官方安装选择器](https://pytorch.org/get-started/locally/)安装彼此兼容的CUDA版torch、torchvision、torchaudio，目标解释器使用 `ComfyUI/.venv/bin/python`。已有Linux实测环境使用PyTorch 2.14.0 / CUDA 13.0；这不代表可以将Linux依赖快照当成Windows锁文件。

```bash
ComfyUI/.venv/bin/python -m pip install -r ComfyUI/requirements.txt
ComfyUI/.venv/bin/python -m pip install -r ComfyUI/custom_nodes/ComfyUI-GGUF/requirements.txt
ComfyUI/.venv/bin/python -m pip install -r requirements-app.lock
```

当前源码、补丁和模型组合在已有Linux环境中验证过。所有GPU依赖的全新环境重建仍属后续发布验收，首版不宣称已完成跨平台一键安装。

## 2. 下载模型

下载器只需要Python 3.10+标准库，无需先安装PyTorch或网页依赖。

```bash
python3 scripts/download_models.py --list
python3 scripts/download_models.py
python3 scripts/download_models.py --check
```

第一条显示清单，第二条展示许可并询问下载，第三条完整校验但不下载。阅读并接受许可后，无交互安装可增加 `--accept-model-license`。

文件总计约11.19GB，另外预留后端、输出和下载缓存空间。脚本固定上游版本和SHA-256，支持重试、断点续传、下载锁、校验后原子安装。重复运行跳过已有正确文件。

下载中断时再次执行同一命令；校验失败的临时文件会隔离为 `.invalid-*`。已有同名异常模型默认不覆盖；检查后可用 `--replace-invalid`，仍须新文件校验正确才能替换。脚本不悄悄改量化或切镜像源。

其他后端目录使用 `--models-dir /path/to/ComfyUI/models`，这只改变模型下载目标，不改变应用配置。

## 3. 启动与日常使用

```bash
./start.sh doctor
./start.sh
```

画室：http://127.0.0.1:7860 ；工作台：http://127.0.0.1:7860/pro 。运行中的兼容后端会复用；未运行时自动启动并添加已验证配置所需的 `--disable-comfy-compiler`。

默认模型缺失、后端未启动且终端可交互时，启动器提供下载入口；后台无交互运行只提示安装命令，不擅自下载。已有后端不兼容时报告问题，不停止其他程序。

Ctrl+C关闭界面跟踪进程，后端任务继续运行；重新打开可恢复。队列空闲时 `./start.sh stop-backend` 仅停止本启动器记录并核对过的进程。

升级前备份配置、state、output和参考图。复制SQLite前停止观察进程，或使用SQLite备份机制；生成期间不要更新后端/节点/模型。

## 4. 常见问题

- `.venv`缺失：先准备第一步的后端环境。
- CUDA不可用：检查驱动和后端解释器里的PyTorch版本。
- GGUF架构不识别：检查节点commit和补丁。
- `aimdo memory compile`：检查后端启动参数。
- 下载中断：重新执行原下载命令续传。
- 哈希错误：保留旧模型，检查隔离文件与下载源。
- 显存不足：768方图、CFG=1、单张参考、参考大小512，并关闭其他GPU负载。
- 提交响应丢失：使用界面的“重试同一次提交”，避免创建重复任务。

## Windows下载模型文件

```powershell
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models'
py -3 scripts/download_models.py --models-dir 'D:\ComfyUI\models' --check
```

这为已有Windows ComfyUI安装提供权重，不代表Linux应用启动器已经完成Windows适配。
