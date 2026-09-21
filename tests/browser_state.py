"""Offline browser test: lost submission response and independent draft/result state."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from studio_app.config import ROOT,EXAMPLES,GENERATION
from studio_app.workflow import normalize,build_workflow


def main():
    jobs={};requests=[];drop_first=[True];errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--disable-gpu'])
        page=browser.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        def handle(route):
            req=route.request;path=req.url.split('http://127.0.0.1:7898',1)[-1]
            if path=='/':return route.fulfill(body=(ROOT/'web/index.html').read_bytes(),content_type='text/html')
            if path.startswith('/static/'):
                name=path.rsplit('/',1)[1]
                return route.fulfill(body=(ROOT/'web'/name).read_bytes(),content_type='application/javascript' if name.endswith('.js') else 'text/css')
            if path=='/api/config':return route.fulfill(json={'examples':EXAMPLES,'generation':GENERATION,'backend_ready':True,'queue_limit':5})
            if path.startswith('/api/gallery'):return route.fulfill(json={'items':[],'next':None})
            if path.startswith('/api/jobs?'):return route.fulfill(json={'items':list(jobs.values()),'next':None})
            if path=='/api/generate':
                key=req.headers['idempotency-key'];requests.append({'key':key,'payload':req.post_data_json})
                if key not in jobs:
                    payload=normalize(req.post_data_json)
                    jobs[key]={'id':key,'status':'done','created':1,'payload':payload,'actual_size':[payload['width'],payload['height']],
                        'result':{'prompt_id':key,'files':['fixture.png'],'seconds':1,'workflow':build_workflow(**payload),'timings':{}}}
                if drop_first[0]:drop_first[0]=False;return route.abort('connectionreset')
                return route.fulfill(json={'id':key,'payload':jobs[key]['payload']})
            if path.startswith('/api/jobs/'):return route.fulfill(json=jobs[path.rsplit('/',1)[1]])
            if path.startswith('/output/'):return route.fulfill(body=(ROOT/'examples/input_cat.png').read_bytes(),content_type='image/png')
            return route.fulfill(status=404)
        page.route('http://127.0.0.1:7898/**',handle)
        page.goto('http://127.0.0.1:7898/')
        page.wait_for_function("document.querySelector('#health').textContent.includes('已连接')")
        assert not page.locator('#retry').is_visible()
        assert not page.locator('#more').is_visible()
        page.locator('#prompt').fill('A: orange cat');page.locator('#preset').select_option('preview')
        page.locator('#generate').click();page.locator('#retry').wait_for(state='visible')
        page.locator('#retry').click();page.get_by_text('用此作品参数生成标准版',exact=True).wait_for()
        assert requests[0]['key']==requests[1]['key'] and len(jobs)==1
        assert not page.locator('#retry').is_visible()
        page.locator('#prompt').fill('B: blue bird');page.locator('#mode').select_option('transparent');page.locator('#size').select_option('832,1216')
        page.get_by_text('用此作品参数生成标准版',exact=True).click()
        page.wait_for_function("!document.querySelector('#generate').disabled")
        assert requests[-1]['payload']['prompt']=='A: orange cat'
        assert requests[-1]['payload']['steps']==40
        assert page.locator('#prompt').input_value()=='B: blue bird'
        assert 'A: orange cat' in page.locator('#snapshot').inner_text()
        assert '独立草稿' in page.locator('#snapshot').inner_text()
        page.reload();page.wait_for_function("document.querySelector('#prompt').value === 'B: blue bird'")
        assert page.locator('#mode').input_value()=='transparent'
        assert page.locator('#size').input_value()=='832,1216'
        assert not errors,errors
        (ROOT/'docs/optimization-browser-state.json').write_text(json.dumps({'checks':['lost acknowledgement retries same key','one job per request key','selected result parameters explicit','draft preserved during standard generation','draft survives reload'],'page_errors':errors},indent=2))
        browser.close();print('Browser state tests PASS')


if __name__=='__main__':main()
