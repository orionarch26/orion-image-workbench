import json
import math
import secrets
from .config import ROOT, MODELS, GENERATION as G

PRO_OPTIONS = {
    'sampler': ['euler', 'heun', 'dpmpp_2m'],
    'scheduler': ['simple', 'normal', 'beta', 'karras'],
    'cache_device': ['auto', 'cpu', 'gpu', 'off'],
    'cache_dtype': ['auto', 'default', 'int8', 'int4'],
    'tile_size': [256, 512, 768],
}
PRO_DEFAULTS = {'negative_prompt':'', 'cfg':1.0, 'sampler':'euler', 'scheduler':'simple',
                'cache_device':'auto', 'cache_dtype':'auto', 'tile_size':512}


def integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f'{name}必须是整数')
    return value


def reference_size(width, height, resolution):
    ratio = width / height
    if not 1 / G['max_aspect_ratio'] <= ratio <= G['max_aspect_ratio']:
        raise ValueError('参考图比例需在1:4至4:1之间，请先裁剪或填充画布')
    w = max(32, round(math.sqrt(resolution * resolution * ratio) / 32) * 32)
    h = max(32, round(math.sqrt(resolution * resolution / ratio) / 32) * 32)
    if max(w, h) > G['max_side'] or w * h > G['max_pixels']:
        raise ValueError(f'改图实际尺寸为{w}×{h}，超过本机设置；请降低参考大小')
    return w, h


def normalize(payload):
    if not isinstance(payload, dict):
        raise ValueError('参数必须为JSON对象')
    allowed = {'prompt','mode','preset','width','height','seed','steps','images','resolution',*PRO_DEFAULTS}
    if set(payload) - allowed:
        raise ValueError('含有未知生成参数')
    p = dict(prompt='', mode='text', preset='standard', width=1024, height=1024,
             seed=-1, steps=None, images=[], resolution=768) | payload
    if not isinstance(p['prompt'], str) or not 1 <= len(p['prompt'].strip()) <= 6000:
        raise ValueError('请输入1–6000字符的描述')
    p['prompt'] = p['prompt'].strip()
    if p['mode'] not in ('text','edit','transparent') or p['preset'] not in ('preview','standard'):
        raise ValueError('无效的模式或质量设置')
    if not isinstance(p['images'], list) or any(not isinstance(n, str) for n in p['images']):
        raise ValueError('参考图必须是文件名列表')
    if len(p['images']) > G['max_references']:
        raise ValueError('最多使用3张参考图')
    if p['mode'] == 'edit' and not p['images']:
        raise ValueError('改图需要至少一张参考图')
    if p['mode'] == 'text' and p['images']:
        raise ValueError('使用参考图请选择改图或透明模式')
    w, h = integer(p['width'], '宽'), integer(p['height'], '高')
    if any(v < 512 or v > G['max_side'] or v % 32 for v in (w,h)) or w*h > G['max_pixels']:
        raise ValueError('宽高需为512–1536之间的32倍数，总像素不超过160万')
    if integer(p['resolution'], '参考大小') not in G['reference_resolutions']:
        raise ValueError('参考大小只能为512、768、1024')
    if p['steps'] is None:
        p['steps'] = G[p['preset'] + '_steps']
    if not 1 <= integer(p['steps'], '步数') <= 60:
        raise ValueError('步数需为1–60')
    seed = integer(p['seed'], '种子')
    if not -1 <= seed < 2**32:
        raise ValueError('种子需为-1或0–4294967295')
    if seed == -1:
        p['seed'] = secrets.randbelow(2**32)
    # Keep legacy payloads unchanged; normalize advanced settings only when supplied.
    for key, choices in PRO_OPTIONS.items():
        if key in p and (isinstance(p[key],bool) or p[key] not in choices):
            raise ValueError(f'{key}不在支持的选项中')
    if 'tile_size' in p:
        integer(p['tile_size'],'解码分块')
    if 'negative_prompt' in p and (not isinstance(p['negative_prompt'],str) or len(p['negative_prompt'])>6000):
        raise ValueError('负面提示词最多6000字符')
    if 'cfg' in p and (isinstance(p['cfg'],bool) or not isinstance(p['cfg'],(int,float)) or not math.isfinite(p['cfg']) or not 1<=p['cfg']<=6):
        raise ValueError('CFG需为1–6的有限数值，推荐1')
    return p


