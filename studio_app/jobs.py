import asyncio
import contextlib
import hashlib
import io
import json
import time
import urllib.parse
from pathlib import Path

import aiohttp
from PIL import Image
from .backend import BackendUnavailable, BackendRejected
from .config import SERVER
from .files import atomic_bytes, atomic_json
from .store import ACTIVE, TERMINAL

STAGES={'1':'加载生成模型','2':'准备缓存','3':'加载编码器','4':'加载VAE','5':'编码提示词与参考图',
        '6':'准备画布','7':'采样','8':'解码','9':'保存图片'}


class Manager:
    def __init__(self,store,client,output,timeout=None):
        self.store=store
        self.client=client
        self.output=Path(output)
        self.timeout=SERVER['task_timeout'] if timeout is None else timeout
        self.client_id='studio-'+hashlib.sha256(str(self.output.resolve()).encode()).hexdigest()[:20]
        self.worker=None
        self.listener=None

    def update(self,job_id,**changes):
        current=self.store.get(job_id)
        if current and all(current.get(key)==value for key,value in changes.items()):
            return current
        job=self.store.update(job_id,**changes)
        if any(k in changes for k in ('status','result','error','outputs')):
            self.export_record(job)
        return job

    def export_record(self,job):
        record=job.get('result') or {'prompt_id':job['prompt_id'],'job_id':job['id'],
                 'workflow':job['workflow'],'payload':job['payload'],'timings':job.get('timings',{}),
                 'outputs':job.get('outputs')}
        record=dict(record,status=job['status'],error=job.get('error'),batch=job.get('batch'))
        try:
            atomic_json(self.output/(job['prompt_id']+'.json'),record)
        except OSError as exc:
            # SQLite remains authoritative if the separate output volume is unavailable.
            if job.get('metadata_error')!=str(exc):
                self.store.update(job['id'],metadata_error=str(exc))
        else:
            if job.get('metadata_error'):
                self.store.update(job['id'],metadata_error=None)

    async def start(self):
        await self.client.open()
        self.worker=asyncio.create_task(self.run())
        if hasattr(self.client,'session'):
            self.listener=asyncio.create_task(self.listen())

    async def close(self):
        # Stop observing, never cancel the user's GPU jobs when the web UI closes.
        for task in (self.worker,self.listener):
            if task:
                task.cancel()
        for task in (self.worker,self.listener):
            if task:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.client.close()

    async def run(self):
        while True:
            await self.tick()
            await asyncio.sleep(SERVER['poll_interval'])

    async def tick(self):
        pending_exports=self.store.db.execute("SELECT data FROM jobs WHERE json_extract(data,'$.metadata_error') IS NOT NULL LIMIT 100").fetchall()
        for row in pending_exports:
            self.export_record(json.loads(row[0]))
        jobs=self.store.list(ACTIVE,limit=100)
        for original in jobs:
            job=self.store.get(original['id'])
            if job['status'] not in ACTIVE:
                continue
            try:
                await self.step(job)
            except BackendUnavailable as exc:
                current=self.store.get(job['id'])
                status='downloading' if current.get('outputs') else 'reconnecting'
                self.update(job['id'],status=status,error=str(exc))
            except BackendRejected as exc:
                self.update(job['id'],status='failed',error=str(exc))
            except (OSError,ValueError,KeyError) as exc:
                current=self.store.get(job['id'])
                self.update(job['id'],status='downloading' if current.get('outputs') else 'failed',error=str(exc))

    async def step(self,job):
        job_id=job['id'];now=time.time()
        if job['deadline'] is not None and now>job['deadline']:
            self.update(job_id,status='timed_out',error='等待超时，后端任务未自动取消。可继续跟踪或取消该任务。')
            return
        if job['status']=='queued' and job['submitted_at'] is None:
            if job['cancel_requested']:
                self.update(job_id,status='cancelled',error=None)
                return
            # The intent and chosen UUID are durable BEFORE the non-idempotent POST.
            self.update(job_id,status='submitting',submitted_at=now,deadline=now+self.timeout,error=None)
            try:
                response=await self.client.request('/prompt',{'prompt':job['workflow'],'prompt_id':job['prompt_id'],
                                                             'client_id':self.client_id})
            except BackendUnavailable:
                self.update(job_id,status='reconnecting',error='提交响应丢失，正在按任务ID核对；不会重复提交。')
                return
            if response.get('prompt_id')!=job['prompt_id']:
                self.update(job_id,status='submission_unknown',error='后端未保留指定任务ID，需要人工核对队列，未重发任务。')
                return
            self.update(job_id,status='backend_queued',observed=True,error=None)
            return
        if job.get('outputs'):
            await self.download(job)
            return
        history=(await self.client.request('/history/'+job['prompt_id'])).get(job['prompt_id'])
        if history:
            status=history.get('status',{})
            messages=status.get('messages',[])
            if status.get('status_str')=='error':
                interrupted=any(m[0]=='execution_interrupted' for m in messages)
                error=next((m[1].get('exception_message',str(m[1])) for m in messages if m[0]=='execution_error'),'任务已被中断')
                if 'aimdo memory compile' in error:
                    error+='；请用带 --disable-comfy-compiler 的兼容后端启动。'
                self.update(job_id,status='cancelled' if interrupted else 'failed',error=error)
                return
            if status.get('completed'):
                outputs=[im for out in history.get('outputs',{}).values() for im in out.get('images',[]) if im.get('type')=='output']
                if not outputs:
                    self.update(job_id,status='failed',error='后端执行完成但没有输出图片')
                    return
                times={m[0]:m[1].get('timestamp') for m in messages if isinstance(m[1],dict)}
                timings=job.get('timings',{}).copy()
                started=times.get('execution_start');ended=times.get('execution_success')
                if started and ended:
                    timings['backend_execution_seconds']=round((ended-started)/1000,3)
                    timings['backend_queue_seconds']=round(max(0,started/1000-job['submitted_at']),3)
                cached=[n for name,data in messages if name=='execution_cached' for n in data.get('nodes',[])]
                timings['sampler_cached']='7' in cached
                self.update(job_id,status='downloading',outputs=outputs,observed=True,error=None,timings=timings,
                            progress={'stage':'下载与校验图片'})
                await self.download(self.store.get(job_id))
                return
        queue=await self.client.request('/queue')
        running={x[1] for x in queue.get('queue_running',[])}
        pending=[x[1] for x in queue.get('queue_pending',[])]
        present=job['prompt_id'] in running or job['prompt_id'] in pending
        if present:
            if job['cancel_requested']:
                await self.client.request('/api/jobs/'+job['prompt_id']+'/cancel',{})
                self.update(job_id,status='cancelling',observed=True,error=None)
            else:
                self.update(job_id,status='running' if job['prompt_id'] in running else 'backend_queued',
                            observed=True,missing_since=None,error=None,
                            queue_position=0 if job['prompt_id'] in running else pending.index(job['prompt_id'])+len(running)+1)
        else:
            # A task may move queue -> history between the two reads. Recheck on a later tick.
            missing_since=job.get('missing_since') or now
            if now-missing_since<30:
                self.store.update(job_id,missing_since=missing_since)
            elif job['cancel_requested'] and job['observed']:
                self.update(job_id,status='cancelled',error=None)
            else:
                self.update(job_id,status='lost' if job['observed'] else 'submission_unknown',
                            error='后端已无此任务记录，可能已重启或提交未到达。未自动重新生成；可继续核对或明确创建新任务。')

    async def download(self,job):
        started=time.monotonic();files=[]
        for index,item in enumerate(job['outputs']):
            filename=f"{job['prompt_id']}_{index}_{Path(item['filename']).name}"
            destination=self.output/filename
            valid=False
            if destination.exists():
                try:
                    with Image.open(destination) as im: im.verify()
                    valid=True
                except (OSError,ValueError):
                    pass
            if not valid:
                query=urllib.parse.urlencode({k:item[k] for k in ('filename','subfolder','type') if k in item})
                blob=await self.client.request('/view?'+query,raw=True)
                with Image.open(io.BytesIO(blob)) as im:
                    if im.format!='PNG':
                        raise ValueError('输出格式不是预期的PNG')
                    im.verify()
                atomic_bytes(destination,blob)
            files.append(filename)
        timings=job.get('timings',{}) | {'download_seconds':round(time.monotonic()-started,3)}
        result={'prompt_id':job['prompt_id'],'job_id':job['id'],'status':'done','workflow':job['workflow'],
                'payload':job['payload'],'seconds':round(time.time()-job['submitted_at'],2),
                'files':files,'timings':timings,'actual_size':job.get('actual_size')}
        self.update(job['id'],status='done',result=result,error=None,timings=timings,
                    progress={'stage':'已完成'})

    def cancel(self,job_id):
        job=self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job['status'] in ('done','failed','cancelled'):
            return job
        if job['submitted_at'] is None:
            return self.update(job_id,status='cancelled',cancel_requested=True,error=None)
        return self.update(job_id,status='cancelling',cancel_requested=True,deadline=time.time()+120,error=None)

    def resume(self,job_id):
        job=self.store.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job['status'] not in ('timed_out','submission_unknown','lost'):
            return job
        if job['submitted_at'] is None:
            raise ValueError('没有已提交的后端任务可恢复')
        if len(self.store.list(ACTIVE,limit=SERVER['queue_limit']))>=SERVER['queue_limit']:
            raise ValueError('活动任务已达上限，请稍后继续跟踪')
        return self.update(job_id,status='downloading' if job.get('outputs') else 'reconnecting',
                           error=None,deadline=time.time()+self.timeout,missing_since=None,cancel_requested=False)

    async def listen(self):
        while True:
            try:
                async with self.client.session.ws_connect(self.client.base+'/ws?clientId='+self.client_id,heartbeat=20) as ws:
                    async for msg in ws:
                        if msg.type==aiohttp.WSMsgType.TEXT:
                            self.event(json.loads(msg.data))
            except (aiohttp.ClientError,asyncio.TimeoutError,ValueError):
                await asyncio.sleep(2)

    def event(self,message):
        kind=message.get('type');data=message.get('data',{})
        job_id=data.get('prompt_id')
        if not job_id:
            return
        job=self.store.get(job_id)
        if not job or job['status'] not in ACTIVE:
            return
        progress=job.get('progress',{}).copy()
        if kind=='executing':
            node=data.get('node')
            if node is None:
                return
            now=time.time();timings=job.get('timings',{}).copy()
            prev=progress.get('node');since=progress.get('since')
            if prev and since:
                timings['node_'+str(prev)+'_seconds']=round(now-since,3)
            progress={'node':str(node),'stage':STAGES.get(str(node),'处理参考图'),'since':now}
            self.store.update(job_id,progress=progress,timings=timings)
        elif kind=='progress':
            progress.update(value=data.get('value'),max=data.get('max'),stage='采样')
            self.store.update(job_id,progress=progress)
