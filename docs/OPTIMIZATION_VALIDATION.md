# Validation scope

The original local Linux environment used an RTX 4070 Laptop (8GB VRAM), 16GB RAM, Python 3.12, and the backend/node revisions documented in the installation guide.

Verified there: text generation, native reference editing, transparent PNG output, task recovery, targeted cancellation, advanced parameter mapping, batch submission, recipe versions and A/B comparison.

One two-image sequential batch at 768×768, 20 steps, Euler/Simple, CFG=1 took 37.555s and 31.991s of backend execution time. Neither sampler output was cached. Backend timestamps confirmed that the second execution started after the first finished. These figures exclude waiting behind earlier jobs and are not a general speed guarantee.

Current repository test commands and CI scope are documented in [testing.md](testing.md). Windows GPU inference, clean GPU-runtime reconstruction and full UI internationalization are not claimed as complete in this initial source release. Private execution logs and gallery screenshots are intentionally not distributed.
