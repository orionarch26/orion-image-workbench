"""Professional workbench helpers. Preview compiles the same graph used for generation."""
import json
import uuid
import time
from .files import atomic_json, file_lock
from .workflow import normalize, build_workflow, PRO_DEFAULTS, PRO_OPTIONS
from .config import MODELS


def preview(raw, assets):
    p=normalize(raw)
    size=assets.validate(p)
    graph=build_workflow(**p)
    warnings=[]
    if p.get('cfg',1)==1 and p.get('negative_prompt'):
        warnings.append('CFG=1时采样不使用负条件；负面提示词不会产生预期引导。')
    if p.get('cfg',1)>1:
        warnings.append('CFG>1会增加条件计算开销，可能改变色彩和质感；本模型建议从1开始。')
    if p.get('sampler','euler')!='euler' or p.get('scheduler','simple')!='simple':
        warnings.append('当前采样组合属于实验设置；固定种子，与Euler/simple结果比较后再采用。')
    if graph['2']['inputs']['dtype']=='int4':
        warnings.append('int4缓存会引入更多量化误差，不代表质量更高。')
    if p.get('cache_device') in ('off','gpu'):
        warnings.append('关闭缓存通常更慢；强制GPU缓存可能增加显存压力。')
    if len(p['images'])>1:
        warnings.append('多图会增加资源需求；8GB机器建议从512参考大小开始。')
    return {'payload':p,'actual_size':size,'workflow':graph,'warnings':warnings,
            'models':MODELS,'options':PRO_OPTIONS,'defaults':PRO_DEFAULTS}


def save_preset(path, data):
    if not isinstance(data,dict) or set(data)-{'name','parameters'}:
        raise ValueError('预设需要name和parameters')
    name=data.get('name','')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:
        raise ValueError('预设名称需为1–80字符')
    raw=data.get('parameters');p=normalize(raw)
    p['seed']=raw.get('seed',-1)  # A random-seed recipe remains random after saving.
    with file_lock(path.with_suffix('.lock'),blocking=True):
        rows=json.loads(path.read_text()) if path.exists() else []
        old=next((r for r in rows if r['name']==name.strip()),None)
        if not old and len(rows)>=50: raise ValueError('最多保存50个预设')
        history=(old.get('history',[])+[{'parameters':old['parameters'],'revision':old.get('revision',1),'saved_at':old.get('saved_at')}])[-10:] if old else []
        item={'id':old['id'] if old else str(uuid.uuid4()),'name':name.strip(),'parameters':p,
              'revision':old.get('revision',1)+1 if old else 1,'history':history,'saved_at':time.time()}
        rows=[item if r['id']==item['id'] else r for r in rows] if old else rows+[item]
        atomic_json(path,rows)
    return item
