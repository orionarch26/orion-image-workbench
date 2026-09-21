import json
import tempfile
import unittest
from pathlib import Path
from studio_app.assets import Assets
from studio_app.pro import preview, save_preset
from studio_app.workflow import build_workflow, normalize, payload_from_workflow


class WorkflowTests(unittest.TestCase):
    def test_advanced_parameters_reach_nodes_and_roundtrip(self):
        wf=build_workflow('cat',negative_prompt='letters',cfg=1.5,steps=24,sampler='heun',scheduler='beta',cache_device='cpu',cache_dtype='int8',tile_size=256,seed=52)
        self.assertEqual(wf['5']['inputs']['negative_prompt'],'letters')
        self.assertEqual(wf['7']['inputs']['cfg'],1.5)
        self.assertEqual(wf['7']['inputs']['sampler_name'],'heun')
        self.assertEqual(wf['2']['inputs']['device'],'cpu')
        self.assertEqual(wf['8']['inputs']['tile_size'],256)
        self.assertEqual(build_workflow(**payload_from_workflow(wf)),wf)
    def test_edit_keeps_native_latent_and_explicit_cache(self):
        wf=build_workflow('edit',mode='edit',images=['a.png'],cache_dtype='default')
        self.assertEqual(wf['7']['inputs']['latent_image'],['5',2])
        self.assertEqual(wf['7']['inputs']['denoise'],1)
        self.assertEqual(wf['2']['inputs']['dtype'],'default')
        self.assertEqual(build_workflow('edit',mode='edit',images=['a.png'])['2']['inputs']['dtype'],'int8')
    def test_invalid_advanced_settings_rejected(self):
        for settings in ({'cfg':float('nan')},{'cfg':float('inf')},{'cfg':True},{'cfg':7},{'cfg':'2'},{'sampler':'unknown'},{'scheduler':{}},{'tile_size':256.0},{'cache_dtype':'bf16'},{'negative_prompt':[]},{'negative_prompt':'x'*6001}):
            with self.subTest(settings=settings),self.assertRaises(ValueError):normalize({'prompt':'cat',**settings})
    def test_preset_keeps_random_seed_and_saves_atomically(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'presets.json'
            first=save_preset(path,{'name':'My recipe','parameters':{'prompt':'cat','seed':-1,'cfg':1.2}})
            second=save_preset(path,{'name':'My recipe','parameters':{'prompt':'dog','seed':-1,'cfg':1.2}})
            self.assertEqual(first['id'],second['id']);self.assertEqual(second['parameters']['seed'],-1)
            self.assertEqual(len(json.loads(path.read_text())),1)
            self.assertEqual(second['revision'],2)
            self.assertEqual(second['history'][0]['parameters']['prompt'],'cat')
    def test_preview_reports_ineffective_negative_and_does_not_queue(self):
        result=preview({'prompt':'cat','cfg':1,'negative_prompt':'letters'},Assets())
        self.assertEqual(result['actual_size'],[1024,1024])
        self.assertIn('CFG=1',result['warnings'][0])
