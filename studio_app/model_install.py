"""Standard-library model installer; independent of ComfyUI, torch and app packages."""
import argparse
import contextlib
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'runtime/models.json'
CHUNK = 4 * 1024 * 1024


def manifest(path=MANIFEST):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or not data.get('models'):
        raise ValueError('Unsupported model manifest / 不支持的模型清单')
    paths = set()
    for item in data['models']:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or '\\' in item['path'] or ':' in item['path']:
            raise ValueError('Invalid model path / 模型路径无效')
        if item['path'] in paths:
            raise ValueError('Duplicate model path / 模型路径重复')
        paths.add(item['path'])
        if not re.fullmatch(r'[0-9a-f]{64}', item['sha256']) or not re.fullmatch(r'[0-9a-f]{40}', item['revision']):
            raise ValueError('Invalid pinned revision/hash / 固定版本或校验值无效')
        if type(item['bytes']) is not int or item['bytes'] <= 0:
            raise ValueError('Invalid model size / 模型大小无效')
    return data


def destination(root, item):
    root = Path(root).resolve()
    target = root / item['path']
    if not target.resolve().is_relative_to(root):
        raise ValueError('Model path escapes destination / 模型路径超出目标目录')
    return target


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as file:
        while chunk := file.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def valid(path, item):
    return path.is_file() and path.stat().st_size == item['bytes'] and sha256(path) == item['sha256']


def model_url(item):
    return f"https://huggingface.co/{item['repo']}/resolve/{item['revision']}/{item['filename']}"


@contextlib.contextmanager
def download_lock(path):
    """OS-owned lock; automatically released on interruption, including Windows."""
    with path.open('a+b') as file:
        file.seek(0, 2)
        if file.tell() == 0:
            file.write(b'0'); file.flush()
        file.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Download already running / 此模型已有下载进程') from exc
            try:
                yield
            finally:
                file.seek(0); msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Download already running / 此模型已有下载进程') from exc
            try:
                yield
            finally:
                fcntl.flock(file, fcntl.LOCK_UN)


