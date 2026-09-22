"""Capture a public UI preview using only the bundled fixture and mocked endpoints."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from studio_app.workflow import normalize,build_workflow,PRO_OPTIONS,PRO_DEFAULTS
from studio_app.config import EXAMPLES,GENERATION,MODELS

URL='http://127.0.0.1:7897'
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--disable-gpu'])
    page=browser.new_page(locale="zh-CN",viewport={'width':1600,'height':1050})
    def route(r):
        path=r.request.url.removeprefix(URL)
        if path=='/pro':return r.fulfill(body=(ROOT/'web/pro.html').read_bytes(),content_type='text/html')
        if path.startswith('/static/'):
            p=ROOT/'web'/path.rsplit('/',1)[1]
            return r.fulfill(body=p.read_bytes(),content_type='text/css' if p.suffix=='.css' else 'application/javascript')
        if path=='/api/config':return r.fulfill(json={'examples':EXAMPLES,'generation':GENERATION,'backend_ready':False,'queue_limit':5})
        if path=='/api/pro/preview':
            p=normalize(r.request.post_data_json)
            return r.fulfill(json={'payload':p,'workflow':build_workflow(**p),'actual_size':[768,768],'models':MODELS,'options':PRO_OPTIONS,'defaults':PRO_DEFAULTS,'warnings':[]})
        if path.startswith('/api/'):return r.fulfill(json={'items':[],'next':None})
        if path.startswith('/output/'):return r.fulfill(body=(ROOT/'examples/input_cat.png').read_bytes(),content_type='image/png')
        return r.fulfill(status=404)
    page.route(URL+'/**',route)
    page.goto(URL+'/pro');page.wait_for_function("!document.querySelector('#run').disabled")
    p=normalize({'prompt':EXAMPLES['photo'],'seed':42,'steps':20,'width':768,'height':768})
    job={'id':'public-demo','payload':p,'workflow':build_workflow(**p),'actual_size':[768,768],'result':{'files':['example.png']}}
    page.evaluate('(job)=>{showResult(job);apply(job.payload);document.querySelector("#connection").textContent="演示预览 · 无 GPU";}',job)
    page.wait_for_function('document.querySelector("#canvas img").complete')
    page.wait_for_timeout(500)
    (ROOT/'docs/media').mkdir(exist_ok=True)
    page.screenshot(path=str(ROOT/'docs/media/workbench-demo.png'))
    browser.close()
