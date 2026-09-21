import asyncio
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import aiohttp
from .config import ROOT, STATE, BACKEND, SERVER, MODELS
from .files import atomic_json, file_lock


class BackendUnavailable(RuntimeError):
    pass


class BackendRejected(RuntimeError):
    pass


def request(path, data=None, raw=False, timeout=15):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(BACKEND+path, data=body, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=timeout) as r:
            result=r.read()
        return result if raw else json.loads(result)
    except urllib.error.HTTPError as e:
        raise BackendRejected(f'ComfyUI HTTP {e.code}: '+e.read().decode(errors='replace')[:2000]) from e
    except (OSError,ValueError) as e:
        raise BackendUnavailable('暂时无法连接ComfyUI，将保留任务等待恢复。') from e


class Client:
    def __init__(self, base=BACKEND):
        self.base=base
        self.session=None

    async def open(self):
        self.session=aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), trust_env=False)

    async def close(self):
        if self.session:
            await self.session.close()

    async def request(self,path,data=None,raw=False):
        try:
            async with self.session.request('POST' if data is not None else 'GET',self.base+path,json=data) as r:
                if r.status >= 500:
                    raise BackendUnavailable('后端暂时不可用：HTTP '+str(r.status))
                if r.status >= 400:
                    raise BackendRejected(f'ComfyUI HTTP {r.status}: '+(await r.text())[:2000])
                return await r.read() if raw else await r.json()
        except (aiohttp.ClientError,asyncio.TimeoutError) as e:
            raise BackendUnavailable('连接中断，正在重新连接已有任务。') from e


def ready():
    try:
        return bool(request('/system_stats',timeout=2).get('system'))
    except RuntimeError:
        return False


def check_backend():
    stats=request('/system_stats')
    args=stats['system'].get('argv',[])
    if '--disable-comfy-compiler' not in args:
        raise RuntimeError('已有ComfyUI缺少 --disable-comfy-compiler。请等待其任务完成后停止旧后端，再运行 ./start.sh。')
    for node, field, model in [('UnetLoaderGGUF','unet_name',MODELS['diffusion_models']),
                               ('CLIPLoader','clip_name',MODELS['text_encoders']),
                               ('VAELoader','vae_name',MODELS['vae'])]:
        info=request('/object_info/'+node)
        try:
            choices=info[node]['input']['required'][field][0]
        except (KeyError,TypeError) as e:
            raise RuntimeError('缺少兼容节点：'+node) from e
        if model not in choices:
            raise RuntimeError('后端找不到模型：'+model)
    for node in ('TextEncodeQwenImage21','QwenImage21Cache','JoinImageWithAlpha'):
        if node not in request('/object_info/'+node):
            raise RuntimeError('缺少节点：'+node)
    return stats


def ensure_backend():
    # A shared startup lock protects all UI ports and CLI invocations.
    with file_lock(ROOT/'state/backend-start.lock',blocking=True):
        if ready():
            check_backend()
            print('复用已验证的ComfyUI：'+BACKEND,flush=True)
            return
        from .model_install import ensure_startup_models
        ensure_startup_models(ROOT/'ComfyUI/models', MODELS)
        (ROOT/'logs').mkdir(exist_ok=True)
        with (ROOT/'logs/comfyui.log').open('a') as log:
            proc=subprocess.Popen([str(ROOT/'ComfyUI/.venv/bin/python'),'main.py','--listen','127.0.0.1',
                                   '--port',str(SERVER['backend_port']),'--reserve-vram','0.5','--disable-comfy-compiler'],
                                  cwd=ROOT/'ComfyUI',stdout=log,stderr=log,start_new_session=True)
        # The backend intentionally survives UI shutdown, so tasks can be recovered.
        atomic_json(ROOT/'state/backend-process.json',{'pid':proc.pid,'started':time.time()})
        try:
            for _ in range(180):
                if proc.poll() is not None:
                    raise RuntimeError('后端启动失败，详见 logs/comfyui.log')
                if ready():
                    check_backend()
                    print('模型服务已启动：'+BACKEND,flush=True)
                    return
                time.sleep(1)
            raise RuntimeError('后端启动超时，详见 logs/comfyui.log')
        except BaseException:
            if proc.poll() is None:
                proc.terminate()
            raise


def stop_backend():
    queue=request('/queue')
    if queue['queue_running'] or queue['queue_pending']:
        raise RuntimeError('后端仍有任务，请先等待完成或在界面取消自己的任务。')
    path=ROOT/'state/backend-process.json'
    if not path.exists():
        raise RuntimeError('该后端不是本启动器记录的进程，请在原终端关闭。')
    pid=int(json.loads(path.read_text())['pid'])
    procpath=ROOT/'ComfyUI'
    try:
        cwd=os.readlink(f'/proc/{pid}/cwd')
        args=open(f'/proc/{pid}/cmdline','rb').read().split(b'\0')
    except OSError as e:
        raise RuntimeError('记录的进程已不存在。') from e
    if cwd != str(procpath) or b'main.py' not in args:
        raise RuntimeError('进程身份不匹配，未停止任何进程。')
    os.kill(pid,15)