def download(item, root, replace_invalid=False, opener=urllib.request.urlopen, retries=3):
    target = destination(root, item)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.' + item['sha256'][:12] + '.part')
    with download_lock(target.with_name(target.name + '.download.lock')):
        if valid(target, item):
            print('Verified / 已校验：' + item['path'], flush=True)
            return target
        if target.exists() and not replace_invalid:
            raise ValueError('Existing file differs; use --replace-invalid after checking / 已有文件校验不符，请检查后使用 --replace-invalid：' + str(target))
        if partial.exists() and partial.stat().st_size > item['bytes']:
            raise ValueError('Oversized partial; inspect and remove / 临时文件大小异常，请检查后移除：' + str(partial))
        offset = partial.stat().st_size if partial.exists() else 0
        if shutil.disk_usage(target.parent).free < item['bytes'] - offset + 64 * 1024**2:
            raise OSError('Insufficient disk space / 磁盘空间不足：' + str(target.parent))
        for attempt in range(retries):
            offset = partial.stat().st_size if partial.exists() else 0
            if offset == item['bytes']:
                break
            headers = {'User-Agent': 'Orion-Image-Workbench-model-installer/1', 'Accept-Encoding': 'identity'}
            if offset:
                headers['Range'] = f'bytes={offset}-'
            request = urllib.request.Request(model_url(item), headers=headers)
            try:
                with opener(request, timeout=60) as response:
                    status = response.status
                    mode = 'wb'
                    if status == 206:
                        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                        if not match or int(match[1]) != offset or int(match[3]) != item['bytes'] or int(match[2]) != item['bytes']-1:
                            raise ValueError('Invalid resume response / 断点响应不匹配，未写入')
                        mode = 'ab'
                    elif status == 200:
                        # Server ignored Range: safely restart this partial instead of appending duplicates.
                        offset = 0
                    else:
                        raise ValueError('Unexpected download status / 下载响应异常：' + str(status))
                    length = response.headers.get('Content-Length')
                    if length is not None and int(length) != item['bytes'] - offset:
                        raise ValueError('Download length mismatch / 下载大小与清单不符')
                    last = 0.0
                    with partial.open(mode) as file:
                        while chunk := response.read(CHUNK):
                            if offset + len(chunk) > item['bytes']:
                                raise ValueError('Download exceeds pinned size / 下载内容超过预期大小')
                            file.write(chunk); offset += len(chunk)
                            if time.monotonic() - last >= 2:
                                print(f"{target.name}: {offset / item['bytes']:.1%}", flush=True)
                                last = time.monotonic()
                        file.flush(); os.fsync(file.fileno())
                if offset != item['bytes']:
                    raise ConnectionError('Incomplete download / 下载未完成')
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.HTTPException) as exc:
                if isinstance(exc, urllib.error.HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                    raise RuntimeError(f'HTTP {exc.code}; verify source/access. / 请检查下载源与访问权限；临时文件已保留。') from exc
                if attempt + 1 == retries:
                    raise RuntimeError('Download interrupted; rerun to resume / 下载中断，重新执行可续传') from exc
                print(f'Retrying / 重试 {attempt+1}/{retries-1}', flush=True)
                time.sleep(min(2**attempt, 5))
        if not valid(partial, item):
            # Preserve evidence and any pre-existing target. Next run starts a clean download.
            bad = partial.with_name(partial.name + f'.invalid-{time.time_ns()}')
            partial.replace(bad)
            raise ValueError('SHA-256 mismatch; quarantined / SHA-256不匹配，临时文件已隔离：' + str(bad))
        os.replace(partial, target)
        print('Installed and verified / 安装并校验完成：' + item['path'], flush=True)
        return target


def install(data, root, accept_license=False, replace_invalid=False, items=None):
    selected = data['models'] if items is None else items
    print('Model license / 模型许可：' + data['license_url'])
    print('Research/evaluation only; commercial use requires separate permission. / 仅限研究评估；商业使用需另行许可。')
    print(f"Selected files / 所选文件：{sum(i['bytes'] for i in selected)/1e9:.2f} GB")
    print('Destination / 目标目录：' + str(Path(root).resolve()))
    if not accept_license:
        if not sys.stdin.isatty():
            raise ValueError('Read the license, then pass --accept-model-license / 请阅读许可后传入 --accept-model-license')
        if input('Download under these terms? / 阅读并同意上述条款后下载？ [y/N] ').strip().lower() not in ('y', 'yes'):
            raise ValueError('Download cancelled / 已取消下载')
    for item in selected:
        download(item, root, replace_invalid=replace_invalid)


def ensure_startup_models(root, configured):
    """Quick local startup check. Never switch a custom model to this profile silently."""
    missing = [(folder, name) for folder, name in configured.items() if not (Path(root)/folder/name).is_file()]
    if not missing:
        return
    data = manifest()
    known = {i['path']: i for i in data['models']}
    keys = [f'{folder}/{name}' for folder, name in missing]
    if any(key not in known for key in keys):
        raise RuntimeError('缺少自定义模型，请自行安装；不会替换模型配置：' + ', '.join(keys))
    if not sys.stdin.isatty():
        raise RuntimeError('缺少模型。请运行 python scripts/download_models.py；自动化安装可在阅读许可后加 --accept-model-license。')
    install(data, root, items=[known[key] for key in keys])


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download pinned model files / 下载固定版本模型（Python标准库，无额外依赖）')
    parser.add_argument('--models-dir', type=Path, default=ROOT/'ComfyUI/models')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--list', action='store_true', help='Show sizes/URLs; no downloads / 查看清单，不下载')
    actions.add_argument('--check', action='store_true', help='Check every SHA-256; no downloads / 完整校验，不下载')
    parser.add_argument('--accept-model-license', action='store_true', help='Confirm you reviewed and accepted the linked model license / 已阅读并接受模型许可')
    parser.add_argument('--replace-invalid', action='store_true', help='Replace mismatched target only after a verified download / 新文件校验通过后才替换异常文件')
    args = parser.parse_args(argv)
    try:
        data = manifest()
        if args.list:
            for item in data['models']:
                print(f"{item['path']}  {item['bytes']/1e9:.2f} GB\n  {model_url(item)}\n  SHA-256: {item['sha256']}")
            print(f"Total / 合计：{sum(i['bytes'] for i in data['models'])/1e9:.2f} GB")
            print('License / 许可：' + data['license_url'])
            return 0
        if args.check:
            statuses = []
            for item in data['models']:
                good = valid(destination(args.models_dir, item), item)
                statuses.append(good)
                print(('OK / 正常：' if good else 'MISSING OR INVALID / 缺失或异常：') + item['path'], flush=True)
            return 0 if all(statuses) else 1
        install(data, args.models_dir, args.accept_model_license, args.replace_invalid)
        return 0
    except (OSError, ValueError, RuntimeError, EOFError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nInterrupted; rerun to resume / 已中断，重新执行可续传', file=sys.stderr)
        return 130
