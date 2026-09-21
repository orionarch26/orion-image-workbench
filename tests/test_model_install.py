import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from studio_app import model_install as models


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status=status
        self.headers=headers or {'Content-Length':str(len(data))}


class ModelInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.data=b'fixture-model-contents'
        self.item={'path':'diffusion_models/fixture.gguf','bytes':len(self.data),
                   'sha256':hashlib.sha256(self.data).hexdigest(),'repo':'test/model','revision':'a'*40,'filename':'fixture.gguf'}
    def tearDown(self): self.temp.cleanup()
    def partial(self):
        dest=self.root/self.item['path'];dest.parent.mkdir(parents=True,exist_ok=True)
        return dest.with_name(dest.name+'.'+self.item['sha256'][:12]+'.part')
    def test_verified_target_is_reused_without_network(self):
        dest=self.root/self.item['path'];dest.parent.mkdir();dest.write_bytes(self.data)
        def forbidden(*args,**kwargs):raise AssertionError('Unexpected network')
        self.assertTrue(models.download(self.item,self.root,opener=forbidden).samefile(dest))
    def test_resume_and_atomic_completion(self):
        self.partial().write_bytes(self.data[:5])
        def opener(req,**kwargs):
            self.assertEqual(req.get_header('Range'),'bytes=5-')
            return Response(self.data[5:],206,{'Content-Range':f'bytes 5-{len(self.data)-1}/{len(self.data)}','Content-Length':str(len(self.data)-5)})
        dest=models.download(self.item,self.root,opener=opener)
        self.assertEqual(dest.read_bytes(),self.data);self.assertFalse(self.partial().exists())
    def test_ignored_range_restarts_without_appending(self):
        self.partial().write_bytes(self.data[:4])
        dest=models.download(self.item,self.root,opener=lambda *a,**k:Response(self.data))
        self.assertEqual(dest.read_bytes(),self.data)
    def test_bad_resume_does_not_change_partial(self):
        part=self.partial();part.write_bytes(self.data[:4])
        with self.assertRaises(ValueError):models.download(self.item,self.root,opener=lambda *a,**k:Response(self.data[4:],206,{'Content-Range':'bytes 3-20/21'}))
        self.assertEqual(part.read_bytes(),self.data[:4]);self.assertFalse((self.root/self.item['path']).exists())
    def test_bad_hash_preserves_previous_target(self):
        target=self.root/self.item['path'];target.parent.mkdir();target.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'SHA-256'):
            models.download(self.item,self.root,replace_invalid=True,opener=lambda *a,**k:Response(b'x'*len(self.data)))
        self.assertEqual(target.read_bytes(),b'original')
        self.assertEqual(len(list(target.parent.glob('*.invalid-*'))),1)
    def test_invalid_target_needs_explicit_replacement(self):
        target=self.root/self.item['path'];target.parent.mkdir();target.write_bytes(b'original')
        with self.assertRaisesRegex(ValueError,'replace-invalid'):
            models.download(self.item,self.root,opener=lambda *a,**k:self.fail('network before explicit replacement'))
    def test_noninteractive_requires_license_flag(self):
        with patch('studio_app.model_install.sys.stdin.isatty',return_value=False),patch('studio_app.model_install.download') as download:
            with self.assertRaisesRegex(ValueError,'accept-model-license'):
                models.install({'models':[self.item],'license_url':'https://example.com/license'},self.root)
            download.assert_not_called()
    def test_startup_does_not_substitute_custom_models(self):
        with self.assertRaisesRegex(RuntimeError,'自定义模型'):
            models.ensure_startup_models(self.root,{'diffusion_models':'custom.gguf'})
    def test_manifest_is_pinned_and_target_cannot_escape(self):
        self.assertEqual(len(models.manifest()['models']),3)
        with self.assertRaises(ValueError):models.destination(self.root,{'path':'../escape.gguf'})
    def test_short_read_is_resumed_on_retry(self):
        calls=[]
        def opener(req,**kwargs):
            calls.append(req.get_header('Range'))
            if len(calls)==1:return Response(self.data[:4],headers={'Content-Length':str(len(self.data))})
            return Response(self.data[4:],206,{'Content-Range':f'bytes 4-{len(self.data)-1}/{len(self.data)}'})
        with patch('studio_app.model_install.time.sleep'):
            dest=models.download(self.item,self.root,opener=opener)
        self.assertEqual(calls,[None,'bytes=4-']);self.assertEqual(dest.read_bytes(),self.data)
    def test_destination_with_spaces_and_unicode(self):
        root=self.root/'模型 files'
        target=models.download(self.item,root,opener=lambda *a,**k:Response(self.data))
        self.assertTrue(models.valid(target,self.item))
    def test_download_lock_prevents_competing_writer_and_releases(self):
        path=self.root/'test.lock'
        with models.download_lock(path):
            with self.assertRaises(RuntimeError):
                with models.download_lock(path): pass
        with models.download_lock(path): pass
