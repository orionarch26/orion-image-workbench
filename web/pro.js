"use strict";
const $ = (id) => document.getElementById(id);
const fields = [
  "prompt",
  "mode",
  "steps",
  "cfg",
  "negative_prompt",
  "sampler",
  "scheduler",
  "seed",
  "width",
  "height",
  "resolution",
  "cache_device",
  "cache_dtype",
  "tile_size",
];
const numbers = new Set([
  "steps",
  "cfg",
  "seed",
  "width",
  "height",
  "resolution",
  "tile_size",
]);
const base = {
  prompt: "",
  mode: "text",
  preset: "standard",
  steps: 40,
  cfg: 1,
  negative_prompt: "",
  sampler: "euler",
  scheduler: "simple",
  seed: -1,
  width: 1024,
  height: 1024,
  resolution: 768,
  cache_device: "auto",
  cache_dtype: "auto",
  tile_size: 512,
  images: [],
};
const terminal = new Set([
  "done",
  "failed",
  "cancelled",
  "timed_out",
  "submission_unknown",
  "lost",
]);
const names = {
  queued: I18n.msg("ui.waiting_to_submit"),
  submitting: I18n.msg("ui.submitting"),
  backend_queued: I18n.msg("ui.queued_in_backend"),
  running: I18n.msg("ui.generating"),
  reconnecting: I18n.msg("ui.reconnecting_68891"),
  downloading: I18n.msg("server.saving_images"),
  done: I18n.msg("ui.done"),
  failed: I18n.msg("ui.failed"),
  cancelled: I18n.msg("ui.cancelled"),
  cancelling: I18n.msg("ui.cancelling"),
  timed_out: I18n.msg("ui.timed_out_e512c"),
  lost: I18n.msg("ui.record_missing"),
  submission_unknown: I18n.msg("ui.submission_needs_review_70ff5"),
};
let refs = [],
  compiled = null,
  revision = 0,
  timer,
  submitting = false,
  uploading = false,
  active = null,
  selected = null,
  comparison = [null, null],
  nextPage = null,
  galleryItems = [],
  presets = [];
let selectionEpoch = 0,
  polling = false,
  listing = false,
  galleryLoading = false;
let jobsSignature = "",
  batchesSignature = "",
  validationFailures = 0;
let completedBatchSignature = "",
  galleryNeedsRefresh = false;
let queueLimit = 5,
  healthLoading = false;
