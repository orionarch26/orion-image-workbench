import asyncio
import io
import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from studio_app import backend
from studio_app.assets import Assets
from studio_app.jobs import Manager
from studio_app.store import Store, CapacityError, ConflictError
from studio_app.workflow import build_workflow, normalize, reference_size


def png(size=(32,32)):
    buf=io.BytesIO();Image.new('RGBA',size,(255,100,0,255)).save(buf,format='PNG');return buf.getvalue()


class FakeClient:
    def __init__(self):
        self.running=[];self.pending=[];self.history={};self.posts=[];self.calls=[]
        self.lose_ack=False;self.offline=False;self.bad_image=False
    async def open(self): pass
    async def close(self): pass
    async def request(self,path,data=None,raw=False):
        self.calls.append((path,data))
        if self.offline: raise backend.BackendUnavailable('offline')
        if path=='/prompt':
            self.posts.append(data);self.pending.append([0,data['prompt_id']])
            if self.lose_ack:raise backend.BackendUnavailable('ack lost')
            return {'prompt_id':data['prompt_id']}
        if path.startswith('/history/'):
            pid=path.rsplit('/',1)[1];return {pid:self.history[pid]} if pid in self.history else {}
        if path=='/queue':return {'queue_running':self.running,'queue_pending':self.pending}
        if path.startswith('/view?'):return b'broken PNG' if self.bad_image else png()
        if path.endswith('/cancel'):
            pid=path.split('/')[-2]
            self.pending=[r for r in self.pending if r[1]!=pid]
            self.running=[r for r in self.running if r[1]!=pid]
            return {'cancelled':True}
        raise AssertionError(path)
    def finish(self,pid):
        self.pending=[];self.running=[]
        self.history[pid]={'status':{'completed':True,'status_str':'success','messages':[
            ['execution_start',{'timestamp':1000}],['execution_cached',{'nodes':['1']}],
            ['execution_success',{'timestamp':2500}]]},
            'outputs':{'9':{'images':[{'filename':'cat.png','subfolder':'studio','type':'output'}]}}}


