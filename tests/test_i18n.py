import json
from pathlib import Path
import re
import unittest
from studio_app.config import ROOT
from studio_app.i18n import error_payload


class LocaleTests(unittest.TestCase):
    def test_catalog_keys_and_placeholders_match(self):
        en = json.loads((ROOT/'locales/en.json').read_text())
        zh = json.loads((ROOT/'locales/zh-CN.json').read_text())
        self.assertEqual(set(en), set(zh))
        for key in en:
            self.assertTrue(en[key], key)
            self.assertEqual(set(re.findall(r'\{\w+\}', en[key])), set(re.findall(r'\{\w+\}', zh[key])), key)
        source = '\n'.join((ROOT/name).read_text() for name in ['web/app.js','web/pro.js','web/index.html','web/pro.html','studio_app/navigation.py'])
        used = set(re.findall(r'I18n.msg\("([^"]+)"', source)) | set(re.findall(r'data-i18n(?:-[\w-]+)?="([\w.]+)"', source))
        self.assertFalse(used-set(en), used-set(en))

    def test_errors_have_stable_keys_without_changing_raw_text(self):
        text='队列还可容纳2张，本批需要3张；请减少数量或等待。未提交任何图片。'
        result=error_payload(text)
        self.assertEqual(result['error'],text)
        self.assertTrue(result['error_key'].startswith('server.'))
        self.assertEqual(result['error_params'],{'p0':'2','p1':'3'})
        self.assertIsNone(error_payload('Unknown provider detail')['error_key'])

    def test_guide_files_exist_for_both_languages(self):
        for name in ['docs/en/guide.md','docs/en/workflow.md','docs/en/workbench.md',
                     'docs/zh-CN/research.md','docs/zh-CN/validation.md']:
            self.assertTrue((ROOT/name).is_file())