function saved(key) {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
}
function persist(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}
function message(text, error = false) {
  I18n.text($("message"), text);
  $("message").className = error ? "error" : "";
}
async function api(path, data, headers = {}) {
  const response = await fetch(path, {
    ...(data !== undefined
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify(data),
        }
      : {}),
    signal: AbortSignal.timeout(20000),
  });
  let result;
  try {
    result = await response.json();
  } catch {
    const e = I18n.error(I18n.msg("ui.invalid_server_response_p0", {p0: response.status}));
    e.status = response.status;
    throw e;
  }
  if (!response.ok) {
    const e = I18n.error(result.error || I18n.msg("ui.request_failed_p0_85a3f", {p0: response.status}));
    e.status = response.status;
    throw e;
  }
  return result;
}
function act(label, fn, parent, cls = "") {
  const b = document.createElement("button");
  b.type = "button";
  I18n.text(b, label);
  b.className = cls;
  b.onclick = () =>
    Promise.resolve()
      .then(fn)
      .catch((e) => message(e.message, true));
  parent.append(b);
  return b;
}
function payload() {
  const p = {
    preset: Number($("steps").value) === 20 ? "preview" : "standard",
    images: $("mode").value === "text" ? [] : refs.map((r) => r.name),
  };
  for (const k of fields)
    p[k] = numbers.has(k) ? Number($(k).value) : $(k).value;
  return p;
}
function controls() {
  const pending = saved("proPending");
  $("run").disabled = !compiled || submitting || uploading || Boolean(pending);
  $("retry").hidden = !pending;
  $("retry").disabled = submitting;
}
function change() {
  compiled = null;
  revision++;
  validationFailures = 0;
  persist("proDraft", { parameters: payload(), references: refs });
  I18n.text($("draft-status"), I18n.msg("ui.draft_saved"));
  $("reference-box").hidden = $("mode").value === "text";
  $("canvas-size").hidden =
    $("mode").value === "edit" ||
    ($("mode").value === "transparent" && refs.length > 0);
  I18n.text($("validation"), I18n.msg("ui.validating_draft"));
  I18n.text($("run-summary"), I18n.msg("ui.waiting_for_validation"));
  controls();
  clearTimeout(timer);
  timer = setTimeout(validate, 350);
}
async function validate() {
  const rev = revision;
  try {
    const data = await api("/api/pro/preview", payload());
    if (rev !== revision) return;
    compiled = data;
    validationFailures = 0;
    $("validate-again").hidden = true;
    I18n.text($("flow-input"), {
      text: I18n.msg("ui.text_generation"),
      edit: I18n.msg("ui.p0_reference_images", {p0: refs.length}),
      transparent: I18n.msg("ui.rgba_transparent_asset"),
    }[data.payload.mode]);
    I18n.text($("flow-sample"), I18n.msg("ui.p0_p1_steps", {p0: data.payload.sampler || "euler", p1: data.payload.steps}));
    I18n.text($("flow-output"), I18n.parts(data.actual_size, " × "));
    I18n.text($("run-summary"), I18n.msg("ui.p0_steps_cfg_p1_p2", {p0: data.payload.steps, p1: data.payload.cfg || 1, p2: I18n.parts(data.actual_size, " × ")}));
    I18n.text($("validation"), I18n.msg("ui.validated_p0_nodes_cache_p1", {p0: Object.keys(data.workflow).length, p1: data.workflow["2"].inputs.dtype}));
    $("validation").className = "muted";
    $("warnings").replaceChildren(
      ...data.warnings.map((text) => {
        const p = document.createElement("p");
        I18n.text(p, I18n.server(text));
        return p;
      }),
    );
    I18n.text($("model-name"), data.models.diffusion_models);
  } catch (e) {
    if (rev !== revision) return;
    compiled = null;
    I18n.text($("validation"), e.message);
    $("validation").className = "error";
    I18n.text($("run-summary"), I18n.msg("ui.draft_has_not_passed_validation"));
    $("warnings").replaceChildren();
    $("validate-again").hidden = false;
    if (!e.status || e.status >= 500) {
      clearTimeout(timer);
      timer = setTimeout(
        () => {
          if (rev === revision) validate();
        },
        Math.min(15000, 1500 * 2 ** validationFailures++),
      );
    }
  } finally {
    if (rev === revision) controls();
  }
}
function renderRefs() {
  const box = $("references");
  box.replaceChildren();
  refs.forEach((r, i) => {
    const row = document.createElement("div");
    row.className = "ref";
    const img = document.createElement("img");
    img.src = I18n.plus("/reference/", encodeURIComponent(r.name));
    I18n.text(img, I18n.plus(I18n.msg("ui.reference_image"), I18n.plus(i, 1)), "alt");
    img.onerror = () => {
      I18n.text(text, I18n.msg("ui.image_p0_is_missing_remove_it_and_upload_again", {p0: I18n.plus(i, 1)}));
    };
    const text = document.createElement("span");
    I18n.text(text, I18n.msg("ui.image_p0_p1_625ff", {p0: I18n.plus(i, 1), p1: r.display || r.name.slice(0, 18)}));
    row.append(img, text);
    act(
      "↑",
      () => {
        [refs[i - 1], refs[i]] = [refs[i], refs[i - 1]];
        renderRefs();
        change();
      },
      row,
    ).disabled = i === 0;
    act(
      I18n.msg("ui.remove"),
      () => {
        refs.splice(i, 1);
        renderRefs();
        change();
      },
      row,
    );
    box.append(row);
  });
}
function apply(p, referenceData = []) {
  const v = { ...base, ...p };
  for (const k of fields) $(k).value = v[k];
  refs = referenceData.length
    ? referenceData
    : (v.images || []).map((name) => ({ name }));
  $("upload").value = "";
  const size = I18n.join(["", v.width, ",", v.height, ""]);
  $("size").value = [...$("size").options].some((o) => o.value === size)
    ? size
    : "custom";
  renderRefs();
  change();
}
function downloadJSON(value, name) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function view(which) {
  $("result-view").hidden = which !== "result";
  $("compare-view").hidden = which !== "compare";
  $("view-result").setAttribute("aria-pressed", which === "result");
  $("view-compare").setAttribute("aria-pressed", which === "compare");
}
function parameterText(job) {
  const p = { ...base, ...job.payload };
  return I18n.msg("ui.p0_steps_cfg_p1_p2_p3_seed_p4_p5_cache_p6_p7", {p0: p.steps, p1: p.cfg, p2: p.sampler, p3: p.scheduler, p4: p.seed, p5: I18n.parts(job.actual_size || job.result?.actual_size || [p.width, p.height], " × "), p6: job.workflow?.["2"]?.inputs.dtype || p.cache_dtype, p7: p.prompt});
}
async function selectJob(id, loadParameters = false) {
  const epoch = ++selectionEpoch;
  const job = await api(I18n.plus("/api/jobs/", encodeURIComponent(id)));
  if (epoch !== selectionEpoch) return;
  if (job.status === "done") showResult(job);
  else {
    active = id;
    persist("proActive", id);
    await poll();
  }
  if (loadParameters) apply(job.payload);
}
function showResult(job) {
  selectionEpoch++;
  selected = job;
  persist("proSelected", job.id);
  view("result");
  const img = document.createElement("img");
  img.src = I18n.plus("/output/", encodeURIComponent(job.result.files[0]));
  I18n.text(img, I18n.msg("ui.selected_result"), "alt");
  $("canvas").replaceChildren(img);
  $("result-detail").hidden = false;
  I18n.text($("result-detail"), I18n.plus(I18n.msg("ui.actual_result_parameters_the_right_panel_is_an_independent_draft"), parameterText(job)));
  const a = $("result-actions");
  a.replaceChildren();
  const link = document.createElement("a");
  I18n.text(link, I18n.msg("ui.download_png"));
  link.href = img.src;
  link.download = job.result.files[0];
  a.append(link);
  act(I18n.msg("ui.load_parameters"), () => apply(job.payload), a);
  act(
    I18n.msg("ui.use_this_seed"),
    () => {
      $("seed").value = job.payload.seed;
      change();
    },
    a,
  );
  act(
    I18n.msg("ui.use_as_reference"),
    async () => {
      const blob = await (await fetch(img.src)).blob();
      const r = await upload(blob, "result.png");
      apply({ ...payload(), mode: "edit", images: [r.name] }, [r]);
      message(I18n.msg("ui.loaded_as_image_1_describe_what_to_preserve_and_what_to_change"));
    },
    a,
  );
  act(I18n.msg("ui.set_as_a"), () => setComparison(0, job), a);
  act(I18n.msg("ui.set_as_b"), () => setComparison(1, job), a);
  act(
    I18n.msg("ui.export_task_parameters"),
    () => downloadJSON(job, I18n.plus(I18n.plus("qwen-task-", job.id), ".json")),
    a,
  );
}
function setComparison(slot, job) {
  comparison[slot] = job;
  persist(
    "proComparison",
    comparison.map((j) => j?.id || null),
  );
  renderComparison();
  view("compare");
}
function renderComparison() {
  const box = $("compare-images");
  box.replaceChildren();
  comparison.forEach((job, i) => {
    const figure = document.createElement("figure");
    const caption = document.createElement("figcaption");
    I18n.text(caption, I18n.join(["", i ? "B" : "A", " / ", job ? I18n.plus(I18n.plus(job.payload.steps, I18n.msg("ui.steps_seed")), job.payload.seed) : I18n.msg("ui.select_a_result"), ""]));
    figure.append(caption);
    if (job) {
      const img = document.createElement("img");
      img.src = I18n.plus("/output/", encodeURIComponent(job.result.files[0]));
      I18n.text(img, i ? I18n.msg("ui.result_b") : I18n.msg("ui.result_a"), "alt");
      const viewport = document.createElement("div");
      viewport.className = "compare-viewport";
      viewport.append(img);
      figure.append(viewport);
      viewport.onscroll = () => {
        const other = box.querySelectorAll(".compare-viewport")[1 - i];
        if (!other || viewport.dataset.sync === "1") return;
        other.dataset.sync = "1";
        other.scrollLeft =
          (viewport.scrollLeft /
            Math.max(1, viewport.scrollWidth - viewport.clientWidth)) *
          (other.scrollWidth - other.clientWidth);
        other.scrollTop =
          (viewport.scrollTop /
            Math.max(1, viewport.scrollHeight - viewport.clientHeight)) *
          (other.scrollHeight - other.clientHeight);
        requestAnimationFrame(() => {
          other.dataset.sync = "0";
        });
      };
      img.onload = zoomComparison;
      act(I18n.msg("ui.load_parameters"), () => apply(job.payload), figure, "quiet");
    }
    box.append(figure);
  });
  I18n.text($("compare-count"), I18n.plus(comparison.filter(Boolean).length, "/2"));
  const table = $("compare-table");
  table.replaceChildren();
  const effective = (j, key) => {
    if (!j) return "—";
    const graph = j.workflow || j.result?.workflow || {};
    const node = (id, field) => graph[id]?.inputs?.[field];
    const value =
      {
        cache_dtype: node("2", "dtype"),
        cache_device: node("2", "device"),
        sampler: node("7", "sampler_name"),
        scheduler: node("7", "scheduler"),
        steps: node("7", "steps"),
        seed: node("7", "seed"),
        cfg: node("7", "cfg"),
        tile_size: node("8", "tile_size"),
      }[key] ?? j.payload[key];
    return value === "" ? I18n.msg("ui.empty") : (value == null ? I18n.msg("ui.not_recorded") : String(value));
  };
  const values = [
    [
      I18n.msg("ui.output_size"),
      ...comparison.map((j) =>
        j
          ? I18n.parts(j.actual_size ||
              j.result?.actual_size || [j.payload.width, j.payload.height], " × ")
          : "—",
      ),
    ],
    ...Object.entries({
      mode: I18n.msg("ui.creation_mode"),
      prompt: I18n.msg("ui.prompt"),
      negative_prompt: I18n.msg("ui.negative_prompt"),
      steps: I18n.msg("server.steps"),
      seed: I18n.msg("server.seed"),
      cfg: "CFG",
      sampler: I18n.msg("ui.sampler"),
      scheduler: I18n.msg("ui.scheduler"),
      cache_dtype: I18n.msg("ui.cache_precision_effective"),
      cache_device: I18n.msg("ui.cache_location_effective"),
      tile_size: I18n.msg("ui.vae_tile_size"),
      resolution: I18n.msg("server.reference_size"),
    }).map(([k, label]) => [label, ...comparison.map((j) => effective(j, k))]),
    [
      I18n.msg("ui.references_in_order"),
      ...comparison.map((j) =>
        j
          ? I18n.parts((j.payload.images || [])
              .map((name, i) => I18n.join(["", I18n.plus(i, 1), ". ", name, ""])), "\n") || I18n.msg("ui.none")
          : "—",
      ),
    ],
    ...[
      [I18n.msg("ui.diffusion_model"), "1", "unet_name"],
      [I18n.msg("ui.text_encoder"), "3", "clip_name"],
      ["VAE", "4", "vae_name"],
    ].map(([label, id, key]) => [
      label,
      ...comparison.map((j) =>
        j ? (j.workflow?.[id]?.inputs?.[key] ?? I18n.msg("ui.not_recorded")) : "—",
      ),
    ]),
    [
      I18n.msg("ui.backend_execution_time"),
      ...comparison.map((j) => {
        const t = j?.result?.timings;
        return t?.backend_execution_seconds != null
          ? I18n.msg("ui.p0_s_p1", {p0: t.backend_execution_seconds, p1: t.sampler_cached ? I18n.msg("ui.cache_hit") : ""})
          : I18n.msg("ui.not_recorded");
      }),
    ],
    [
      I18n.msg("ui.total_task_time"),
      ...comparison.map((j) =>
        j?.result?.seconds != null ? I18n.msg("ui.p0_s", {p0: j.result.seconds}) : I18n.msg("ui.not_recorded"),
      ),
    ],
  ];
  values.forEach((row) => {
    const tr = document.createElement("tr");
    if (comparison.every(Boolean) && String(row[1]) !== String(row[2]))
      tr.className = "different";
    row.forEach((value) => {
      const td = document.createElement("td");
      I18n.text(td, value);
      tr.append(td);
    });
    table.append(tr);
  });
}
async function gallery(append = false) {
  if (galleryLoading) {
    if (!append) galleryNeedsRefresh = true;
    return;
  }
  galleryLoading = true;
  try {
    const data = await api(I18n.plus("/api/gallery?offset=", append ? nextPage : 0));
    galleryItems = append ? [...galleryItems, ...data.items] : data.items;
    const box = $("gallery");
    if (!append) box.replaceChildren();
    for (const item of data.items) {
      const b = document.createElement("button");
      const img = document.createElement("img");
      img.src = I18n.plus("/thumb/", encodeURIComponent(item.name));
      I18n.text(img, item.prompt, "alt");
      img.loading = "lazy";
      const caption = document.createElement("small");
      I18n.text(caption, item.prompt);
      b.append(img, caption);
      b.onclick = () =>
        selectJob(item.job_id).catch((e) => message(e.message, true));
      box.append(b);
    }
    nextPage = data.next;
    $("more").hidden = nextPage === null;
  } finally {
    galleryLoading = false;
    if (galleryNeedsRefresh) {
      galleryNeedsRefresh = false;
      gallery().catch(() => {});
    }
  }
}
async function jobs() {
  if (listing) return;
  listing = true;
  try {
    const data = await api("/api/jobs?limit=40&summary=1");
    await refreshBatches().catch(() => {});
    const signature = JSON.stringify(data.items);
    if (signature === jobsSignature) return;
    jobsSignature = signature;
    $("jobs").replaceChildren();
    for (const job of data.items) {
      const row = document.createElement("div");
      row.className = "job";
      const label = document.createElement("span");
      I18n.text(label, job.payload.prompt);
      const meta = document.createElement("small");
      I18n.text(meta, I18n.msg("ui.p0_p1_steps_p2", {p0: names[job.status] || job.status, p1: job.payload.steps, p2: job.batch ? I18n.plus(I18n.plus(I18n.plus(I18n.plus(I18n.plus(" · ", job.batch.index), "/"), job.batch.total), " · "), I18n.server(job.batch.label)) : ""}));
      label.append(meta);
      row.append(label);
      act(
        I18n.msg("ui.view"),
        async () => {
          await selectJob(job.id);
        },
        row,
      );
      if (["failed", "cancelled"].includes(job.status))
        act(
          I18n.msg("ui.load_retry_parameters"),
          () => {
            apply(job.payload);
            $("run-kind").value = "single";
            batchControls();
            message(I18n.msg("ui.original_parameters_and_seed_loaded_run_workflow_will_create_a_ne"));
          },
          row,
        );
      if (!["done", "failed", "cancelled"].includes(job.status))
        act(
          I18n.msg("ui.cancel"),
          async () => {
            await api(I18n.plus(I18n.plus("/api/jobs/", job.id), "/cancel"), {});
            await jobs();
          },
          row,
        );
      if (["timed_out", "lost", "submission_unknown"].includes(job.status))
        act(
          I18n.msg("ui.continue_checking"),
          async () => {
            await api(I18n.plus(I18n.plus("/api/jobs/", job.id), "/resume"), {});
            active = job.id;
            persist("proActive", active);
            await poll();
          },
          row,
        );
      $("jobs").append(row);
    }
  } finally {
    listing = false;
  }
}
async function poll() {
  if (!active || polling) return;
  polling = true;
  const id = active,
    epoch = selectionEpoch;
  try {
    const job = await api(I18n.plus("/api/jobs/", id));
    if (active !== id) return;
    const p = job.progress || {};
    message(
      I18n.msg("ui.p0_p1_p2_p3_this_task_p4_steps_cfg_p5_seed_p6_p7", {p0: names[job.status] || job.status, p1: I18n.server(p.stage) || "", p2: p.max ? I18n.plus(I18n.plus(I18n.plus(" ", p.value), "/"), p.max) : "", p3: job.queue_position ? I18n.plus(I18n.msg("ui.queue_position"), job.queue_position) : "", p4: job.payload.steps, p5: job.payload.cfg || 1, p6: job.payload.seed, p7: I18n.server(job.error) ? I18n.plus("\n", I18n.server(job.error)) : ""}),
    );
    $("progress").hidden = !p.max || terminal.has(job.status);
    if (p.max) {
      $("progress").max = p.max;
      $("progress").value = p.value || 0;
    }
    $("active-actions").replaceChildren();
    if (terminal.has(job.status)) {
      active = null;
      localStorage.removeItem("proActive");
      if (job.status === "done") {
        if (epoch === selectionEpoch) showResult(job);
        await gallery();
      }
      await jobs();
    } else
      act(
        I18n.msg("ui.cancel_this_task"),
        () => api(I18n.plus(I18n.plus("/api/jobs/", id), "/cancel"), {}),
        $("active-actions"),
      );
  } catch (e) {
    if (active !== id) return;
    if (e.status === 404) {
      active = null;
      localStorage.removeItem("proActive");
      message(I18n.msg("ui.original_task_not_found_select_another_task_from_the_queue"), true);
    } else message(I18n.plus(I18n.msg("ui.connection_interrupted_continuing_to_check_the_original_task"), e.message), true);
  } finally {
    polling = false;
  }
}
async function run(retry = false) {
  if (submitting || uploading) return;
  let pending = saved("proPending");
  if (!retry && pending) return;
  if (!pending) {
    if (!$("parameters").reportValidity() || !compiled) return;
    const kind = $("run-kind").value;
    const parameters = payload();
    const batch =
      kind === "single"
        ? null
        : {
            parameters,
            kind,
            ...(kind === "seeds"
              ? { count: Number($("batch-count").value) }
              : { axis: $("batch-axis").value, values: experimentValues() }),
          };
    pending = {
      key: crypto.randomUUID(),
      parameters: batch || parameters,
      endpoint: batch ? "/api/pro/batches" : "/api/generate",
    };
    persist("proPending", pending);
  }
  submitting = true;
  controls();
  try {
    const result = await api(
      pending.endpoint || "/api/generate",
      pending.parameters,
      {
        "Idempotency-Key": pending.key,
      },
    );
    localStorage.removeItem("proPending");
    active = result.job_ids?.[0] || result.id;
    persist("proActive", active);
    message(
      result.job_ids
        ? I18n.msg("ui.submitted_p0_images_the_backend_will_generate_them_sequentially", {p0: result.job_ids.length})
        : I18n.msg("ui.queued_you_can_keep_editing_the_draft"),
    );
    await jobs();
    await poll();
  } catch (e) {
    if (e.status && e.status < 500) localStorage.removeItem("proPending");
    message(
      I18n.plus(e.message, saved("proPending")
          ? I18n.msg("ui.retry_the_same_submission_to_preserve_its_parameters_and_request")
          : ""),
      true,
    );
  } finally {
    submitting = false;
    controls();
  }
}
async function upload(blob, name) {
  const form = new FormData();
  form.append("image", blob, name);
  const response = await fetch("/api/upload", {
    method: "POST",
    body: form,
    signal: AbortSignal.timeout(30000),
  });
  const r = await response.json();
  if (!response.ok) throw I18n.error(r.error || I18n.msg("ui.upload_failed"));
  return r;
}
async function refreshPresets() {
  presets = (await api("/api/pro/presets")).items;
  I18n.text($("preset-count"), presets.length);
  $("presets").replaceChildren();
  if (!presets.length) I18n.text($("presets"), I18n.msg("ui.save_your_first_recipe"));
  for (const item of presets) {
    const row = document.createElement("div");
    act(
      item.name,
      () => {
        apply(item.parameters);
        $("preset-name").value = item.name;
      },
      row,
      "quiet",
    );
    if (item.history?.length) {
      const select = document.createElement("select");
      I18n.attr(select, I18n.plus(item.name, I18n.msg("ui.revision_history")), "aria-label");
      select.append(I18n.option(I18n.msg("ui.history_current_v_p0", {p0: item.revision}), ""));
      [...item.history]
        .reverse()
        .forEach((h) =>
          select.append(I18n.option(I18n.msg("ui.load_v_p0", {p0: h.revision}), String(h.revision))),
        );
      select.onchange = () => {
        const h = item.history.find((h) => String(h.revision) === select.value);
        if (h) {
          apply(h.parameters);
          $("preset-name").value = item.name;
          message(
            I18n.msg("ui.loaded_p0_v_p1_into_the_draft_save_to_create_a_new_revision", {p0: item.name, p1: h.revision}),
          );
        }
      };
      row.append(select);
    }
    $("presets").append(row);
  }
}
$("parameters").onsubmit = (e) => e.preventDefault();
fields.forEach((k) =>
  $(k).addEventListener("input", () => {
    if (k === "width" || k === "height") $("size").value = "custom";
    change();
  }),
);
$("size").onchange = () => {
  if ($("size").value !== "custom") {
    const [w, h] = $("size").value.split(",");
    $("width").value = w;
    $("height").value = h;
    change();
  }
};
$("random").onclick = () => {
  $("seed").value = -1;
  change();
};
$("run").onclick = () => run();
$("retry").onclick = () => run(true);
$("upload").onchange = async () => {
  uploading = true;
  controls();
  try {
    const files = [...$("upload").files];
    if (I18n.plus(files.length, refs.length) > 3)
      throw I18n.error(I18n.msg("ui.up_to_3_references_remove_unused_images_first"));
    for (const file of files) {
      if (file.size > 20 * 1024 ** 2) throw I18n.error(I18n.msg("ui.each_image_must_be_at_most_20mb"));
      refs.push({ ...(await upload(file, file.name)), display: file.name });
    }
    message(I18n.msg("ui.references_uploaded"));
  } catch (e) {
    message(e.message, true);
  } finally {
    uploading = false;
    $("upload").value = "";
    renderRefs();
    change();
  }
};
$("save-preset").onclick = async () => {
  try {
    const item = await api("/api/pro/presets", {
      name: $("preset-name").value,
      parameters: payload(),
    });
    await refreshPresets();
    message(I18n.plus(I18n.msg("ui.preset_saved"), item.name));
  } catch (e) {
    message(e.message, true);
  }
};
$("export").onclick = () =>
  downloadJSON(
    {
      kind: "qwen-studio-workflow",
      version: 1,
      name: $("preset-name").value || I18n.msg("ui.my_recipe"),
      parameters: payload(),
    },
    "qwen-workflow.json",
  );
