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
  queued: "等待提交",
  submitting: "提交中",
  backend_queued: "后端排队",
  running: "生成中",
  reconnecting: "重新连接",
  downloading: "保存图片",
  done: "完成",
  failed: "失败",
  cancelled: "已取消",
  cancelling: "取消中",
  timed_out: "超时",
  lost: "记录缺失",
  submission_unknown: "提交待核对",
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
  $("message").textContent = text;
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
    const e = new Error(`服务响应异常 (${response.status})`);
    e.status = response.status;
    throw e;
  }
  if (!response.ok) {
    const e = new Error(result.error || `请求失败 (${response.status})`);
    e.status = response.status;
    throw e;
  }
  return result;
}
function act(label, fn, parent, cls = "") {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
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
  $("draft-status").textContent = "草稿已保存";
  $("reference-box").hidden = $("mode").value === "text";
  $("canvas-size").hidden =
    $("mode").value === "edit" ||
    ($("mode").value === "transparent" && refs.length > 0);
  $("validation").textContent = "校验当前草稿…";
  $("run-summary").textContent = "等待当前参数校验…";
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
    $("flow-input").textContent = {
      text: "文字生成",
      edit: `${refs.length}张参考图`,
      transparent: "RGBA 透明素材",
    }[data.payload.mode];
    $("flow-sample").textContent =
      `${data.payload.sampler || "euler"} · ${data.payload.steps} 步`;
    $("flow-output").textContent = data.actual_size.join(" × ");
    $("run-summary").textContent =
      `${data.payload.steps}步 · CFG ${data.payload.cfg || 1} · ${data.actual_size.join(" × ")}`;
    $("validation").textContent =
      `✓ 参数已校验 · ${Object.keys(data.workflow).length}个节点 · 缓存 ${data.workflow["2"].inputs.dtype}`;
    $("validation").className = "muted";
    $("warnings").replaceChildren(
      ...data.warnings.map((text) => {
        const p = document.createElement("p");
        p.textContent = text;
        return p;
      }),
    );
    $("model-name").textContent = data.models.diffusion_models;
  } catch (e) {
    if (rev !== revision) return;
    compiled = null;
    $("validation").textContent = e.message;
    $("validation").className = "error";
    $("run-summary").textContent = "当前草稿尚未通过校验";
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
    img.src = "/reference/" + encodeURIComponent(r.name);
    img.alt = "参考图" + (i + 1);
    img.onerror = () => {
      text.textContent = `图${i + 1}缺失：请移除后重新上传`;
    };
    const text = document.createElement("span");
    text.textContent = `图${i + 1} · ${r.display || r.name.slice(0, 18)}`;
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
      "移除",
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
  const size = `${v.width},${v.height}`;
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
  return `${p.steps}步 · CFG ${p.cfg} · ${p.sampler}/${p.scheduler} · 种子 ${p.seed}\n${(job.actual_size || job.result?.actual_size || [p.width, p.height]).join(" × ")} · 缓存 ${job.workflow?.["2"]?.inputs.dtype || p.cache_dtype}\n${p.prompt}`;
}
async function selectJob(id, loadParameters = false) {
  const epoch = ++selectionEpoch;
  const job = await api("/api/jobs/" + encodeURIComponent(id));
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
  img.src = "/output/" + encodeURIComponent(job.result.files[0]);
  img.alt = "所选作品";
  $("canvas").replaceChildren(img);
  $("result-detail").hidden = false;
  $("result-detail").textContent =
    "所选作品实际参数（右侧为独立草稿）\n" + parameterText(job);
  const a = $("result-actions");
  a.replaceChildren();
  const link = document.createElement("a");
  link.textContent = "下载 PNG";
  link.href = img.src;
  link.download = job.result.files[0];
  a.append(link);
  act("载入参数", () => apply(job.payload), a);
  act(
    "固定此种子",
    () => {
      $("seed").value = job.payload.seed;
      change();
    },
    a,
  );
  act(
    "作为参考图",
    async () => {
      const blob = await (await fetch(img.src)).blob();
      const r = await upload(blob, "result.png");
      apply({ ...payload(), mode: "edit", images: [r.name] }, [r]);
      message("已载入为图1，请描述要保留和改变的内容。");
    },
    a,
  );
  act("设为 A", () => setComparison(0, job), a);
  act("设为 B", () => setComparison(1, job), a);
  act(
    "导出任务参数",
    () => downloadJSON(job, "qwen-task-" + job.id + ".json"),
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
    caption.textContent = `${i ? "B" : "A"} / ${job ? job.payload.steps + "步 · 种子 " + job.payload.seed : "从作品中选择"}`;
    figure.append(caption);
    if (job) {
      const img = document.createElement("img");
      img.src = "/output/" + encodeURIComponent(job.result.files[0]);
      img.alt = i ? "作品B" : "作品A";
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
      act("载入参数", () => apply(job.payload), figure, "quiet");
    }
    box.append(figure);
  });
  $("compare-count").textContent = comparison.filter(Boolean).length + "/2";
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
    return value === "" ? "空" : String(value ?? "未记录");
  };
  const values = [
    [
      "输出尺寸",
      ...comparison.map((j) =>
        j
          ? (
              j.actual_size ||
              j.result?.actual_size || [j.payload.width, j.payload.height]
            ).join(" × ")
          : "—",
      ),
    ],
    ...Object.entries({
      mode: "创作模式",
      prompt: "提示词",
      negative_prompt: "负面提示词",
      steps: "步数",
      seed: "种子",
      cfg: "CFG",
      sampler: "采样器",
      scheduler: "调度器",
      cache_dtype: "缓存精度（实际）",
      cache_device: "缓存位置（实际）",
      tile_size: "VAE分块",
      resolution: "参考大小",
    }).map(([k, label]) => [label, ...comparison.map((j) => effective(j, k))]),
    [
      "参考图片（按顺序）",
      ...comparison.map((j) =>
        j
          ? (j.payload.images || [])
              .map((name, i) => `${i + 1}. ${name}`)
              .join("\n") || "无"
          : "—",
      ),
    ],
    ...[
      ["生成模型", "1", "unet_name"],
      ["文本编码器", "3", "clip_name"],
      ["VAE", "4", "vae_name"],
    ].map(([label, id, key]) => [
      label,
      ...comparison.map((j) =>
        j ? (j.workflow?.[id]?.inputs?.[key] ?? "未记录") : "—",
      ),
    ]),
    [
      "后端执行时间",
      ...comparison.map((j) => {
        const t = j?.result?.timings;
        return t?.backend_execution_seconds != null
          ? `${t.backend_execution_seconds}秒${t.sampler_cached ? "（缓存命中）" : ""}`
          : "未记录";
      }),
    ],
    [
      "任务总耗时",
      ...comparison.map((j) =>
        j?.result?.seconds != null ? `${j.result.seconds}秒` : "未记录",
      ),
    ],
  ];
  values.forEach((row) => {
    const tr = document.createElement("tr");
    if (comparison.every(Boolean) && row[1] !== row[2])
      tr.className = "different";
    row.forEach((value) => {
      const td = document.createElement("td");
      td.textContent = value;
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
    const data = await api("/api/gallery?offset=" + (append ? nextPage : 0));
    galleryItems = append ? [...galleryItems, ...data.items] : data.items;
    const box = $("gallery");
    if (!append) box.replaceChildren();
    for (const item of data.items) {
      const b = document.createElement("button");
      const img = document.createElement("img");
      img.src = "/thumb/" + encodeURIComponent(item.name);
      img.alt = item.prompt;
      img.loading = "lazy";
      const caption = document.createElement("small");
      caption.textContent = item.prompt;
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
      label.textContent = job.payload.prompt;
      const meta = document.createElement("small");
      meta.textContent = `${names[job.status] || job.status} · ${job.payload.steps}步${job.batch ? " · " + job.batch.index + "/" + job.batch.total + " · " + job.batch.label : ""}`;
      label.append(meta);
      row.append(label);
      act(
        "查看",
        async () => {
          await selectJob(job.id);
        },
        row,
      );
      if (["failed", "cancelled"].includes(job.status))
        act(
          "载入重试参数",
          () => {
            apply(job.payload);
            $("run-kind").value = "single";
            batchControls();
            message("已载入原参数和种子。点击运行工作流会创建一次新的生成。");
          },
          row,
        );
      if (!["done", "failed", "cancelled"].includes(job.status))
        act(
          "取消",
          async () => {
            await api("/api/jobs/" + job.id + "/cancel", {});
            await jobs();
          },
          row,
        );
      if (["timed_out", "lost", "submission_unknown"].includes(job.status))
        act(
          "继续核对",
          async () => {
            await api("/api/jobs/" + job.id + "/resume", {});
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
    const job = await api("/api/jobs/" + id);
    if (active !== id) return;
    const p = job.progress || {};
    message(
      `${names[job.status] || job.status} · ${p.stage || ""}${p.max ? " " + p.value + "/" + p.max : ""}${job.queue_position ? " · 队列位置 " + job.queue_position : ""}\n本次：${job.payload.steps}步 / CFG ${job.payload.cfg || 1} / 种子 ${job.payload.seed}${job.error ? "\n" + job.error : ""}`,
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
        "取消此任务",
        () => api("/api/jobs/" + id + "/cancel", {}),
        $("active-actions"),
      );
  } catch (e) {
    if (active !== id) return;
    if (e.status === 404) {
      active = null;
      localStorage.removeItem("proActive");
      message("原任务记录不存在；请从任务队列选择其他任务。", true);
    } else message("连接暂时中断，将继续核对原任务。\n" + e.message, true);
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
        ? `已提交整组 ${result.job_ids.length} 张，后台依次生成。`
        : "已加入队列；右侧草稿可继续编辑。",
    );
    await jobs();
    await poll();
  } catch (e) {
    if (e.status && e.status < 500) localStorage.removeItem("proPending");
    message(
      e.message +
        (saved("proPending")
          ? "\n请重试同一次提交，将保留原参数和请求ID。"
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
  if (!response.ok) throw new Error(r.error || "上传失败");
  return r;
}
async function refreshPresets() {
  presets = (await api("/api/pro/presets")).items;
  $("preset-count").textContent = presets.length;
  $("presets").replaceChildren();
  if (!presets.length) $("presets").textContent = "保存你的第一个创作配方";
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
      select.setAttribute("aria-label", item.name + "的历史版本");
      select.append(new Option(`历史版本 · 当前 v${item.revision}`, ""));
      [...item.history]
        .reverse()
        .forEach((h) =>
          select.append(new Option(`载入 v${h.revision}`, String(h.revision))),
        );
      select.onchange = () => {
        const h = item.history.find((h) => String(h.revision) === select.value);
        if (h) {
          apply(h.parameters);
          $("preset-name").value = item.name;
          message(
            `已载入 ${item.name} v${h.revision} 到草稿。保存后成为新版本。`,
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
    if (files.length + refs.length > 3)
      throw new Error("最多3张参考图，请先移除不需要的图片");
    for (const file of files) {
      if (file.size > 20 * 1024 ** 2) throw new Error("单张图片不能超过20MB");
      refs.push({ ...(await upload(file, file.name)), display: file.name });
    }
    message("参考图上传完成");
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
    message("已保存预设：" + item.name);
  } catch (e) {
    message(e.message, true);
  }
};
$("export").onclick = () =>
  downloadJSON(
    {
      kind: "qwen-studio-workflow",
      version: 1,
      name: $("preset-name").value || "我的配方",
      parameters: payload(),
    },
    "qwen-workflow.json",
  );
$("import").onclick = () => $("import-file").click();
$("import-file").onchange = async () => {
  try {
    const file = $("import-file").files[0];
    if (!file) return;
    if (file.size > 1024 * 1024) throw new Error("配方文件不能超过1MB");
    const data = JSON.parse(await file.text());
    if (
      data.kind !== "qwen-studio-workflow" ||
      data.version !== 1 ||
      !data.parameters
    )
      throw new Error(
        "请选择从专业工作台导出的v1配方JSON；API节点图请在ComfyUI中使用",
      );
    const recipe = await api("/api/pro/recipe", data.parameters);
    apply(recipe.parameters);
    $("preset-name").value = String(data.name || "导入配方").slice(0, 80);
    message(
      recipe.missing_references.length
        ? "配方参数已载入。参考图缺失，请在输入区按原顺序重新上传；补齐前无法生成。"
        : "配方已导入草稿；点击运行才会生成。",
    );
  } catch (e) {
    message(e.message, true);
  } finally {
    $("import-file").value = "";
  }
};
$("inspect").onclick = () => {
  if (!compiled) return message("请先修正参数，完成校验。", true);
  $("graph-json").textContent = JSON.stringify(compiled.workflow, null, 2);
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
        [...select.options].map((o) => [o.value, o.textContent]),
      );
      select.replaceChildren(
        ...values.map(
          (v) => new Option(labels.get(String(v)) || String(v), String(v)),
        ),
      );
    }
    if (config.generation?.reference_resolutions) {
      $("resolution").replaceChildren(
        ...config.generation.reference_resolutions.map(
          (v) => new Option(String(v), String(v)),
        ),
      );
    }
    for (const id of ["width", "height"])
      $(id).max = config.generation?.max_side || 1536;
    queueLimit = config.queue_limit || 5;
    $("batch-count").max = queueLimit;
    batchControls();
    $("connection").textContent = config.backend_ready
      ? "● 模型已连接"
      : "○ 模型未连接";
    const recipes = [
      ["标准摄影", "1024 / 40步 · 质量起点", { prompt: config.examples.photo }],
      [
        "快速探索",
        "768 / 20步 · 构图预览",
        { prompt: config.examples.photo, steps: 20, width: 768, height: 768 },
      ],
      [
        "中文海报",
        "竖幅 / 40步 · 检查文字",
        { prompt: config.examples.poster, width: 832, height: 1216 },
      ],
      [
        "参考图编辑",
        "768参考 / INT8缓存",
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
      title.textContent = label;
      const desc = document.createElement("small");
      desc.textContent = description;
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
      message("部分列表暂不可用，任务跟踪仍在运行。可点击刷新重试。", true);
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
          ? api("/api/jobs/" + encodeURIComponent(ids[i]))
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
  $("batch-hint").textContent =
    kind === "experiment"
      ? `保持同一种子、提示词和参考图，只改变所选参数。种子为 -1 时整组共用一次随机值；支持 2–${queueLimit} 个不同值。`
      : `每张种子依次加 1；-1 时随机起点。每批 2–${queueLimit} 张，适合挑选构图。`;
  $("run").textContent =
    kind === "single"
      ? "运行工作流 ↗"
      : kind === "seeds"
        ? "提交整组 · 依次生成 ↗"
        : "提交单变量实验 ↗";
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
    title.textContent = `${batch.kind === "experiment" ? "对比实验" : "连续出图"} · 完成 ${done}/${batch.jobs.length} · ${uncertain ? "需核对" : ended === batch.jobs.length ? "已结束" : "进行中"} · ${new Date(batch.created * 1000).toLocaleTimeString()}`;
    card.append(title);
    for (const job of batch.jobs) {
      const row = document.createElement("div");
      row.className = "batch-member";
      const label = document.createElement("span");
      label.textContent = `${job.batch.index}. ${job.batch.label} · ${names[job.status]}${job.error ? " · " + job.error : ""}`;
      row.append(label);
      act("查看", () => selectJob(job.id), row, "quiet");
      if (job.status === "done") {
        for (const [slot, name] of [
          [0, "A"],
          [1, "B"],
        ])
          act(
            name,
            async () => setComparison(slot, await api("/api/jobs/" + job.id)),
            row,
            "quiet",
          );
      }
      card.append(row);
    }
    if (ended < batch.jobs.length)
      act(
        "取消本批未完成任务",
        async () => {
          await api(`/api/pro/batches/${batch.id}/cancel`, {});
          await refreshBatches();
          await jobs();
        },
        card,
        "quiet",
      );
    act(
      "导出整组记录",
      async () =>
        downloadJSON(
          {
            ...batch,
            jobs: await Promise.all(
              batch.job_ids.map((id) => api("/api/jobs/" + id)),
            ),
          },
          `qwen-batch-${batch.id}.json`,
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
    $("connection").textContent = config.backend_ready
      ? "● 模型已连接"
      : "○ 模型未连接";
  } catch {
    $("connection").textContent = "○ 连接中断";
  } finally {
    healthLoading = false;
  }
}
function zoomComparison() {
  const zoom = $("compare-zoom").value;
  document.querySelectorAll(".compare-viewport img").forEach((img) => {
    img.style.width =
      zoom === "fit" ? "100%" : `${img.naturalWidth * Number(zoom)}px`;
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
  if (form.scrollHeight > form.clientHeight + 1) {
    form.scrollTo({top:form.scrollTop + section.getBoundingClientRect().top - form.getBoundingClientRect().top,behavior:"smooth"});
  } else section.scrollIntoView({behavior:"smooth",block:"start"});
}
$("run-kind").addEventListener("change",scrollBatch);
$("batch-shortcut").onclick = () => {
  scrollBatch();
  $("run-kind").focus({preventScroll:true});
};
