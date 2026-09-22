"""Professional page E2E. --generate also executes a real non-default GPU workflow."""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]

def main():
    args=argparse.ArgumentParser();args.add_argument('--generate',action='store_true');args=args.parse_args()
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as temp:
        browser=pw.chromium.launch(headless=True,args=['--disable-gpu'])
        page=browser.new_page(locale="zh-CN",viewport={'width':1600,'height':1050},accept_downloads=True)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:7860/pro')
        page.wait_for_function("!document.querySelector('#run').disabled")
        assert '专业工作台' in page.title()
        page.locator('#width').fill('768');page.locator('#height').fill('768')
        page.locator('#steps').fill('12');page.locator('#cfg').fill('1.1')
        page.locator('#sampler').select_option('heun');page.locator('#seed').fill('6200921')
        page.locator('details').filter(has=page.locator('#negative_prompt')).locator('summary').click()
        page.locator('#negative_prompt').fill('text, watermark')
        page.locator('details').filter(has=page.locator('#tile_size')).locator('summary').click()
        page.locator('#tile_size').select_option('256')
        page.wait_for_function("!document.querySelector('#run').disabled")
        page.locator('#inspect').click()
        graph=json.loads(page.locator('#graph-json').inner_text())
        assert graph['7']['inputs']['cfg']==1.1 and graph['7']['inputs']['sampler_name']=='heun'
        assert graph['8']['inputs']['tile_size']==256
        page.locator('#close-dialog').click()
        page.locator('#preset-name').fill('专业验收示例 · Heun 实验')
        page.locator('#save-preset').click()
        page.wait_for_function("document.querySelector('#message').textContent.includes('已保存预设')")
        with page.expect_download() as event:page.locator('#export').click()
        exported=Path(temp)/'recipe.json';event.value.save_as(exported)
        page.locator('#steps').fill('30')
        page.locator('#import-file').set_input_files(exported)
        page.wait_for_function("document.querySelector('#steps').value === '12'")
        page.reload();page.wait_for_function("!document.querySelector('#run').disabled")
        assert page.locator('#cfg').input_value()=='1.1'
        page.locator('#mode').select_option('edit')
        page.locator('#upload').set_input_files(ROOT/'examples/input_cat.png')
        page.wait_for_function("document.querySelector('#validation').textContent.includes('参数已校验') && document.querySelector('#references').children.length === 1")
        assert '768 × 768' in page.locator('#flow-output').inner_text()
        page.locator('#mode').select_option('text')
        page.wait_for_function("!document.querySelector('#run').disabled")
        report={'checks':['separate professional page','advanced parameters in compiled graph','persistent preset','recipe import/export','independent draft reload','reference upload and dimensions'],'page_errors':errors}
        if args.generate:
            with page.expect_response(lambda r:'/api/generate' in r.url and r.request.method=='POST') as event:
                page.locator('#run').click()
            job_id=event.value.json()['id'];report['job_id']=job_id
            print('Real professional workflow: '+job_id,flush=True)
            page.locator('#steps').fill('30')
            deadline=time.monotonic()+600
            while time.monotonic()<deadline:
                job=page.request.get('http://127.0.0.1:7860/api/jobs/'+job_id).json()
                if job['status']=='done':break
                if job['status'] in ('failed','cancelled','timed_out','lost','submission_unknown'):raise AssertionError(job)
                page.wait_for_timeout(2000)
            else:raise TimeoutError(job_id)
            page.wait_for_function("document.querySelector('#result-detail').textContent.includes('12步')")
            assert page.locator('#steps').input_value()=='30','Job completion must preserve newer draft'
            report['result']=job['result'];report['checks'].append('real Heun / CFG 1.1 / VAE256 generation with newer draft preserved')
        else:
            page.locator('#gallery button').first.click()
        page.get_by_role('button',name='设为 A',exact=True).wait_for()
        page.get_by_role('button',name='设为 A',exact=True).click()
        page.locator('#gallery button').nth(1).click()
        page.get_by_role('button',name='设为 B',exact=True).click()
        assert page.locator('#compare-images img').count()==2
        assert page.locator('#compare-table tr.different').count()>0
        report['checks'].append('A/B comparison and parameter differences')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ROOT/'docs/pro-comparison.png'),full_page=True)
        page.locator('#view-result').click()
        # Use the photo fixture for the documentation preview.
        page.locator('#gallery button').filter(has=page.locator('img[alt^="一只橘猫"]')).first.click()
        page.evaluate('window.scrollTo(0,0)')
        assert page.locator('#run').bounding_box()['y'] < 1050
        page.screenshot(path=str(ROOT/'docs/pro-desktop.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.evaluate('window.scrollTo(0,0)')
        page.screenshot(path=str(ROOT/'docs/pro-mobile.png'),full_page=True)
        response=page.goto('http://127.0.0.1:7860/help/pro');assert response.status==200
        response=page.goto('http://127.0.0.1:7860/');assert response.status==200
        page.locator('#generate').wait_for();assert page.get_by_role('link',name='专业工作台').count()==1
        assert not errors,errors
        report['checks']+=['desktop and mobile without overflow','professional guide','original studio preserved']
        (ROOT/('docs/pro-browser-validation.json' if args.generate else 'docs/pro-browser-ui.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'checks':report['checks'],'page_errors':errors},ensure_ascii=False,indent=2))
        browser.close()

if __name__=='__main__':main()