class WorkflowTests(unittest.TestCase):
    def test_edit_latent_and_alpha(self):
        wf=build_workflow('cat',mode='edit',images=['a.png','b.png'])
        self.assertEqual(wf['7']['inputs']['latent_image'],['5',2])
        self.assertEqual(wf['5']['inputs']['images.image_2'],['25',0])
        self.assertEqual(wf['25']['class_type'],'JoinImageWithAlpha')
    def test_invalid_parameters(self):
        for kwargs in ({'width':2048},{'width':513},{'mode':'edit'},{'steps':0},{'seed':-2},{'steps':1.5},{'seed':True},{'images':'abc'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):build_workflow('cat',**kwargs)
    def test_alpha_and_determinism(self):
        a=build_workflow('cat',mode='transparent',seed=42)
        self.assertEqual(a,build_workflow('cat',mode='transparent',seed=42))
        self.assertIn('RGBA',a['5']['inputs']['prompt'])
        self.assertEqual(a['7']['inputs']['cfg'],1)
    def test_actual_edit_dimensions(self):
        self.assertEqual(reference_size(1200,800,768),(928,640))
        with self.assertRaises(ValueError):reference_size(2048,1,768)
        with self.assertRaises(ValueError):reference_size(2048,512,1024)
    def test_backend_requires_compatible_flags(self):
        with patch('studio_app.backend.request',return_value={'system':{'argv':['main.py']}}):
            with self.assertRaisesRegex(RuntimeError,'disable-comfy-compiler'):backend.check_backend()
    def test_existing_backend_is_checked_before_reuse(self):
        with patch('studio_app.backend.ready',return_value=True),patch('studio_app.backend.check_backend',side_effect=RuntimeError('bad flags')),patch('subprocess.Popen') as spawn:
            with self.assertRaisesRegex(RuntimeError,'bad flags'):backend.ensure_backend()
            spawn.assert_not_called()


class AssetTests(unittest.TestCase):
    def test_deduplicate_and_validate(self):
        with tempfile.TemporaryDirectory() as d:
            a=Assets(Path(d)/'state',Path(d)/'output',Path(d)/'input')
            one=a.add(png());two=a.add(png())
            self.assertEqual(one,two)
            self.assertEqual(len(list((Path(d)/'input').glob('*.png'))),1)
            self.assertEqual(a.validate(normalize({'prompt':'edit','mode':'edit','images':[one['name']]})),[768,768])
            with self.assertRaises(ValueError):a.describe('../evil.png')
            with self.assertRaises(ValueError):a.add(png((2048,1)))
    def test_thumbnail_does_not_change_original(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'output';out.mkdir();original=png((1024,1024));(out/'x.png').write_bytes(original)
            a=Assets(Path(d)/'state',out,Path(d)/'input')
            thumbnail=a.thumbnail('x.png')
            with Image.open(thumbnail) as im:self.assertEqual(im.size,(320,320))
            self.assertEqual((out/'x.png').read_bytes(),original)


class StoreTests(unittest.TestCase):
    def test_idempotency(self):
        with tempfile.TemporaryDirectory() as d:
            s=Store(Path(d)/'tasks.db');raw={'prompt':'cat','seed':-1}
            a=s.create('same',raw,normalize(raw),build_workflow('cat'))
            b=s.create('same',raw,normalize(raw),build_workflow('cat'))
            self.assertEqual(a['id'],b['id']);self.assertEqual(a['payload']['seed'],b['payload']['seed'])
            with self.assertRaises(ConflictError):s.create('same',{'prompt':'dog'},{},{})
            s.close()
    def test_capacity_across_connections(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'tasks.db';Store(path).close()
            def create(i):
                s=Store(path)
                try:s.create(str(i),{'prompt':'cat'},{},{},limit=5);return True
                except CapacityError:return False
                finally:s.close()
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted=list(pool.map(create,range(8)))
            self.assertEqual(sum(accepted),5)


class JobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.store=Store(self.root/'jobs.db');self.client=FakeClient();self.manager=Manager(self.store,self.client,self.root/'output')
    def tearDown(self):self.store.close();self.tmp.cleanup()
    def job(self):
        p=normalize({'prompt':'cat','seed':42});return self.store.create(str(time.time_ns()),p,p,build_workflow(**p))
    async def test_lost_submission_response_never_resubmits(self):
        j=self.job();self.client.lose_ack=True
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'reconnecting')
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'backend_queued')
        self.assertEqual(len(self.client.posts),1)
    async def test_disconnect_recovers_same_task(self):
        j=self.job();await self.manager.tick();self.client.offline=True
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'reconnecting')
        meta=json.loads((self.root/'output'/f"{j['id']}.json").read_text());self.assertEqual(meta['status'],'reconnecting')
        self.client.offline=False;self.client.finish(j['id']);await self.manager.tick()
        self.assertEqual(self.store.get(j['id'])['status'],'done');self.assertEqual(len(self.client.posts),1)
    async def test_restart_preserves_mapping_and_queued_jobs(self):
        j=self.job();await self.manager.tick();queued=self.job()
        self.store.close();self.store=Store(self.root/'jobs.db');self.manager=Manager(self.store,self.client,self.root/'output')
        self.client.finish(j['id']);await self.manager.tick()
        self.assertEqual(self.store.get(j['id'])['status'],'done')
        self.assertEqual(len(self.client.posts),2)
        self.assertEqual(self.client.posts[-1]['prompt_id'],queued['id'])
    async def test_download_retry_only_downloads(self):
        j=self.job();await self.manager.tick();self.client.finish(j['id']);self.client.bad_image=True
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'downloading')
        self.client.bad_image=False;await self.manager.tick()
        done=self.store.get(j['id']);self.assertEqual(done['status'],'done');self.assertEqual(len(self.client.posts),1)
        self.assertEqual(done['result']['timings']['backend_execution_seconds'],1.5)
        self.assertFalse(done['result']['timings']['sampler_cached'])
    async def test_timeout_resume_does_not_submit(self):
        j=self.job();await self.manager.tick();self.store.update(j['id'],deadline=0)
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'timed_out')
        self.manager.resume(j['id']);self.client.finish(j['id']);await self.manager.tick()
        self.assertEqual(self.store.get(j['id'])['status'],'done');self.assertEqual(len(self.client.posts),1)
    async def test_metadata_write_failure_keeps_tracking_and_retries(self):
        j=self.job()
        with patch('studio_app.jobs.atomic_json',side_effect=OSError('output volume unavailable')):
            await self.manager.tick()
            self.client.finish(j['id']);await self.manager.tick()
        self.assertEqual(self.store.get(j['id'])['status'],'done')
        self.assertIn('unavailable',self.store.get(j['id'])['metadata_error'])
        await self.manager.tick()
        self.assertIsNone(self.store.get(j['id'])['metadata_error'])
        self.assertEqual(json.loads((self.root/'output'/f"{j['id']}.json").read_text())['status'],'done')
        self.assertEqual(len(self.client.posts),1)
    async def test_cancel_before_submission(self):
        j=self.job();self.manager.cancel(j['id']);await self.manager.tick()
        self.assertEqual(self.store.get(j['id'])['status'],'cancelled');self.assertEqual(self.client.posts,[])
    async def test_cancel_is_scoped_to_exact_backend_id(self):
        j=self.job();await self.manager.tick();self.manager.cancel(j['id']);await self.manager.tick()
        cancelled=[path for path,_ in self.client.calls if path.endswith('/cancel')]
        self.assertEqual(cancelled,['/api/jobs/'+j['id']+'/cancel'])
        self.assertFalse(any(path=='/interrupt' for path,_ in self.client.calls))
    async def test_missing_submitted_task_is_not_recreated(self):
        j=self.job();await self.manager.tick();self.client.pending=[]
        self.store.update(j['id'],missing_since=time.time()-40)
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'lost');self.assertEqual(len(self.client.posts),1)
    async def test_failed_backend_is_saved(self):
        j=self.job();await self.manager.tick()
        self.client.history[j['id']]={'status':{'status_str':'error','messages':[['execution_error',{'exception_message':'OOM'}]]}}
        await self.manager.tick();self.assertEqual(self.store.get(j['id'])['status'],'failed')
    async def test_progress_and_stage_timing(self):
        j=self.job();await self.manager.tick()
        self.manager.event({'type':'executing','data':{'prompt_id':j['id'],'node':'7'}})
        self.manager.event({'type':'progress','data':{'prompt_id':j['id'],'value':3,'max':20}})
        self.assertEqual(self.store.get(j['id'])['progress']['value'],3)
        self.manager.event({'type':'executing','data':{'prompt_id':j['id'],'node':'8'}})
        self.assertIn('node_7_seconds',self.store.get(j['id'])['timings'])


if __name__=='__main__':unittest.main()
