import asyncio
import json
import uuid
from pathlib import Path

from aiohttp import web
from markdown_it import MarkdownIt
from .assets import Assets
from .backend import Client, ready
from .config import ROOT, STATE, OUTPUT, SERVER, GENERATION, EXAMPLES
from .files import file_lock
from .jobs import Manager
from .store import Store, CapacityError, ConflictError
from .workflow import normalize, build_workflow, PRO_DEFAULTS, PRO_OPTIONS
from .pro import preview, save_preset
from .navigation import header
from .batches import prepare

STORE=web.AppKey('store',Store)
MANAGER=web.AppKey('manager',Manager)
ASSETS=web.AppKey('assets',Assets)


def create_app(port=7860,state=STATE,output=OUTPUT,client=None,start_worker=True):
    state=Path(state);output=Path(output)
    state.mkdir(parents=True,exist_ok=True);output.mkdir(parents=True,exist_ok=True)
    store=Store(state/'jobs.sqlite3')
    store.import_completed(output)
    assets=Assets(state,output)
    manager=Manager(store,client or Client(),output)

    @web.middleware
    async def local_only(req,handler):
        allowed={f'127.0.0.1:{port}',f'localhost:{port}'}
        if req.host not in allowed:
            raise web.HTTPForbidden(text='仅供本机访问')
        if req.headers.get('Origin') and req.headers['Origin'] not in {'http://'+h for h in allowed}:
            raise web.HTTPForbidden(text='不接受跨站请求')
        try:
            return await handler(req)
        except CapacityError as exc:
            return web.json_response({'error':str(exc)},status=429)
        except ConflictError as exc:
            return web.json_response({'error':str(exc)},status=409)
        except (ValueError,TypeError) as exc:
            return web.json_response({'error':str(exc)},status=400)
        except FileNotFoundError:
            raise web.HTTPNotFound()
        except KeyError:
            return web.json_response({'error':'任务不存在'},status=404)

    async def lifecycle(app):
        # Cross-process lock is held for the lifetime of this database owner.
        with file_lock(state/'manager.lock'):
            if start_worker:
                await manager.start()
            try:
                yield
            finally:
                if start_worker:
                    await manager.close()
                store.close()

    async def index(req):
        response=web.FileResponse(ROOT/'web/index.html')
        response.headers['Cache-Control']='no-cache'
        return response

    async def static(req):
        name=req.match_info['name']
        if name not in ('app.js','style.css','pro.js','pro.css'):
            raise web.HTTPNotFound()
        response=web.FileResponse(ROOT/'web'/name)
        response.headers['Cache-Control']='no-cache'
        return response

    async def professional(req):
        return web.FileResponse(ROOT/'web/pro.html',headers={'Cache-Control':'no-cache'})

    async def pro_preview(req):
        raw=await req.json()
        return web.json_response(await asyncio.to_thread(preview,raw,assets))

    async def import_recipe(req):
        raw=await req.json()
        p=normalize(raw)
        p['seed']=raw.get('seed',-1)
        missing=[]
        for name in p['images']:
            if Path(name).name!=name or not name.startswith('studio_') or not name.endswith('.png'):
                raise ValueError('参考图片名称无效')
            if not (assets.input/name).is_file(): missing.append(name)
            else: await asyncio.to_thread(assets.describe,name)
        return web.json_response({'parameters':p,'missing_references':missing})

    async def presets(req):
        path=state/'pro-presets.json'
        if req.method=='GET':
            return web.json_response({'items':json.loads(path.read_text()) if path.exists() else []})
        data=await req.json()
        return web.json_response(await asyncio.to_thread(save_preset,path,data))

    async def reference(req):
        name=req.match_info['name']
        await asyncio.to_thread(assets.describe,name)
        return web.FileResponse(assets.input/name)

    async def config(req):
        return web.json_response({'examples':EXAMPLES,'backend_ready':await asyncio.to_thread(ready),
                                 'generation':GENERATION,'queue_limit':SERVER['queue_limit'],'pro':{'defaults':PRO_DEFAULTS,'options':PRO_OPTIONS}})

    async def upload(req):
        reader=await req.multipart();part=await reader.next()
        if part is None or part.name!='image':
            raise ValueError('请选择图片')
        data=bytearray()
        while chunk:=await part.read_chunk():
            data.extend(chunk)
            if len(data)>20*1024**2:
                raise ValueError('图片不能超过20MB')
        return web.json_response(await asyncio.to_thread(assets.add,bytes(data)))

    async def validate(req):
        p=normalize(await req.json())
        size=await asyncio.to_thread(assets.validate,p)
        return web.json_response({'actual_size':size})

    async def generate(req):
        raw=await req.json()
        key=req.headers.get('Idempotency-Key')
        if not key:
            raise ValueError('缺少Idempotency-Key，请刷新页面后重试')
        try: uuid.UUID(key)
        except ValueError: raise ValueError('请求ID格式无效')
        # No await between capacity check and registration: Store also uses BEGIN IMMEDIATE.
        p=normalize(raw)
        existing=store.by_key(key)
        if existing:
            # create checks that re-used keys have identical original parameters.
            job=store.create(key,raw,p,{},SERVER['queue_limit'])
            return web.json_response({'id':job['id'],'payload':job['payload'],'actual_size':job.get('actual_size')})
        size=await asyncio.to_thread(assets.validate,p)
        workflow=build_workflow(**p)
        job=store.create(key,raw,p,workflow,SERVER['queue_limit'])
        store.update(job['id'],actual_size=size)
        return web.json_response({'id':job['id'],'payload':p,'actual_size':size})

    async def batch_generate(req):
        raw=await req.json()
        key=req.headers.get('Idempotency-Key','')
        try: uuid.UUID(key)
        except ValueError: raise ValueError('批次需要有效的Idempotency-Key')
        existing=store.batch_by_key(key,raw)
        if existing: return web.json_response(existing)
        prepared=await asyncio.to_thread(prepare,raw,assets,SERVER['queue_limit'])
        return web.json_response(store.create_batch(key,raw,prepared,SERVER['queue_limit']))

    async def batches(req):
        return web.json_response({'items':[{**batch,'jobs':[store.summary(store.get(i)) for i in batch['job_ids']]} for batch in store.batches()]})

    async def cancel_batch(req):
        row=store.db.execute('SELECT data FROM batches WHERE id=?',(req.match_info['id'],)).fetchone()
        if not row: raise KeyError()
        batch=json.loads(row[0])
        for job_id in batch['job_ids']:
            manager.cancel(job_id)
        return web.json_response({'id':batch['id'],'message':'已请求取消本批未完成任务，已完成作品保留'})

    async def job(req):
        found=store.get(req.match_info['id'])
        if not found: raise KeyError()
        return web.json_response(found)

    async def jobs(req):
        limit=min(40,max(1,int(req.query.get('limit',20))))
        offset=max(0,int(req.query.get('offset',0)))
        rows=store.list(limit=limit+1,offset=offset)
        return web.json_response({'items':[store.summary(j) for j in rows[:limit]] if req.query.get('summary')=='1' else rows[:limit],'next':offset+limit if len(rows)>limit else None})

    async def cancel(req):
        return web.json_response(manager.cancel(req.match_info['id']))

    async def resume(req):
        return web.json_response(manager.resume(req.match_info['id']))

    async def gallery(req):
        offset=max(0,int(req.query.get('offset',0)))
        # Completed records, descending order; old records are imported once on startup.
        rows=store.db.execute('SELECT data FROM jobs WHERE status=? ORDER BY created DESC LIMIT 21 OFFSET ?',('done',offset)).fetchall()
        items=[]
        for row in rows[:20]:
            data=json.loads(row[0]);result=data['result']
            for name in result.get('files',[]):
                if Path(name).name==name and (output/name).is_file():
                    items.append({'name':name,'job_id':data['id'],'prompt':data['payload'].get('prompt','')})
        return web.json_response({'items':items,'next':offset+20 if len(rows)>20 else None})

    async def thumb(req):
        return web.FileResponse(await asyncio.to_thread(assets.thumbnail,req.match_info['name']))

    async def download(req):
        name=req.match_info['name']
        if Path(name).name!=name or Path(name).suffix not in ('.png','.json'):
            raise web.HTTPNotFound()
        path=output/name
        if not path.is_file() or not path.resolve().is_relative_to(output.resolve()):
            raise web.HTTPNotFound()
        return web.FileResponse(path)

    async def guide(req):
        names={'guide':'GUIDE.md','workflow':'WORKFLOW.md','research':'docs/RESEARCH.md','validation':'docs/OPTIMIZATION_VALIDATION.md','pro':'docs/PRO_GUIDE.md'}
        key=req.match_info.get('page','guide')
        if key not in names: raise web.HTTPNotFound()
        path=ROOT/names[key]
        if not path.exists(): raise web.HTTPNotFound()
        content=MarkdownIt('commonmark',{'html':False}).enable('table').render(path.read_text())
        # Link common local documentation to the in-app routes.
        for source,target in [('docs/RESEARCH.md','/help/research'),('WORKFLOW.md','/help/workflow'),('GUIDE.md','/help/guide'),('docs/VALIDATION.md','/help/validation'),('docs/OPTIMIZATION_VALIDATION.md','/help/validation')]:
            content=content.replace('href="'+source+'"','href="'+target+'"')
        return web.Response(text='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>使用指南</title><link rel="stylesheet" href="/static/style.css">'+header('help')+'<main class="help"><a href="/">← 返回画室</a>'+content+'</main></html>',content_type='text/html')

    app=web.Application(client_max_size=21*1024**2,middlewares=[local_only])
    app[STORE]=store;app[MANAGER]=manager;app[ASSETS]=assets
    app.cleanup_ctx.append(lifecycle)
    app.add_routes([web.get('/',index),web.get('/pro',professional),web.get('/static/{name}',static),web.get('/api/config',config),
                    web.post('/api/pro/preview',pro_preview),web.post('/api/pro/recipe',import_recipe),web.post('/api/pro/batches',batch_generate),web.get('/api/pro/batches',batches),web.post('/api/pro/batches/{id}/cancel',cancel_batch),web.get('/api/pro/presets',presets),web.post('/api/pro/presets',presets),web.get('/reference/{name}',reference),
                    web.post('/api/upload',upload),web.post('/api/validate',validate),web.post('/api/generate',generate),
                    web.get('/api/jobs',jobs),web.get('/api/jobs/{id}',job),web.post('/api/jobs/{id}/cancel',cancel),
                    web.post('/api/jobs/{id}/resume',resume),web.get('/api/gallery',gallery),
                    web.get('/thumb/{name}',thumb),web.get('/output/{name}',download),
                    web.get('/help',guide),web.get('/help/{page}',guide)])
    return app


def serve(port):
    print(f'打开浏览器：http://127.0.0.1:{port}  Ctrl+C关闭界面；模型后端保留，任务可恢复。',flush=True)
    web.run_app(create_app(port),host='127.0.0.1',port=port,print=None)
