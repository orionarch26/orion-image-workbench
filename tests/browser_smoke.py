"""Real browser + real model test. Run explicitly against an idle studio."""
import json
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL=os.environ.get('STUDIO_TEST_URL','http://127.0.0.1:7860')


def main():
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=['--disable-gpu'])
        page=browser.new_page(locale="zh-CN",viewport={'width':1440,'height':1100})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(URL)
        page.wait_for_function("document.querySelector('#health').textContent.includes('已连接')")
        page.locator('[data-example="edit"]').click()
        page.locator('#images').set_input_files(ROOT/'examples/input_cat.png')
        page.wait_for_function("document.querySelector('#status').textContent.includes('参考图已准备好')")
        page.locator('details').click()
        page.locator('#seed').fill('77601')
        with page.expect_response('**/api/generate') as response:
            page.locator('#generate').click()
        assert response.value.status==200,response.value.text()
        job_id=response.value.json()['id']
        (ROOT/'docs/smoke-active.json').write_text(json.dumps({'job_id':job_id,'url':URL}))
        print('Real edit job: '+job_id,flush=True)
        page.reload()
        page.wait_for_function("document.querySelector('#mode').value === 'edit'")
        assert '已恢复' not in page.locator('#refs').inner_text() or page.locator('#refs').inner_text()
        deadline=time.monotonic()+1200
        reconnects=0
        while time.monotonic()<deadline:
            try:
                response=page.request.get(URL+'/api/jobs/'+job_id,timeout=5000)
                if not response.ok:raise RuntimeError(response.status)
                job=response.json()
            except Exception:
                reconnects+=1;page.wait_for_timeout(1000);continue
            if job['status'] in ['failed','lost','submission_unknown','timed_out']:
                raise AssertionError(job)
            if job['status']=='done':break
            page.wait_for_timeout(1500)
        else:raise TimeoutError(job_id)
        page.wait_for_function("document.querySelector('#status').textContent.includes('已完成')")
        with page.expect_download() as download:page.get_by_text('下载 PNG',exact=True).click()
        assert download.value.failure() is None
        assert page.locator('#preview img').evaluate('im=>im.naturalWidth')==768
        page.screenshot(path=str(ROOT/'docs/studio-v2-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(ROOT/'docs/studio-v2-mobile.png'),full_page=True)
        page.goto(URL+'/help');assert '使用指南' in page.title()
        assert not errors,errors
        (ROOT/'docs/optimization-browser-test.json').write_text(json.dumps({'job':job,'reconnect_observations':reconnects,'page_errors':errors,'checks':['reference upload','actual edit generation','page reload','PNG download','desktop','mobile','in-app guide']},ensure_ascii=False,indent=2))
        print(json.dumps({'files':job['result']['files'],'seconds':job['result']['seconds'],'timings':job['result']['timings'],'reconnects':reconnects},ensure_ascii=False),flush=True)
        browser.close()


if __name__=='__main__':main()
