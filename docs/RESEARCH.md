# Model sources and limitations

This application initially supports Qwen-Image-2.1 through a specific ComfyUI/GGUF pipeline. It does not implement every capability mentioned by upstream model documentation.

- [Qwen model and license](https://huggingface.co/Qwen/Qwen-Image-2.1)
- [GGUF distribution](https://huggingface.co/leejet/Qwen-Image-2.1-GGUF)
- [Comfy-Org encoder/VAE distribution](https://huggingface.co/Comfy-Org/Qwen-Image-2.1)
- [Pinned model files](../runtime/models.json)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)

The local tested combination uses Q4_K diffusion weights, a w4a8 text encoder and bf16 VAE. The workbench exposes cache settings separately from weight quantization. Native reference editing uses the model's conditioning pipeline; the interface does not claim pixel-locked editing or arbitrary node composition.

Model materials use the Qwen Research License. The independent application's code license does not override those terms. Verify upstream license and model-card changes before adopting a different revision.
