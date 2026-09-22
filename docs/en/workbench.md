# Professional workbench guide

Complete [installation](installation.md), then open http://127.0.0.1:7860/pro. Choose English or 简体中文 from the header. Switching language preserves your draft, references, seed, selected results, pending submission ID and active-task tracking.

## First parameter experiment

1. Choose **Quick exploration** on the left. Enter a prompt and use 768×768, 20 steps, CFG=1 and Euler / Simple.
2. Click **Batch / Experiment** above the run button. Choose **Sequential seeds**, count 3, seed -1.
3. Submit the batch. The backend runs one image at a time; the queue displays each member's status.
4. Pick a result and click **Load parameters** to retain its actual seed.
5. Choose **One-parameter experiment**, select steps, and enter `20, 30, 40`.
6. Set completed results as A and B. Compare actual parameters and inspect at 100% or 200%.
7. Save a named preset. Saving the same name retains the last ten revisions, which can be loaded back into the draft.

## Parameters and references

- Standard output uses 40 steps; 20 is a useful preview. More steps do not guarantee better results.
- Start with CFG=1. A negative prompt participates in guidance when CFG is greater than 1, with additional computation.
- Seed -1 means random. A parameter experiment draws one random seed for the whole batch.
- Use at most 3 references in the intended order, at most 20MB each. Output follows image 1's aspect ratio.
- Cache precision does not change model weight quantization. Compare experimental settings against the defaults.
- Native editing uses denoise=1 and does not provide a pixel lock or mask-editing guarantee.

## Batches and recovery

Each batch contains 2–5 images. The studio and workbench share five active-task slots. Insufficient capacity rejects the entire batch; the backend does not run multiple GPU generations in parallel.

Closing the browser does not cancel registered jobs. Submitted parameters are fixed; editing or changing the UI language cannot change a submitted batch. Cancelling a batch targets unfinished members and retains completed results.

If a response is lost, **Retry same submission** reuses its original parameters and request ID. For timed-out or uncertain jobs, **Continue checking** queries the existing task without regenerating. Load a failed task's parameters and explicitly run it to create a new generation.

When zoomed, comparison scrolling synchronizes relative positions. Different sizes or compositions do not imply pixel correspondence.

## Recipes and exports

Recipe JSON contains parameters and reference filenames, not models or reference files. Load a recipe with missing references into the draft, then upload them in their original order before generating.

Task and batch exports record actual parameters, seeds and API workflows. They are records, not the same import format as recipe JSON. User prompts, preset names, filenames and exported records keep their original language.
