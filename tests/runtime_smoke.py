"""Real GPU validation: scoped cancellation, transparent output, CLI resume, browser help."""
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_app.config import EXAMPLES


def main():
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def api(path,data=None,backend=False):
        url=('http://127.0.0.1:8188' if backend else 'http://127.0.0.1:7860')+path
        headers={'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())}
        req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        with opener.open(req,timeout=25) as response:return json.load(response)
    def wait_job(job_id,predicate,seconds=240):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            job=api('/api/jobs/'+job_id)
            if predicate(job):return job
            if job['status'] in ('failed','lost','submission_unknown','timed_out'):
                raise AssertionError(job)
            time.sleep(1)
        raise TimeoutError(job_id)

    queue=api('/queue',backend=True)
    assert not queue['queue_running'] and not queue['queue_pending'],'Run only with an idle backend'
    main_job=api('/api/generate',{'prompt':EXAMPLES['sticker'],'mode':'transparent','seed':932706,'preset':'standard'})
    wait_job(main_job['id'],lambda j:j['status']=='running')
    cancelled=api('/api/generate',{'prompt':'A red cube on a white table','seed':932707,'preset':'preview'})
    wait_job(cancelled['id'],lambda j:j['status']=='backend_queued')
    api('/api/jobs/'+cancelled['id']+'/cancel',{})
    cancelled=wait_job(cancelled['id'],lambda j:j['status']=='cancelled',90)
    done=wait_job(main_job['id'],lambda j:j['status']=='done')
    image_path=ROOT/'output'/done['result']['files'][0]
    with Image.open(image_path) as im:
        assert im.size==(1024,1024) and im.mode=='RGBA'
        alpha=im.getchannel('A').getextrema()
        assert alpha[0]<255 and alpha[1]>0
    print('Scoped cancellation and transparent PNG PASS',flush=True)

    before=set(api('/history',backend=True))
    with tempfile.TemporaryDirectory() as directory:
        result=subprocess.run([sys.executable,str(ROOT/'run_inference.py'),str(ROOT/'output'/(done['id']+'.json')),directory,'--resume'],cwd=ROOT,capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stderr
        assert list(Path(directory).glob('*.png'))
    assert set(api('/history',backend=True))==before,'Resume must not create a new backend job'

    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--disable-gpu'])
        page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:7860/')
        page.wait_for_function("document.querySelector('#health').textContent.includes('已连接')")
        assert not page.locator('#retry').is_visible()
        page.locator('#gallery button').filter(has=page.get_by_alt_text(EXAMPLES['sticker'],exact=True)).first.click()
        page.get_by_text('用此作品参数生成标准版',exact=True).wait_for()
        page.screenshot(path=str(ROOT/'docs/studio-v2-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=str(ROOT/'docs/studio-v2-mobile.png'),full_page=True)
        for route in ('guide','workflow','research','validation'):
            response=page.goto('http://127.0.0.1:7860/help/'+route)
            assert response.status==200,(route,response.status)
        assert not errors,errors
        browser.close()
    report={'main_job':done['id'],'main_status':done['status'],'cancelled_job':cancelled['id'],
            'cancelled_status':cancelled['status'],'file':done['result']['files'][0],
            'alpha_range':alpha,'seconds':done['result']['seconds'],'cli_resume_no_new_job':True,
            'page_errors':errors,'checks':['cancel queued job without interrupting running job','RGBA output','CLI resume without new generation','desktop/mobile','all in-app guide routes']}
    (ROOT/'docs/runtime-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
