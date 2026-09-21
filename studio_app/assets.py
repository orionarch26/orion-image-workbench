import hashlib
import io
import json
from pathlib import Path
from PIL import Image, ImageOps
from .config import ROOT, STATE, OUTPUT
from .files import atomic_bytes, atomic_json, file_lock
from .workflow import reference_size


class Assets:
    def __init__(self,state=STATE,output=OUTPUT,input_dir=None):
        self.state=Path(state)
        self.output=Path(output)
        self.input=Path(input_dir or ROOT/'ComfyUI/input')
        self.registry=self.state/'references.json'

    def add(self,data):
        if len(data)>20*1024**2:
            raise ValueError('单张参考图不能超过20MB')
        with Image.open(io.BytesIO(data)) as source:
            if source.width*source.height>25_000_000:
                raise ValueError('参考图不能超过2500万像素')
            im=ImageOps.exif_transpose(source).convert('RGBA')
            reference_size(im.width,im.height,512)
            im.thumbnail((2048,2048),Image.Resampling.LANCZOS)
            buf=io.BytesIO()
            im.save(buf,format='PNG')
        blob=buf.getvalue()
        digest=hashlib.sha256(blob).hexdigest()
        name='studio_'+digest+'.png'
        with file_lock(self.state/'references.lock',blocking=True):
            entries=json.loads(self.registry.read_text()) if self.registry.exists() else {}
            destination=self.input/name
            if not destination.exists():
                atomic_bytes(destination,blob)
            record={'name':name,'width':im.width,'height':im.height,'sha256':digest}
            entries[name]=record
            atomic_json(self.registry,entries)
        return record

    def describe(self,name):
        if not isinstance(name,str) or Path(name).name != name or not name.startswith('studio_') or not name.endswith('.png'):
            raise ValueError('参考图名称无效，请重新上传')
        path=self.input/name
        if not path.is_file() or not path.resolve().is_relative_to(self.input.resolve()):
            raise ValueError('参考图已不存在，请重新上传')
        with Image.open(path) as im:
            return {'name':name,'width':im.width,'height':im.height}

    def validate(self,payload):
        size=(payload['width'],payload['height'])
        for i,name in enumerate(payload['images']):
            im=self.describe(name)
            calculated=reference_size(im['width'],im['height'],payload['resolution'])
            if i==0:
                size=calculated
        return list(size)

    def thumbnail(self,name):
        if Path(name).name != name or not name.endswith('.png'):
            raise ValueError('图片名称无效')
        src=self.output/name
        if not src.is_file() or not src.resolve().is_relative_to(self.output.resolve()):
            raise FileNotFoundError(name)
        st=src.stat()
        key=hashlib.sha256(f'{name}:{st.st_mtime_ns}:{st.st_size}'.encode()).hexdigest()
        dst=self.state/'thumbnails'/f'{key}.webp'
        if not dst.exists():
            with Image.open(src) as im:
                im.thumbnail((320,320),Image.Resampling.LANCZOS)
                buf=io.BytesIO()
                im.save(buf,format='WEBP',quality=82)
            atomic_bytes(dst,buf.getvalue())
        return dst