$("import").onclick = () => $("import-file").click();
$("import-file").onchange = async () => {
  try {
    const file = $("import-file").files[0];
    if (!file) return;
    if (file.size > 1024 * 1024) throw I18n.error(I18n.msg("ui.recipe_files_must_be_at_most_1mb"));
    const data = JSON.parse(await file.text());
    if (
      data.kind !== "qwen-studio-workflow" ||
      data.version !== 1 ||
      !data.parameters
    )
      throw I18n.error(I18n.msg("ui.select_a_v1_recipe_json_exported_by_this_workbench_open_api_node"));
    const recipe = await api("/api/pro/recipe", data.parameters);
    apply(recipe.parameters);
    $("preset-name").value = String(data.name || I18n.msg("ui.import_recipe")).slice(0, 80);
    message(
      recipe.missing_references.length
        ? I18n.msg("ui.parameters_loaded_but_references_are_missing_upload_them_in_the_o")
        : I18n.msg("ui.recipe_imported_into_draft_run_it_when_ready"),
    );
  } catch (e) {
    message(e.message, true);
  } finally {
    $("import-file").value = "";
  }
};
$("inspect").onclick = () => {
  if (!compiled) return message(I18n.msg("ui.fix_the_parameters_and_complete_validation_first"), true);
  I18n.text($("graph-json"), JSON.stringify(compiled.workflow, null, 2));
  $("graph-dialog").showModal();
};
$("close-dialog").onclick = () => $("graph-dialog").close();
$("export-graph").onclick = () =>
  downloadJSON(
    JSON.parse($("graph-json").textContent),
    "qwen-api-workflow.json",
  );
