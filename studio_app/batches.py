"""Freeze reproducible batches before placing them in the single backend queue."""
from .workflow import normalize, build_workflow

AXES = {'steps', 'cfg', 'sampler', 'scheduler', 'cache_dtype', 'tile_size'}


def prepare(raw, assets, limit):
    if not isinstance(raw, dict) or set(raw)-{'parameters','kind','count','axis','values'}:
        raise ValueError('批次参数格式错误')
    kind = raw.get('kind', 'seeds')
    baseline = normalize(raw.get('parameters'))
    if kind == 'seeds':
        count = raw.get('count', 3)
        if type(count) is not int or not 2 <= count <= limit:
            raise ValueError(f'每批需要2–{limit}张图片')
        variants = [{**baseline, 'seed': (baseline['seed']+i) % (2**32)} for i in range(count)]
        labels = [f'种子 {p["seed"]}' for p in variants]
    elif kind == 'experiment':
        axis, values = raw.get('axis'), raw.get('values')
        if axis not in AXES or not isinstance(values, list) or not 2 <= len(values) <= limit:
            raise ValueError(f'请选择支持的单变量，并提供2–{limit}个值')
        variants = [normalize({**baseline, axis: value}) for value in values]
        if len({str(p[axis]) for p in variants}) != len(variants):
            raise ValueError('实验值不能重复')
        labels = [f'{axis} = {p[axis]}' for p in variants]
    else:
        raise ValueError('未知批次类型')
    return [{'payload': p, 'workflow': build_workflow(**p), 'actual_size': assets.validate(p),
             'label': label} for p, label in zip(variants, labels)]
