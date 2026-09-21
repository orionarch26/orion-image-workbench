"""Check the staged/committed Git tree, not personal untracked working files."""
import fnmatch
from pathlib import PurePosixPath
import re
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    names=[n for n in git('ls-files','-z').decode().split('\0') if n]
    if not names:
        print('Stage the proposed source files before running this check.');return 1
    forbidden_dirs={'ComfyUI','output','state','logs','.backups','.omc','.venv','__pycache__'}
    forbidden_exts={'.gguf','.safetensors','.ckpt','.pt','.pth','.sqlite3','.pyc','.log'}
    secrets=re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
    errors=[];total=0
    for name in names:
        path=PurePosixPath(name)
        if set(path.parts)&forbidden_dirs or path.suffix in forbidden_exts or fnmatch.fnmatch(path.name,'.env*') and path.name!='.env.example':
            errors.append(f'Private/runtime file: {name}');continue
        size=int(git('cat-file','-s',':'+name));total+=size
        if size>10*1024**2:errors.append(f'Oversized source asset: {name}')
        if path.suffix not in ('.png','.webp','.jpg','.jpeg') and size<2*1024**2:
            blob=git('show',':'+name)
            if secrets.search(blob):errors.append(f'Possible credential in {name}')
    print(f'Checked {len(names)} tracked files, {total/1024**2:.2f} MiB')
    for error in errors:print(error,file=sys.stderr)
    return 1 if errors else 0


if __name__=='__main__':raise SystemExit(main())
