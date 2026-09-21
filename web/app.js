'use strict';
const $ = id => document.getElementById(id);
const terminal = new Set(['done', 'failed', 'cancelled', 'timed_out', 'submission_unknown', 'lost']);
const statusNames = {queued:'等待提交',submitting:'提交中',backend_queued:'后端排队',running:'生成中',reconnecting:'恢复连接',downloading:'下载与校验',cancelling:'取消中',cancelled:'已取消',done:'完成',failed:'失败',timed_out:'等待超时',submission_unknown:'提交状态待核对',lost:'后端记录缺失'};
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
    const error = new Error(data.error || `请求失败 ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return data;
}
function post(path, data = {}, headers = {}) {
  return api(path, {method:'POST',headers:{'Content-Type':'application/json',...headers},body:JSON.stringify(data)});
}
function message(text, error = false) {
  $('status').textContent = text;
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
  const size = `${payload.width || 1024},${payload.height || 1024}`;
  if (![...$('size').options].some(option => option.value === size)) {
    $('size').add(new Option(size.replace(',', ' × '), size));
  }
  $('size').value = size;
  references = refs.length ? refs : (payload.images || []).map(name => ({name}));
  $('images').value = '';
  modeChanged();
}
function modeChanged() {
  $('uploadbox').hidden = $('mode').value === 'text';
  $('sizebox').hidden = $('mode').value === 'edit' || ($('mode').value === 'transparent' && references.length > 0);
  $('refs').textContent = references.map((ref,index) => `图${index+1}：${ref.display || ref.name}`).join(' / ');
  $('refsize').textContent = '';
  if ($('mode').value !== 'text' && references.length) {
    post('/api/validate', {...draft(),prompt:$('prompt').value || '尺寸预检'}).then(result => {
      $('refsize').textContent = `预计输出：${result.actual_size.join(' × ')}（保持图1比例）`;
    }).catch(error => { $('refsize').textContent = error.message; });
  }
}
function showImage(name) {
  const image = document.createElement('img');
  image.src = '/output/' + encodeURIComponent(name);
  image.alt = '生成结果';
  $('preview').replaceChildren(image);
}
function button(label, action, parent = $('actions')) {
  const node = document.createElement('button');
  node.className = 'secondary'; node.textContent = label;
  node.onclick = () => Promise.resolve(action()).catch(error => message(error.message,true));
  parent.append(node);
  return node;
}
function showSnapshot(job) {
  const p = job.payload;
  if (!p) return;
  const mode = {text:'文生图',edit:'参考图编辑',transparent:'透明素材'}[p.mode];
  const size = job.actual_size || job.result?.actual_size || [p.width,p.height];
  $('snapshot').hidden = false;
  $('snapshot').textContent = `所选作品 / 本次任务参数（左侧是独立草稿）\n${mode} · ${size.join(' × ')} · ${p.steps}步 · 种子 ${p.seed}\n${p.prompt}`;
}
function showResult(job) {
  selectedJob = job;
  const result = job.result;
  showImage(result.files[0]); showSnapshot(job);
  $('progress').hidden = true;
  message(`已完成 · ${result.seconds}秒 · 图片和参数已保存\n${result.timings?.sampler_cached ? '本次复用了后端缓存，不计入新生成速度。' : ''}`);
  if (job.metadata_error) message('图片已完成；参数文件暂时写入失败，任务库已保留，正在重试：'+job.metadata_error,true);
  $('actions').replaceChildren();
  for (const [label,name] of [['下载 PNG',result.files[0]],['下载参数',result.prompt_id+'.json']]) {
    const a = document.createElement('a');
    a.className = 'download'; a.textContent = label;
    a.href = '/output/' + encodeURIComponent(name); a.download = name;
    $('actions').append(a);
  }
  const professional = document.createElement('a');
  professional.className='download'; professional.textContent='在专业工作台打开';
  professional.href='/pro?job='+encodeURIComponent(job.id); $('actions').append(professional);
  button('把作品参数载入草稿', () => { applyDraft(job.payload); saveDraft(); });
  if (job.payload) {
    const target = {...job.payload,preset:'standard',steps:generation.standard_steps};
    button('用此作品参数生成标准版', () => generate(target));
  }
}
async function refreshGallery(append = false) {
  const data = await api('/api/gallery?offset=' + (append ? nextPage : 0));
  if (!append) $('gallery').replaceChildren();
  for (const item of data.items) {
    const b = document.createElement('button');
    const image = document.createElement('img');
    image.src = '/thumb/' + encodeURIComponent(item.name); image.loading = 'lazy'; image.alt = item.prompt;
    const caption = document.createElement('span'); caption.textContent = item.prompt;
    b.append(image,caption);
    b.onclick = async () => {
      if (busy) return message('请先等待当前跟踪的任务完成，或在任务列表操作。');
      try { showResult(await api('/api/jobs/' + item.job_id)); }
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
  if (!data.items.length) $('tasks').textContent = '暂无任务';
  for (const job of data.items) {
    const row = document.createElement('div'); row.className = 'task';
    const label = document.createElement('span');
    label.textContent = (job.payload.prompt || '').slice(0,55);
    const meta = document.createElement('small');
    meta.textContent = `${statusNames[job.status] || job.status} · ${new Date(job.created*1000).toLocaleTimeString()}`;
    label.append(meta); row.append(label);
    button('查看', async () => {
      if (job.status === 'done') {
        if (!busy) showResult(await api('/api/jobs/' + job.id));
      } else {
        localStorage.setItem('studioJob',job.id);
        watch(job.id);
      }
    },row);
    if (!['done','failed','cancelled'].includes(job.status)) {
      button('取消', async () => { await post('/api/jobs/'+job.id+'/cancel'); await refreshTasks(); },row);
    }
    if (['timed_out','submission_unknown','lost'].includes(job.status)) {
      button('继续核对', async () => { await post('/api/jobs/'+job.id+'/resume'); watch(job.id); },row);
    }
    $('tasks').append(row);
  }
}
async function generate(reuse = null) {
  if (busy) return;
  const pending = readSaved('studioPending');
  if (pending && reuse) return message('还有一次提交未确认，请先点击“重试同一次提交”核对原任务。',true);
  let submission = pending;
  if (!submission) {
    const payload = reuse || draft();
    if (!payload.prompt.trim()) return message('请先写下画面描述',true);
    submission = {key:crypto.randomUUID(),payload};
    // Store the same key BEFORE sending, so a lost response can be retried safely.
    localStorage.setItem('studioPending',JSON.stringify(submission));
  }
  setBusy(true); $('retry').hidden = true;
  try {
    const result = await post('/api/generate',submission.payload,{'Idempotency-Key':submission.key});
    localStorage.removeItem('studioPending');
    localStorage.setItem('studioJob',result.id);
    if (reuse) message('使用所选作品的参数生成；左侧草稿保持不变。');
    await watch(result.id);
  } catch (error) {
    // Validation failures were not accepted. Network failures keep the idempotency key.
    if (error.status && error.status < 500) localStorage.removeItem('studioPending');
    $('retry').hidden = !readSaved('studioPending');
    message(error.message + (readSaved('studioPending') ? '\n提交响应未确认；请“重试同一次提交”，不会创建重复任务。' : ''),true);
  } finally { setBusy(Boolean(activeId)); }
}
async function watch(id) {
  const sequence = ++watching;
  activeId = id; setBusy(true);
  localStorage.setItem('studioJob',id);
  let failures = 0;
  while (sequence === watching) {
    try {
      const job = await api('/api/jobs/' + id);
      failures = 0; showSnapshot(job);
      if (terminal.has(job.status)) {
        localStorage.removeItem('studioJob'); activeId = null; setBusy(false);
        if (job.status === 'done') {
          showResult(job);
          refreshGallery().catch(() => {});
        } else {
          $('actions').replaceChildren(); $('progress').hidden = true;
          message(`${statusNames[job.status]}：${job.error || ''}`,job.status !== 'cancelled');
          if (['timed_out','submission_unknown','lost'].includes(job.status)) {
            button('继续核对原任务（不重新生成）',async () => { await post('/api/jobs/'+id+'/resume'); await watch(id); });
          }
        }
        refreshTasks().catch(() => {});
        return;
      }
      const progress = job.progress || {};
      $('progress').hidden = !progress.max;
      if (progress.max) { $('progress').max = progress.max; $('progress').value = progress.value || 0; }
      const elapsed = Math.floor(Date.now()/1000-job.created);
      message(`${statusNames[job.status]} · ${elapsed}秒\n${progress.stage || ''}${progress.max ? ` ${progress.value}/${progress.max}` : ''}${job.queue_position ? ` · 队列位置 ${job.queue_position}` : ''}${job.error ? '\n'+job.error : ''}`);
      $('actions').replaceChildren();
      button('取消此任务',async () => { await post('/api/jobs/'+id+'/cancel'); });
    } catch (error) {
      if (error.status === 404) {
        // Retain the id for diagnosis, but do not leave the UI permanently locked.
        message('任务不在当前任务库中，请确认启动的是原来的数据目录。',true);
        activeId = null; setBusy(false); return;
      }
      failures++;
      message(`界面连接中断，正在恢复原任务；不会重新生成。\n${error.message}`,true);
    }
    await new Promise(resolve => setTimeout(resolve,Math.min(10000,1500*(failures+1))));
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
  if (files.length > generation.max_references) { $('images').value=''; return message('最多3张参考图',true); }
  setBusy(true);
  try {
    const uploaded = [];
    for (const file of files) {
      if (file.size > 20*1024**2) throw new Error('单张图片不能超过20MB');
      const form = new FormData(); form.append('image',file);
      message('正在上传 '+file.name);
      const ref = await api('/api/upload',{method:'POST',body:form});
      uploaded.push({...ref,display:file.name});
    }
    references = uploaded; $('images').value = '';
    modeChanged(); saveDraft(); message('参考图已准备好，同一文件不会重复存储。');
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
    $('health').textContent = config.backend_ready ? '● 本地服务已连接' : '● 后端暂未连接';
    $('size').replaceChildren(...generation.sizes.map(([w,h]) => new Option(`${w} × ${h}`,`${w},${h}`)));
    $('preset').options[0].textContent = `快速预览 · ${generation.preview_steps}步`;
    $('preset').options[1].textContent = `标准质量 · ${generation.standard_steps}步（推荐）`;
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
    setInterval(() => api('/api/config').then(c => { $('health').textContent = c.backend_ready ? '● 本地服务已连接' : '● 后端暂未连接'; }).catch(() => { $('health').textContent = '● 正在重连'; }),15000);
  } catch (error) { message(error.message,true); }
})();
