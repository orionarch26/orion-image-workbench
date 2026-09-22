"""Stable error descriptors alongside unchanged legacy error text."""
import json
import re
from .config import ROOT

CATALOG = json.loads((ROOT/'locales/zh-CN.json').read_text())
KEYS = json.loads((ROOT/'locales/server-keys.json').read_text())
RULES = [(key, re.compile('^' + r'([\s\S]*?)'.join(re.escape(part) for part in re.split(r'\{\w+\}', CATALOG[key])) + '$'),
          re.findall(r'\{(\w+)\}', CATALOG[key])) for key in KEYS]


def error_payload(error):
    text = str(error)
    for key, pattern, names in RULES:
        match = pattern.fullmatch(text)
        if match:
            return {'error': text, 'error_key': key, 'error_params': dict(zip(names, match.groups()))}
    return {'error': text, 'error_key': None, 'error_params': {}}
