import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from .config import ROOT, STATE, OUTPUT, EXAMPLES, SERVER, MODELS
from .assets import Assets
from .backend import Client, ensure_backend, check_backend, ready, stop_backend
from .files import file_lock
from .jobs import Manager
from .store import Store, TERMINAL
from .workflow import normalize, build_workflow, payload_from_workflow


async def run_record(workflow,out_dir=OUTPUT,timeout=1800,progress=None,record=None,payload=None):
    """CLI has its own durable registry; it never resubmits a resumed backend job."""
    out_dir=Path(out_dir);state=out_dir/'.cli-state'
    with file_lock(state/'manager.lock'):
        store=Store(state/'jobs.sqlite3')
        client=Client();manager=Manager(store,client,out_dir,timeout)
        try:
            if record and record.get('prompt_id'):
                pid=record['prompt_id'];job=store.get(pid)
                if not job:
                    # Import a metadata file from the UI/legacy runner and attach by backend id.
                    p=record.get('payload') or payload_from_workflow(workflow)
                    job=store.create(str(uuid.uuid4()),p,p,workflow,limit=100)
                    store.db.execute('DELETE FROM jobs WHERE id=?',(job['id'],));store.db.commit()
                    job.update(id=pid,prompt_id=pid,status='reconnecting',submitted_at=time.time(),deadline=time.time()+timeout,
                               outputs=record.get('outputs'))
                    store._insert(job);store.db.commit()
                else:
                    manager.resume(pid)
            else:
                p=payload or payload_from_workflow(workflow)
                job=store.create(str(uuid.uuid4()),p,p,workflow,limit=100)
            if progress: progress(job['prompt_id'])
            await client.open()
            while True:
                await manager.tick()
                current=store.get(job['id'])
                if current['status'] in TERMINAL:
                    if current['status']=='done': return current['result']
                    raise RuntimeError(current.get('error') or current['status'])
                await asyncio.sleep(SERVER['poll_interval'])
        finally:
            await client.close();store.close()


def run_workflow(workflow,out_dir=OUTPUT,timeout=1800,progress=None,record=None):
    return asyncio.run(run_record(workflow,out_dir,timeout,progress,record))


def doctor():
    import torch
    ok=True
    for folder,name in MODELS.items():
        path=ROOT/'ComfyUI/models'/folder/name
        exists=path.is_file() and path.stat().st_size>1_000_000
        print(('OK  ' if exists else '缺失  ')+name);ok &= exists
    print(f'PyTorch {torch.__version__}，CUDA可用：{torch.cuda.is_available()}')
    ok &= torch.cuda.is_available()
    if ready():
        try:
            stats=check_backend();print('后端节点、模型列表、兼容参数检查通过：'+stats['system']['comfyui_version'])
        except RuntimeError as e:
            print(str(e));ok=False
    else: print('后端尚未启动，./start.sh会自动启动')
    return 0 if ok else 1


def main():
    parser=argparse.ArgumentParser(description='本地画室 · Qwen-Image-2.1')
    sub=parser.add_subparsers(dest='command',required=True)
    ui=sub.add_parser('ui');ui.add_argument('--port',type=int,default=SERVER['ui_port'])
    sub.add_parser('doctor');sub.add_parser('stop-backend')
    gen=sub.add_parser('generate')
    gen.add_argument('prompt',nargs='?');gen.add_argument('--example',choices=EXAMPLES)
    gen.add_argument('--mode',choices=['text','edit','transparent'],default='text')
    gen.add_argument('--preset',choices=['preview','standard'],default='standard')
    gen.add_argument('--image',action='append',default=[])
    for name,default in [('width',1024),('height',1024),('resolution',768),('seed',-1),('steps',None)]:
        gen.add_argument('--'+name,type=int,default=default)
    gen.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    if args.command=='doctor': return doctor()
    if args.command=='stop-backend':stop_backend();return 0
    if args.command=='generate':
        # Reject cheap invalid inputs before starting a GPU process or uploading files.
        p={'prompt':args.prompt or EXAMPLES.get(args.example,''),'mode':args.mode,'preset':args.preset,
           'width':args.width,'height':args.height,'resolution':args.resolution,'steps':args.steps,'seed':args.seed,
           'images':['pending']*len(args.image)}
        p=normalize(p)
    ensure_backend()
    if args.command=='ui':
        from .server import serve
        serve(args.port)
    else:
        assets=Assets();p['images']=[assets.add(Path(f).read_bytes())['name'] for f in args.image]
        assets.validate(p)
        result=asyncio.run(run_record(build_workflow(**p),args.output,payload=p,
                                     progress=lambda pid:print('任务ID：'+pid,flush=True)))
        print(json.dumps(result|{'workflow':'参数已保存至同目录JSON'},ensure_ascii=False,indent=2))
    return 0
