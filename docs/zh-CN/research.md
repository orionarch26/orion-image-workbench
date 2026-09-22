# 模型来源与限制

本应用通过指定的 ComfyUI/GGUF 流程支持 Qwen-Image-2.1，并未实现上游模型展示的全部能力。

- [Qwen 模型及许可](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [GGUF 权重](https://huggingface.co/leejet/Qwen-Image-2.1-GGUF)
- [Comfy-Org 编码器与 VAE](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)
- [固定模型清单](../../runtime/models.json)
- [第三方声明](../../THIRD_PARTY_NOTICES.md)

本地已测试的组合是 Q4_K 生成权重、W4A8 文本编码器和 BF16 VAE。工作台中的缓存精度与模型权重量化是不同的设置。原生参考图编辑采用模型的条件输入流程，不提供像素锁定，也不等同于任意节点编辑器。

模型采用 Qwen Research License；独立应用的代码许可证不改变模型条款。使用其他版本前，请核对上游模型卡和许可。
