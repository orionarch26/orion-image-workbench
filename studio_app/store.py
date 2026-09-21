import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

TERMINAL={'done','failed','cancelled','timed_out','submission_unknown','lost'}
ACTIVE={'queued','submitting','backend_queued','running','reconnecting','downloading','cancelling'}


class CapacityError(ValueError):
    pass


class ConflictError(ValueError):
    pass


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
            status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, data TEXT NOT NULL)''')
        self.db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL, created REAL NOT NULL, data TEXT NOT NULL)')
        self.db.commit()

    def close(self):
        self.db.close()

    def get(self,job_id):
        row=self.db.execute('SELECT data FROM jobs WHERE id=?',(job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def by_key(self,key):
        row=self.db.execute('SELECT data FROM jobs WHERE request_key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def create(self,key,raw_payload,payload,workflow,limit=5):
        fp=fingerprint(raw_payload)
        try:
            self.db.execute('BEGIN IMMEDIATE')
            existing=self.by_key(key)
            if existing:
                if existing['fingerprint']!=fp:
                    raise ConflictError('同一请求ID对应了不同参数，请发起新任务')
                self.db.commit()
                return existing
            marks=','.join('?' for _ in ACTIVE)
            count=self.db.execute(f'SELECT count(*) FROM jobs WHERE status IN ({marks})',tuple(ACTIVE)).fetchone()[0]
            if count>=limit:
                raise CapacityError(f'已有{limit}个活动任务，请等待完成再提交')
            now=time.time();job_id=str(uuid.uuid4())
            data={'id':job_id,'prompt_id':job_id,'request_key':key,'fingerprint':fp,'status':'queued',
                  'created':now,'updated':now,'payload':payload,'workflow':workflow,'submitted_at':None,
                  'result':None,'error':None,'cancel_requested':False,'progress':{},'observed':False,
                  'deadline':None,'outputs':None,'timings':{}}
            self._insert(data)
            self.db.commit()
            return data
        except BaseException:
            self.db.rollback()
            raise

    def batch_by_key(self, key, raw):
        row=self.db.execute('SELECT data,fingerprint FROM batches WHERE request_key=?',(key,)).fetchone()
        if not row: return None
        if row[1]!=fingerprint(raw): raise ConflictError('同一批次请求ID对应了不同参数')
        return json.loads(row[0])

    def create_batch(self, key, raw, prepared, limit):
        try:
            self.db.execute('BEGIN IMMEDIATE')
            existing=self.batch_by_key(key,raw)
            if existing:
                self.db.commit()
                return existing
            marks=','.join('?' for _ in ACTIVE)
            count=self.db.execute(f'SELECT count(*) FROM jobs WHERE status IN ({marks})',tuple(ACTIVE)).fetchone()[0]
            if count+len(prepared)>limit:
                raise CapacityError(f'队列还可容纳{max(0,limit-count)}张，本批需要{len(prepared)}张；请减少数量或等待。未提交任何图片。')
            now=time.time(); batch_id=str(uuid.uuid4()); ids=[]
            for index,item in enumerate(prepared):
                job_id=str(uuid.uuid4()); ids.append(job_id)
                data={'id':job_id,'prompt_id':job_id,'request_key':f'{key}:{index}',
                      'fingerprint':fingerprint(item['payload']),'status':'queued','created':now+index*0.00001,
                      'updated':now,'payload':item['payload'],'workflow':item['workflow'],
                      'actual_size':item['actual_size'],'submitted_at':None,'result':None,'error':None,
                      'cancel_requested':False,'progress':{},'observed':False,'deadline':None,'outputs':None,'timings':{},
                      'batch':{'id':batch_id,'index':index+1,'total':len(prepared),'label':item['label'],'kind':raw.get('kind','seeds')}}
                self._insert(data)
            batch={'id':batch_id,'created':now,'kind':raw.get('kind','seeds'),'job_ids':ids}
            self.db.execute('INSERT INTO batches VALUES (?,?,?,?,?)',(batch_id,key,fingerprint(raw),now,json.dumps(batch)))
            self.db.commit()
            return batch
        except BaseException:
            self.db.rollback()
            raise

    def batches(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM batches ORDER BY created DESC LIMIT 20')]

    @staticmethod
    def summary(job):
        return {k:job.get(k) for k in ('id','status','updated','payload','progress','batch','error','queue_position')}

    def _insert(self,data):
        self.db.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                        (data['id'],data['request_key'],data['fingerprint'],data['status'],data['created'],data['updated'],json.dumps(data,ensure_ascii=False)))

    def update(self,job_id,**changes):
        data=self.get(job_id)
        if data is None:
            raise KeyError(job_id)
        data.update(changes,updated=time.time())
        self.db.execute('UPDATE jobs SET status=?,updated=?,data=? WHERE id=?',
                        (data['status'],data['updated'],json.dumps(data,ensure_ascii=False),job_id))
        self.db.commit()
        return data

    def list(self,statuses=None,limit=50,offset=0):
        if statuses:
            marks=','.join('?' for _ in statuses)
            rows=self.db.execute(f'SELECT data FROM jobs WHERE status IN ({marks}) ORDER BY created ASC LIMIT ? OFFSET ?',
                                 (*statuses,limit,offset))
        else:
            rows=self.db.execute('SELECT data FROM jobs ORDER BY created DESC LIMIT ? OFFSET ?',(limit,offset))
        return [json.loads(row[0]) for row in rows]

    def import_completed(self,output_dir):
        from .workflow import payload_from_workflow
        for file in Path(output_dir).glob('*.json'):
            try:
                old=json.loads(file.read_text())
                job_id=old['prompt_id']
                if self.get(job_id) or old.get('status')!='done' or not old.get('files'):
                    continue
                payload=old.get('payload') or payload_from_workflow(old['workflow'])
                data={'id':job_id,'prompt_id':job_id,'request_key':'import-'+job_id,'fingerprint':fingerprint(payload),
                      'status':'done','created':file.stat().st_mtime,'updated':file.stat().st_mtime,
                      'payload':payload,'workflow':old['workflow'],'result':old,'error':None,
                      'submitted_at':None,'cancel_requested':False,'progress':{},'observed':True,
                      'deadline':None,'outputs':None,'timings':old.get('timings',{})}
                self._insert(data)
                self.db.commit()
            except (ValueError,KeyError,TypeError,OSError):
                continue