$("view-result").onclick = () => view("result");
$("view-compare").onclick = () => view("compare");
$("refresh").onclick = () =>
  Promise.all([gallery(), jobs()]).catch((e) => message(e.message, true));
$("more").onclick = () => gallery(true).catch((e) => message(e.message, true));
$("flow")
  .querySelectorAll("button")
  .forEach(
    (b) =>
      (b.onclick = () =>
        $(b.dataset.section).scrollIntoView({
          behavior: "smooth",
          block: "start",
        })),
  );
(async () => {
  active = saved("proActive");
  poll();
  setInterval(() => {
    if (!document.hidden) poll();
  }, 1800);
  setInterval(() => {
    if (!document.hidden) jobs().catch(() => {});
  }, 6500);
  setInterval(() => {
    if (!document.hidden) health();
  }, 15000);
  try {
    const config = await api("/api/config").catch(() => ({
      examples: { photo: "一只猫坐在窗边，柔和自然光，真实摄影" },
      generation: {},
      queue_limit: 5,
    }));
    Object.assign(base, config.pro?.defaults || {});
    base.steps = config.generation?.standard_steps || base.steps;
    for (const [key, values] of Object.entries(config.pro?.options || {})) {
      const select = $(key);
      const labels = new Map(
        [...select.options].map((o) => [o.value, o.dataset.i18n ? I18n.msg(o.dataset.i18n) : o.textContent]),
      );
      select.replaceChildren(
        ...values.map(
          (v) => I18n.option(labels.get(String(v)) || String(v), String(v)),
        ),
      );
    }
    if (config.generation?.reference_resolutions) {
      $("resolution").replaceChildren(
        ...config.generation.reference_resolutions.map(
          (v) => I18n.option(String(v), String(v)),
        ),
      );
    }
    for (const id of ["width", "height"])
      $(id).max = config.generation?.max_side || 1536;
    queueLimit = config.queue_limit || 5;
    $("batch-count").max = queueLimit;
    batchControls();
    I18n.text($("connection"), config.backend_ready
      ? I18n.msg("ui.model_connected")
      : I18n.msg("ui.model_disconnected"));
    const recipes = [
      [I18n.msg("ui.standard_photography"), I18n.msg("ui.1024_40_steps_quality_baseline"), { prompt: config.examples.photo }],
      [
        I18n.msg("ui.quick_exploration"),
        I18n.msg("ui.768_20_steps_composition_preview"),
        { prompt: config.examples.photo, steps: 20, width: 768, height: 768 },
      ],
      [
        I18n.msg("ui.chinese_poster"),
        I18n.msg("ui.portrait_40_steps_check_typography"),
        { prompt: config.examples.poster, width: 832, height: 1216 },
      ],
      [
        I18n.msg("ui.reference_editing"),
        I18n.msg("ui.768_reference_int8_cache"),
        { prompt: config.examples.edit, mode: "edit" },
      ],
    ];
    for (const [label, description, p] of recipes) {
      const b = act(
        "",
        () => {
          apply({ ...base, ...p });
          $("builtins")
            .querySelectorAll("button")
            .forEach((n) => n.classList.toggle("selected", n === b));
        },
        $("builtins"),
        "recipe",
      );
      const title = document.createElement("strong");
      I18n.text(title, label);
      const desc = document.createElement("small");
      I18n.text(desc, description);
      b.append(title, desc);
    }
    const draft = saved("proDraft");
    apply(
      draft?.parameters || { ...base, prompt: config.examples.photo },
      draft?.references || [],
    );
    const restored = await Promise.allSettled([
      gallery(),
      jobs(),
      refreshPresets(),
    ]);
    if (restored.some((r) => r.status === "rejected"))
      message(I18n.msg("ui.some_lists_are_unavailable_task_tracking_continues_use_refresh_to"), true);
    const query = new URLSearchParams(location.search).get("job");
    const selectedId = query || saved("proSelected");
    if (selectedId)
      await selectJob(selectedId, Boolean(query)).catch((e) => {
        if (e.status === 404) localStorage.removeItem("proSelected");
      });
    const ids = saved("proComparison") || [];
    comparison = await Promise.all(
      [0, 1].map((i) =>
        ids[i]
          ? api(I18n.plus("/api/jobs/", encodeURIComponent(ids[i])))
              .then((j) => (j.status === "done" ? j : null))
              .catch(() => null)
          : null,
      ),
    );
    renderComparison();
    await poll();
    controls();
  } catch (e) {
    message(e.message, true);
  } finally {
    controls();
  }
})();

