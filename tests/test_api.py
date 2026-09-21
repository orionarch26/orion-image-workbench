import asyncio
import tempfile
import unittest
import uuid
from pathlib import Path
from aiohttp.test_utils import TestClient, TestServer
from studio_app.server import create_app, STORE


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.app=create_app(7869,root/'state',root/'output',start_worker=False)
        self.client=TestClient(TestServer(self.app),headers={'Host':'127.0.0.1:7869'})
        await self.client.start_server()
    async def asyncTearDown(self):
        await self.client.close();self.temp.cleanup()
    async def submit(self,key=None,payload=None):
        return await self.client.post('/api/generate',json=payload or {'prompt':'cat'},headers={'Idempotency-Key':key or str(uuid.uuid4())})
    async def test_concurrent_limit_and_retry_when_full(self):
        keys=[str(uuid.uuid4()) for _ in range(8)]
        responses=await asyncio.gather(*(self.submit(k) for k in keys))
        self.assertEqual(sum(r.status==200 for r in responses),5)
        self.assertEqual(sum(r.status==429 for r in responses),3)
        index=next(i for i,r in enumerate(responses) if r.status==200)
        first=await responses[index].json();replay=await self.submit(keys[index]);second=await replay.json()
        self.assertEqual(replay.status,200);self.assertEqual(first['id'],second['id']);self.assertEqual(first['payload']['seed'],second['payload']['seed'])
    async def test_idempotency_conflict(self):
        key=str(uuid.uuid4());await self.submit(key)
        response=await self.submit(key,{'prompt':'dog'})
        self.assertEqual(response.status,409)
    async def test_cancelled_queued_job_remains_queryable(self):
        response=await self.submit();job=(await response.json())['id']
        cancelled=await self.client.post('/api/jobs/'+job+'/cancel',json={})
        self.assertEqual((await cancelled.json())['status'],'cancelled')
        query=await self.client.get('/api/jobs/'+job)
        self.assertEqual((await query.json())['status'],'cancelled')
    async def test_origin_and_missing_key(self):
        response=await self.client.post('/api/generate',json={'prompt':'cat'})
        self.assertEqual(response.status,400)
        response=await self.client.post('/api/generate',json={'prompt':'cat'},headers={'Origin':'https://example.com'})
        self.assertEqual(response.status,403)
    async def test_invalid_reference_and_help(self):
        response=await self.submit(payload={'prompt':'edit','mode':'edit','images':['../x.png']})
        self.assertEqual(response.status,400)
        response=await self.client.get('/help')
        self.assertEqual(response.status,200);self.assertIn('text/html',response.headers['Content-Type'])
        self.assertIn('本地画室',await response.text())

    async def test_preview_and_generation_use_identical_graph(self):
        p={'prompt':'cat','seed':42,'steps':24,'cfg':1.3,'sampler':'heun','cache_dtype':'int8'}
        response=await self.client.post('/api/pro/preview',json=p)
        self.assertEqual(response.status,200);graph=(await response.json())['workflow']
        r=await self.submit(payload=p);job_id=(await r.json())['id']
        r=await self.client.get('/api/jobs/'+job_id)
        self.assertEqual((await r.json())['workflow'],graph)
    async def test_pro_page_presets_and_path_guard(self):
        self.assertEqual((await self.client.get('/pro')).status,200)
        r=await self.client.post('/api/pro/presets',json={'name':'Recipe','parameters':{'prompt':'cat','cfg':1.2}})
        self.assertEqual(r.status,200)
        self.assertEqual(len((await (await self.client.get('/api/pro/presets')).json())['items']),1)
        self.assertEqual((await self.client.get('/reference/not-a-reference.png')).status,400)

    async def batch(self, raw=None, key=None):
        return await self.client.post('/api/pro/batches',json=raw or {'parameters':{'prompt':'cat','seed':0},'kind':'seeds','count':3},headers={'Idempotency-Key':key or str(uuid.uuid4())})

    async def test_batch_seeds_replay_conflict_and_summary(self):
        key=str(uuid.uuid4())
        first=await self.batch(key=key);self.assertEqual(first.status,200)
        batch=await first.json();again=await self.batch(key=key)
        self.assertEqual(batch,await again.json())
        jobs=[self.app[STORE].get(i) for i in batch['job_ids']]
        self.assertEqual([j['payload']['seed'] for j in jobs],[0,1,2])
        self.assertEqual([j['batch']['index'] for j in jobs],[1,2,3])
        self.assertEqual(len(self.app[STORE].list()),3)
        conflict=await self.batch({'parameters':{'prompt':'dog'},'count':3},key)
        self.assertEqual(conflict.status,409)
        summary=await (await self.client.get('/api/jobs?summary=1')).json()
        self.assertNotIn('workflow',summary['items'][0])
        self.assertIn('batch',summary['items'][0])
        rows=await (await self.client.get('/api/pro/batches')).json()
        self.assertEqual(len(rows['items'][0]['jobs']),3)

    async def test_batch_capacity_is_atomic_and_replay_works_when_full(self):
        key=str(uuid.uuid4());first=await (await self.batch(key=key)).json()
        blocked=await self.batch()
        self.assertEqual(blocked.status,429)
        self.assertEqual(len(self.app[STORE].list()),3)
        await self.submit();await self.submit()
        self.assertEqual(await (await self.batch(key=key)).json(),first)
        self.assertEqual(len(self.app[STORE].list()),5)

    async def test_batch_experiment_shares_random_seed_and_changes_only_axis(self):
        response=await self.batch({'parameters':{'prompt':'cat','seed':-1},'kind':'experiment','axis':'steps','values':[20,30,40]})
        self.assertEqual(response.status,200)
        jobs=[self.app[STORE].get(i) for i in (await response.json())['job_ids']]
        self.assertEqual(len({j['payload']['seed'] for j in jobs}),1)
        self.assertEqual([j['workflow']['7']['inputs']['steps'] for j in jobs],[20,30,40])
        without_steps=[{k:v for k,v in j['payload'].items() if k!='steps'} for j in jobs]
        self.assertEqual(without_steps[0],without_steps[1]);self.assertEqual(without_steps[1],without_steps[2])

    async def test_batch_invalid_member_rejects_whole_group(self):
        for raw in [
            {'kind':'experiment','axis':'steps','values':[20,99]},
            {'kind':'experiment','axis':'cfg','values':[1,1]},
            {'kind':'experiment','axis':'seed','values':[1,2]},
            {'kind':'seeds','count':True},
            {'kind':'seeds','count':6},
        ]:
            response=await self.batch({'parameters':{'prompt':'cat'},**raw})
            self.assertEqual(response.status,400)
        self.assertEqual(self.app[STORE].list(),[])
        self.assertEqual(self.app[STORE].batches(),[])

    async def test_cancel_batch_preserves_completed_and_unrelated_jobs(self):
        batch=await (await self.batch()).json()
        unrelated=await (await self.submit()).json()
        self.app[STORE].update(batch['job_ids'][0],status='done')
        response=await self.client.post('/api/pro/batches/'+batch['id']+'/cancel',json={})
        self.assertEqual(response.status,200)
        self.assertEqual([self.app[STORE].get(i)['status'] for i in batch['job_ids']],['done','cancelled','cancelled'])
        self.assertEqual(self.app[STORE].get(unrelated['id'])['status'],'queued')

    async def test_concurrent_batches_do_not_partially_fill_queue(self):
        responses=await asyncio.gather(self.batch(),self.batch())
        self.assertEqual(sorted(r.status for r in responses),[200,429])
        self.assertEqual(len(self.app[STORE].list()),3)

    async def test_import_missing_reference_keeps_parameters_but_cannot_generate(self):
        raw={'prompt':'cat','mode':'edit','images':['studio_missing.png'],'seed':-1}
        response=await self.client.post('/api/pro/recipe',json=raw)
        self.assertEqual(response.status,200)
        data=await response.json()
        self.assertEqual(data['missing_references'],raw['images'])
        self.assertEqual(data['parameters']['seed'],-1)
        self.assertEqual((await self.submit(payload=data['parameters'])).status,400)
        self.assertEqual(self.app[STORE].list(),[])
        self.assertEqual((await self.client.post('/api/pro/recipe',json={**raw,'images':['../studio_missing.png']})).status,400)

    async def test_batches_survive_database_reopen(self):
        from studio_app.store import Store
        batch=await (await self.batch()).json()
        reopened=Store(Path(self.temp.name)/'state/jobs.sqlite3')
        try:
            self.assertEqual(reopened.batches()[0],batch)
            self.assertEqual([reopened.get(i)['payload']['seed'] for i in batch['job_ids']],[0,1,2])
        finally: reopened.close()
