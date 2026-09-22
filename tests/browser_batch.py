"""Professional batch UI smoke test; --generate runs a real two-image serial batch."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
URL='http://127.0.0.1:7860'
args=argparse.ArgumentParser();args.add_argument('--generate',action='store_true');args=args.parse_args()
report={'checks':[]}
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--disable-gpu'])
    page=browser.new_page(locale="zh-CN",viewport={'width':1600,'height':1050})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(URL+'/pro')
    page.wait_for_function("!document.querySelector('#run').disabled")
    page.locator('#run-kind').select_option('experiment')
    assert page.locator('#batch-values').input_value()=='20, 30, 40'
    page.locator('#batch-axis').select_option('cfg')
    assert page.locator('#batch-values').input_value()=='1, 1.2, 1.5'
    page.locator('#run-kind').select_option('seeds')
    page.locator('#batch-count').fill('2')
    page.locator('#width').fill('768');page.locator('#height').fill('768')
    page.locator('#steps').fill('20');page.locator('#seed').fill(str(int(time.time()) % (2**32-1)))
    page.wait_for_function("!document.querySelector('#run').disabled")
    page.reload();page.wait_for_function("!document.querySelector('#run').disabled")
    assert page.locator('#run-kind').input_value()=='seeds'
    assert page.locator('#batch-count').input_value()=='2'
    report['checks'].append('batch controls, experiment examples and draft survive refresh')
    if args.generate:
        with page.expect_response(lambda r:r.url.endswith('/api/pro/batches') and r.request.method=='POST') as event:
            page.locator('#run').click()
        response=event.value
        assert response.status==200,response.text()
        batch=response.json();report['batch']=batch
        print('Real batch: '+batch['id'],flush=True)
        page.reload();page.wait_for_function("document.querySelectorAll('.batch-card').length > 0")
        report['checks'].append('accepted group survives page reload')
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            jobs=[page.request.get(URL+'/api/jobs/'+id).json() for id in batch['job_ids']]
            if all(j['status']=='done' for j in jobs):break
            if any(j['status'] in {'failed','cancelled','timed_out','lost','submission_unknown'} for j in jobs):raise AssertionError(jobs)
            page.wait_for_timeout(2500)
        else:raise TimeoutError(batch['id'])
        assert jobs[1]['payload']['seed']==(jobs[0]['payload']['seed']+1) % (2**32)
        hashes=[]
        for j in jobs:
            assert not j['result']['timings']['sampler_cached']
            blob=page.request.get(URL+'/output/'+j['result']['files'][0]).body()
            assert blob.startswith(b'\x89PNG\r\n\x1a\n')
            hashes.append(hashlib.sha256(blob).hexdigest())
        assert hashes[0]!=hashes[1]
        report['jobs']=jobs;report['sha256']=hashes
        report['checks'].append('two uncached GPU outputs with consecutive seeds and different PNG hashes')
        page.evaluate('jobsSignature=""; batchesSignature=""; jobs()')
        page.wait_for_function("document.querySelector('.batch-card summary').textContent.includes('完成 2/2')")
        card=page.locator('.batch-card').first
        if not card.evaluate('(el)=>el.open'): card.locator('summary').click()
        card.get_by_role('button',name='A',exact=True).first.click()
        card.get_by_role('button',name='B',exact=True).last.click()
        page.wait_for_function("document.querySelector('#compare-count').textContent==='2/2'")
        page.locator('#compare-zoom').select_option('2')
        page.wait_for_function("[...document.querySelectorAll('.compare-viewport img')].every(i=>i.complete)")
        assert page.locator('#compare-table tr').filter(has_text='种子').count()==1
        report['checks'].append('batch results can be assigned to A/B and inspected at 200%')
    page.screenshot(path=str(ROOT/'docs/pro-batch-desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.wait_for_timeout(300)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    page.screenshot(path=str(ROOT/'docs/pro-batch-mobile.png'),full_page=True)
    report['checks'].append('desktop and mobile layout, no horizontal page overflow')
    report['page_errors']=errors;assert not errors,errors
    browser.close()
(ROOT/'docs/pro-batch-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps({'checks':report['checks'],'page_errors':report['page_errors']},ensure_ascii=False,indent=2))