function experimentValues() {
  const numeric = ["steps", "cfg", "tile_size"].includes($("batch-axis").value);
  return $("batch-values")
    .value.split(/[,，]/)
    .map((v) => (numeric ? (v.trim() ? Number(v.trim()) : null) : v.trim()));
}
function batchControls() {
  const kind = $("run-kind").value;
  $("batch-options").hidden = kind === "single";
  $("batch-count-box").hidden = kind !== "seeds";
  $("batch-count").disabled = kind !== "seeds";
  $("experiment-options").hidden = kind !== "experiment";
  I18n.text($("batch-hint"), kind === "experiment"
      ? I18n.msg("ui.keep_the_same_seed_prompt_and_references_vary_only_the_selected_p", {p0: queueLimit})
      : I18n.msg("ui.seeds_increase_by_1_per_image_1_picks_a_random_starting_point_gen", {p0: queueLimit}));
  I18n.text($("run"), kind === "single"
      ? I18n.msg("ui.run_workflow")
      : kind === "seeds"
        ? I18n.msg("ui.submit_batch_sequential")
        : I18n.msg("ui.submit_parameter_experiment"));
  persist("proBatchDraft", {
    kind,
    count: $("batch-count").value,
    axis: $("batch-axis").value,
    values: $("batch-values").value,
  });
}
async function refreshBatches() {
  const data = await api("/api/pro/batches");
  const signature = JSON.stringify(data.items);
  if (signature === batchesSignature) return;
  const openStates = new Map(
    [...$("batches").children].map((card) => [card.dataset.batchId, card.open]),
  );
  batchesSignature = signature;
  $("batches").replaceChildren();
  for (const batch of data.items) {
    const done = batch.jobs.filter((j) => j.status === "done").length;
    const ended = batch.jobs.filter((j) =>
      ["done", "failed", "cancelled"].includes(j.status),
    ).length;
    const uncertain = batch.jobs.some((j) =>
      ["timed_out", "lost", "submission_unknown"].includes(j.status),
    );
    const card = document.createElement("details");
    card.className = "batch-card";
    card.dataset.batchId = batch.id;
    card.open = openStates.get(batch.id) ?? ended < batch.jobs.length;
    const title = document.createElement("summary");
    I18n.text(title, I18n.msg("ui.p0_done_p1_p2_p3_p4", {p0: batch.kind === "experiment" ? I18n.msg("ui.parameter_experiment") : I18n.msg("ui.seed_sequence"), p1: done, p2: batch.jobs.length, p3: uncertain ? I18n.msg("ui.needs_review") : ended === batch.jobs.length ? I18n.msg("ui.finished") : I18n.msg("ui.in_progress"), p4: new Date(batch.created * 1000).toLocaleTimeString()}));
    card.append(title);
    for (const job of batch.jobs) {
      const row = document.createElement("div");
      row.className = "batch-member";
      const label = document.createElement("span");
      I18n.text(label, I18n.join(["", job.batch.index, ". ", I18n.server(job.batch.label), " · ", names[job.status], "", I18n.server(job.error) ? I18n.plus(" · ", I18n.server(job.error)) : "", ""]));
      row.append(label);
      act(I18n.msg("ui.view"), () => selectJob(job.id), row, "quiet");
      if (job.status === "done") {
        for (const [slot, name] of [
          [0, "A"],
          [1, "B"],
        ])
          act(
            name,
            async () => setComparison(slot, await api(I18n.plus("/api/jobs/", job.id))),
            row,
            "quiet",
          );
      }
      card.append(row);
    }
    if (ended < batch.jobs.length)
      act(
        I18n.msg("ui.cancel_unfinished_tasks_in_batch"),
        async () => {
          await api(I18n.join(["/api/pro/batches/", batch.id, "/cancel"]), {});
          await refreshBatches();
          await jobs();
        },
        card,
        "quiet",
      );
    act(
      I18n.msg("ui.export_batch_records"),
      async () =>
        downloadJSON(
          {
            ...batch,
            jobs: await Promise.all(
              batch.job_ids.map((id) => api(I18n.plus("/api/jobs/", id))),
            ),
          },
          I18n.join(["qwen-batch-", batch.id, ".json"]),
        ),
      card,
      "quiet",
    );
    $("batches").append(card);
  }
  const completed = JSON.stringify(
    data.items.flatMap((b) =>
      b.jobs.filter((j) => j.status === "done").map((j) => j.id),
    ),
  );
  if (completedBatchSignature && completed !== completedBatchSignature)
    gallery().catch(() => {});
  completedBatchSignature = completed;
}
async function health() {
  if (healthLoading) return;
  healthLoading = true;
  try {
    const config = await api("/api/config");
    I18n.text($("connection"), config.backend_ready
      ? I18n.msg("ui.model_connected")
      : I18n.msg("ui.model_disconnected"));
  } catch {
    I18n.text($("connection"), I18n.msg("ui.connection_interrupted"));
  } finally {
    healthLoading = false;
  }
}
function zoomComparison() {
  const zoom = $("compare-zoom").value;
  document.querySelectorAll(".compare-viewport img").forEach((img) => {
    img.style.width =
      zoom === "fit" ? "100%" : I18n.join(["", img.naturalWidth * Number(zoom), "px"]);
    img.style.height = zoom === "fit" ? "280px" : "auto";
    img.style.maxWidth = "none";
  });
}
$("compare-zoom").onchange = zoomComparison;
$("validate-again").onclick = () => {
  clearTimeout(timer);
  validate();
};
const batchDraft = saved("proBatchDraft");
if (batchDraft) {
  $("run-kind").value = batchDraft.kind;
  $("batch-count").value = batchDraft.count;
  $("batch-axis").value = batchDraft.axis;
  $("batch-values").value = batchDraft.values;
}
["run-kind", "batch-count", "batch-values"].forEach((id) =>
  $(id).addEventListener("input", batchControls),
);
$("batch-axis").onchange = () => {
  $("batch-values").value = {
    steps: "20, 30, 40",
    cfg: "1, 1.2, 1.5",
    sampler: "euler, heun, dpmpp_2m",
    scheduler: "simple, normal, beta",
    cache_dtype: "default, int8, int4",
    tile_size: "256, 512, 768",
  }[$("batch-axis").value];
  batchControls();
};
batchControls();
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    poll();
    jobs().catch(() => {});
    health();
  }
});

function scrollBatch() {
  const form = $("parameters"), section = $("batch-section");
  if (form.scrollHeight > I18n.plus(form.clientHeight, 1)) {
    form.scrollTo({top:I18n.plus(form.scrollTop, section.getBoundingClientRect().top) - form.getBoundingClientRect().top,behavior:"smooth"});
  } else section.scrollIntoView({behavior:"smooth",block:"start"});
}
$("run-kind").addEventListener("change",scrollBatch);
$("batch-shortcut").onclick = () => {
  scrollBatch();
  $("run-kind").focus({preventScroll:true});
};
