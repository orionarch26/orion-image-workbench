'use strict';
const $ = id => document.getElementById(id);
const terminal = new Set(['done', 'failed', 'cancelled', 'timed_out', 'submission_unknown', 'lost']);
const statusNames = {queued:I18n.msg("ui.waiting_to_submit"),submitting:I18n.msg("ui.submitting"),backend_queued:I18n.msg("ui.queued_in_backend"),running:I18n.msg("ui.generating"),reconnecting:I18n.msg("ui.reconnecting"),downloading:I18n.msg("ui.downloading_and_verifying"),cancelling:I18n.msg("ui.cancelling"),cancelled:I18n.msg("ui.cancelled"),done:I18n.msg("ui.done"),failed:I18n.msg("ui.failed"),timed_out:I18n.msg("ui.timed_out"),submission_unknown:I18n.msg("ui.submission_needs_review"),lost:I18n.msg("ui.backend_record_missing")};
let examples = {}, generation = {}, references = [], busy = false, selectedJob = null;
let activeId = null, watching = 0, nextPage = null;

function readSaved(key) {
  try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
}
function setBusy(value) {
  busy = value;
  $('generate').disabled = value || Boolean(readSaved('studioPending'));
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(20000)});
  const data = await response.json();
  if (!response.ok) {
    const error = I18n.error(data.error || I18n.msg("ui.request_failed_p0", {p0: response.status}));
    error.status = response.status;
    throw error;
  }
  return data;
}
function post(path, data = {}, headers = {}) {
  return api(path, {method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(data)});
}
function message(text, error = false) {
  I18n.text($('status'), text);
  $('status').className = error ? 'error' : '';
}
function draft() {
  const [width,height] = $('size').value.split(',').map(Number);
  return {prompt:$('prompt').value,mode:$('mode').value,preset:$('preset').value,
    width,height,seed:Number($('seed').value),resolution:Number($('resolution').value),
    images:$('mode').value === 'text' ? [] : references.map(ref => ref.name)};
}
function saveDraft() {
  localStorage.setItem('studioDraft',JSON.stringify({payload:draft(),references}));
}
function applyDraft(payload, refs = []) {
  $('prompt').value = payload.prompt || '';
  $('mode').value = payload.mode || 'text';
  $('preset').value = payload.preset || 'standard';
  $('seed').value = payload.seed ?? -1;
  $('resolution').value = payload.resolution || 768;
  const size = I18n.join(["", payload.width || 1024, ",", payload.height || 1024, ""]);
  if (![...$('size').options].some(option => option.value === size)) {
    $('size').add(I18n.option(size.replace(',', ' × '), size));
  }
  $('size').value = size;
  references = refs.length ? refs : (payload.images || []).map(name => ({name}));
  $('images').value = '';
  modeChanged();
}
function modeChanged() {
  $('uploadbox').hidden = $('mode').value === 'text';
  $('sizebox').hidden = $('mode').value === 'edit' || ($('mode').value === 'transparent' && references.length > 0);
  I18n.text($('refs'), I18n.parts(references.map((ref,index) => I18n.msg("ui.image_p0_p1", {p0: I18n.plus(index, 1), p1: ref.display || ref.name})), ' / '));
  I18n.text($('refsize'), '');
  if ($('mode').value !== 'text' && references.length) {
    post('/api/validate', {...draft(),prompt:$('prompt').value || '尺寸预检'}).then(result => {
      I18n.text($('refsize'), I18n.msg("ui.expected_output_p0_image_1_aspect_ratio", {p0: I18n.parts(result.actual_size, ' × ')}));
    }).catch(error => { I18n.text($('refsize'), error.message); });
  }
}
function showImage(name) {
  const image = document.createElement('img');
  image.src = I18n.plus('/output/', encodeURIComponent(name));
  I18n.text(image, I18n.msg("ui.generated_image"), "alt");
  $('preview').replaceChildren(image);
}
function button(label, action, parent = $('actions')) {
  const node = document.createElement('button');
  node.className = 'secondary'; I18n.text(node, label);
  node.onclick = () => Promise.resolve(action()).catch(error => message(error.message,true));
  parent.append(node);
  return node;
}
function showSnapshot(job) {
  const p = job.payload;
  if (!p) return;
  const mode = {text:I18n.msg("ui.text_to_image"),edit:I18n.msg("ui.reference_editing"),transparent:I18n.msg("ui.transparent_asset")}[p.mode];
  const size = job.actual_size || job.result?.actual_size || [p.width,p.height];
  $('snapshot').hidden = false;
  I18n.text($('snapshot'), I18n.msg("ui.selected_result_task_parameters_the_left_panel_is_an_independent", {p0: mode, p1: I18n.parts(size, ' × '), p2: p.steps, p3: p.seed, p4: p.prompt}));
}
function showResult(job) {
  selectedJob = job;
  const result = job.result;
  showImage(result.files[0]); showSnapshot(job);
  $('progress').hidden = true;
  message(I18n.msg("ui.complete_p0_s_image_and_parameters_saved_p1", {p0: result.seconds, p1: result.timings?.sampler_cached ? I18n.msg("ui.backend_cache_was_reused_this_is_not_a_new_generation_speed_measu") : ''}));
  if (I18n.server(job.metadata_error)) message(I18n.plus(I18n.msg("ui.image_complete_parameter_file_could_not_be_saved_yet_the_task_is"), I18n.server(job.metadata_error)),true);
  $('actions').replaceChildren();
  for (const [label,name] of [[I18n.msg("ui.download_png"),result.files[0]],[I18n.msg("ui.download_parameters"),I18n.plus(result.prompt_id, '.json')]]) {
    const a = document.createElement('a');
    a.className = 'download'; I18n.text(a, label);
    a.href = I18n.plus('/output/', encodeURIComponent(name)); a.download = name;
    $('actions').append(a);
  }
  const professional = document.createElement('a');
  professional.className='download'; I18n.text(professional, I18n.msg("ui.open_in_workbench"));
  professional.href=I18n.plus('/pro?job=', encodeURIComponent(job.id)); $('actions').append(professional);
  button(I18n.msg("ui.load_result_into_draft"), () => { applyDraft(job.payload); saveDraft(); });
  if (job.payload) {
    const target = {...job.payload,preset:'standard',steps:generation.standard_steps};
    button(I18n.msg("ui.generate_standard_quality_with_these_parameters"), () => generate(target));
  }
}
async function refreshGallery(append = false) {
  const data = await api(I18n.plus('/api/gallery?offset=', append ? nextPage : 0));
  if (!append) $('gallery').replaceChildren();
  for (const item of data.items) {
    const b = document.createElement('button');
    const image = document.createElement('img');
    image.src = I18n.plus('/thumb/', encodeURIComponent(item.name)); image.loading = 'lazy'; I18n.text(image, item.prompt, "alt");
    const caption = document.createElement('span'); I18n.text(caption, item.prompt);
    b.append(image,caption);
    b.onclick = async () => {
      if (busy) return message(I18n.msg("ui.wait_for_the_tracked_task_to_finish_or_use_the_task_list"));
      try { showResult(await api(I18n.plus('/api/jobs/', item.job_id))); }
      catch (error) { message(error.message,true); }
    };
    $('gallery').append(b);
  }
  nextPage = data.next;
  $('more').hidden = nextPage === null;
}
async function refreshTasks() {
  const data = await api('/api/jobs?limit=20');
  $('tasks').replaceChildren();
  if (!data.items.length) I18n.text($('tasks'), I18n.msg("ui.no_tasks_yet"));
  for (const job of data.items) {
    const row = document.createElement('div'); row.className = 'task';
    const label = document.createElement('span');
    I18n.text(label, (job.payload.prompt || '').slice(0,55));
    const meta = document.createElement('small');
    I18n.text(meta, I18n.join(["", statusNames[job.status] || job.status, " · ", new Date(job.created*1000).toLocaleTimeString(I18n.locale), ""]));
    label.append(meta); row.append(label);
    button(I18n.msg("ui.view"), async () => {
      if (job.status === 'done') {
        if (!busy) showResult(await api(I18n.plus('/api/jobs/', job.id)));
      } else {
        localStorage.setItem('studioJob',job.id);
        watch(job.id);
      }
    },row);
    if (!['done','failed','cancelled'].includes(job.status)) {
      button(I18n.msg("ui.cancel"), async () => { await post(I18n.plus(I18n.plus('/api/jobs/', job.id), '/cancel')); await refreshTasks(); },row);
    }
    if (['timed_out','submission_unknown','lost'].includes(job.status)) {
      button(I18n.msg("ui.continue_checking"), async () => { await post(I18n.plus(I18n.plus('/api/jobs/', job.id), '/resume')); watch(job.id); },row);
    }
    $('tasks').append(row);
  }
}
async function generate(reuse = null) {
  if (busy) return;
  const pending = readSaved('studioPending');
  if (pending && reuse) return message(I18n.msg("ui.a_submission_is_unconfirmed_retry_the_same_submission_to_check_th"),true);
  let submission = pending;
  if (!submission) {
    const payload = reuse || draft();
    if (!payload.prompt.trim()) return message(I18n.msg("ui.describe_the_image_first"),true);
    submission = {key:crypto.randomUUID(),payload};
    // Store the same key BEFORE sending, so a lost response can be retried safely.
    localStorage.setItem('studioPending',JSON.stringify(submission));
  }
  setBusy(true); $('retry').hidden = true;
  try {
    const result = await post('/api/generate',submission.payload,{'Idempotency-Key':submission.key});
    localStorage.removeItem('studioPending');
    localStorage.setItem('studioJob',result.id);
    if (reuse) message(I18n.msg("ui.generating_with_the_selected_result_parameters_your_draft_stays_u"));
    await watch(result.id);
  } catch (error) {
    // Validation failures were not accepted. Network failures keep the idempotency key.
    if (error.status && error.status < 500) localStorage.removeItem('studioPending');
    $('retry').hidden = !readSaved('studioPending');
    message(I18n.plus(error.message, readSaved('studioPending') ? I18n.msg("ui.submission_unconfirmed_retry_the_same_submission_to_avoid_duplica") : ''),true);
  } finally { setBusy(Boolean(activeId)); }
}
async function watch(id) {
  const sequence = ++watching;
  activeId = id; setBusy(true);
  localStorage.setItem('studioJob',id);
  let failures = 0;
  while (sequence === watching) {
    try {
      const job = await api(I18n.plus('/api/jobs/', id));
      failures = 0; showSnapshot(job);
      if (terminal.has(job.status)) {
        localStorage.removeItem('studioJob'); activeId = null; setBusy(false);
        if (job.status === 'done') {
          showResult(job);
          refreshGallery().catch(() => {});
        } else {
          $('actions').replaceChildren(); $('progress').hidden = true;
          message(I18n.join(["", statusNames[job.status], "：", I18n.server(job.error) || '', ""]),job.status !== 'cancelled');
          if (['timed_out','submission_unknown','lost'].includes(job.status)) {
            button(I18n.msg("ui.check_original_task_do_not_regenerate"),async () => { await post(I18n.plus(I18n.plus('/api/jobs/', id), '/resume')); await watch(id); });
          }
        }
        refreshTasks().catch(() => {});
        return;
      }
      const progress = job.progress || {};
      $('progress').hidden = !progress.max;
      if (progress.max) { $('progress').max = progress.max; $('progress').value = progress.value || 0; }
      const elapsed = Math.floor(Date.now()/1000-job.created);
      message(I18n.msg("ui.p0_p1_s_p2_p3_p4_p5", {p0: statusNames[job.status], p1: elapsed, p2: I18n.server(progress.stage) || '', p3: progress.max ? I18n.join([" ", progress.value, "/", progress.max, ""]) : '', p4: job.queue_position ? I18n.msg("ui.queue_position_p0", {p0: job.queue_position}) : '', p5: I18n.server(job.error) ? I18n.plus('\n', I18n.server(job.error)) : ''}));
      $('actions').replaceChildren();
      button(I18n.msg("ui.cancel_this_task"),async () => { await post(I18n.plus(I18n.plus('/api/jobs/', id), '/cancel')); });
    } catch (error) {
      if (error.status === 404) {
        // Retain the id for diagnosis, but do not leave the UI permanently locked.
        message(I18n.msg("ui.task_not_found_in_this_database_check_that_you_started_with_the_o"),true);
        activeId = null; setBusy(false); return;
      }
      failures++;
      message(I18n.msg("ui.connection_lost_recovering_the_original_task_without_regenerating", {p0: error.message}),true);
    }
    await new Promise(resolve => setTimeout(resolve,Math.min(10000,1500*(I18n.plus(failures, 1)))));
  }
}
$('generate').onclick = () => generate();
$('retry').onclick = () => generate();
$('more').onclick = () => refreshGallery(true).catch(error => message(error.message,true));
$('mode').onchange = () => { modeChanged(); saveDraft(); };
$('resolution').onchange = () => { modeChanged(); saveDraft(); };
for (const id of ['prompt','preset','size','seed']) $(id).addEventListener('input',saveDraft);
$('clearrefs').onclick = () => { references = []; $('images').value = ''; modeChanged(); saveDraft(); };
$('images').onchange = async () => {
  const files = [...$('images').files];
  if (files.length > generation.max_references) { $('images').value=''; return message(I18n.msg("ui.up_to_3_reference_images"),true); }
  setBusy(true);
  try {
    const uploaded = [];
    for (const file of files) {
      if (file.size > 20*1024**2) throw I18n.error(I18n.msg("ui.each_image_must_be_at_most_20mb"));
      const form = new FormData(); form.append('image',file);
      message(I18n.plus(I18n.msg("ui.uploading"), file.name));
      const ref = await api('/api/upload',{method:'POST',body:form});
      uploaded.push({...ref,display:file.name});
    }
    references = uploaded; $('images').value = '';
    modeChanged(); saveDraft(); message(I18n.msg("ui.references_ready_identical_files_are_stored_only_once"));
  } catch (error) { message(error.message,true); }
  finally { setBusy(Boolean(activeId)); }
};
document.querySelectorAll('[data-example]').forEach(node => node.onclick = () => {
  const key = node.dataset.example;
  if (key !== 'edit') { references = []; $('images').value = ''; }
  $('prompt').value = examples[key] || '';
  $('mode').value = key === 'edit' ? 'edit' : key === 'sticker' ? 'transparent' : 'text';
  modeChanged(); saveDraft();
});
(async () => {
  try {
    const config = await api('/api/config'); examples = config.examples; generation = config.generation;
    I18n.text($('health'), config.backend_ready ? I18n.msg("ui.local_backend_connected") : I18n.msg("ui.backend_disconnected"));
    $('size').replaceChildren(...generation.sizes.map(([w,h]) => I18n.option(I18n.join(["", w, " × ", h, ""]), I18n.join(["", w, ",", h, ""]))));
    I18n.text($('preset').options[0], I18n.msg("ui.preview_p0_steps", {p0: generation.preview_steps}));
    I18n.text($('preset').options[1], I18n.msg("ui.standard_p0_steps_recommended", {p0: generation.standard_steps}));
    const saved = readSaved('studioDraft');
    const legacy = readSaved('studioPayload');
    if (saved) applyDraft(saved.payload,saved.references);
    else if (legacy) applyDraft(legacy);
    else $('prompt').value = examples.photo;
    await Promise.all([refreshGallery(),refreshTasks()]);
    $('retry').hidden = !readSaved('studioPending');
    setBusy(false);
    const id = localStorage.getItem('studioJob');
    if (id) watch(id);
    setInterval(() => refreshTasks().catch(() => {}),5000);
    setInterval(() => api('/api/config').then(c => { I18n.text($('health'), c.backend_ready ? I18n.msg("ui.local_backend_connected") : I18n.msg("ui.backend_disconnected")); }).catch(() => { I18n.text($('health'), I18n.msg("ui.reconnecting_195e9")); }),15000);
  } catch (error) { message(error.message,true); }
})();