def build_workflow(prompt, **kwargs):
    p = normalize(dict(prompt=prompt, **kwargs))
    wf = json.loads((ROOT / 'workflow_qwen21_t2i.json').read_text())
    wf['1']['inputs']['unet_name'] = MODELS['diffusion_models']
    wf['3']['inputs']['clip_name'] = MODELS['text_encoders']
    wf['4']['inputs']['vae_name'] = MODELS['vae']
    text = p['prompt']
    if p['mode'] == 'transparent':
        text = 'This is an RGBA image with transparency. ' + text + ' The image has alpha channel and the background is transparent.'
    wf['5']['inputs'].update(prompt=text, negative_prompt=p.get('negative_prompt',''), resolution=p['resolution'])
    wf['6']['inputs'].update(width=p['width'], height=p['height'])
    wf['7']['inputs'].update(seed=p['seed'], steps=p['steps'], cfg=p.get('cfg',1.0),
                            sampler_name=p.get('sampler','euler'), scheduler=p.get('scheduler','simple'))
    wf['8']['inputs']['tile_size']=p.get('tile_size',512)
    wf['2']['inputs']['device']=p.get('cache_device','auto')
    wf['9']['inputs']['filename_prefix'] = 'studio/' + p['mode']
    if p['images']:
        wf['5']['inputs']['vae'] = ['4',0]
        for i, name in enumerate(p['images'],1):
            loader, join = str(20+i*2), str(21+i*2)
            wf[loader] = {'class_type':'LoadImage','inputs':{'image':name}}
            wf[join] = {'class_type':'JoinImageWithAlpha','inputs':{'image':[loader,0],'alpha':[loader,1]}}
            wf['5']['inputs'][f'images.image_{i}'] = [join,0]
        wf['7']['inputs']['latent_image'] = ['5',2]
        del wf['6']
        wf['2']['inputs']['dtype'] = 'int8'
    if p.get('cache_dtype','auto')!='auto':
        wf['2']['inputs']['dtype']=p['cache_dtype']
    return wf


def payload_from_workflow(wf):
    """Import the old studio's parameter records, without changing their workflow."""
    p = {'prompt':wf['5']['inputs']['prompt'], 'mode':'text', 'preset':'standard',
         'seed':wf['7']['inputs']['seed'], 'steps':wf['7']['inputs']['steps'],
         'width':wf.get('6',{}).get('inputs',{}).get('width',1024),
         'height':wf.get('6',{}).get('inputs',{}).get('height',1024),
         'resolution':wf['5']['inputs'].get('resolution',768), 'images':[]}
    for name, link in sorted(wf['5']['inputs'].items()):
        if name.startswith('images.image_'):
            node = wf[link[0]]
            if node['class_type'] == 'JoinImageWithAlpha':
                node = wf[node['inputs']['image'][0]]
            p['images'].append(node['inputs']['image'])
    if p['images']:
        p['mode'] = 'edit'
    prefix = 'This is an RGBA image with transparency. '
    suffix = ' The image has alpha channel and the background is transparent.'
    if p['prompt'].startswith(prefix):
        p['mode'] = 'transparent'
        p['prompt'] = p['prompt'].removeprefix(prefix).removesuffix(suffix)
    p['preset'] = 'preview' if p['steps'] == G['preview_steps'] else 'standard'
    p.update(negative_prompt=wf['5']['inputs'].get('negative_prompt',''),cfg=wf['7']['inputs'].get('cfg',1.0),
             sampler=wf['7']['inputs'].get('sampler_name','euler'),scheduler=wf['7']['inputs'].get('scheduler','simple'),
             cache_device=wf['2']['inputs'].get('device','auto'),cache_dtype=wf['2']['inputs'].get('dtype','default'),
             tile_size=wf['8']['inputs'].get('tile_size',512))
    return p
