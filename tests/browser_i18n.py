"""Bilingual UI state and locale regressions; fake inference, no GPU or network."""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_app.config import GENERATION, EXAMPLES, MODELS
from studio_app.workflow import normalize, build_workflow, PRO_OPTIONS, PRO_DEFAULTS
from studio_app.navigation import header
from markdown_it import MarkdownIt

URL='http://127.0.0.1:7896'
USER_TEXT='完成 查看 种子 — user text must stay unchanged'


def main():
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True,args=['--disable-gpu'])
        errors=[]
        p=normalize({'prompt':USER_TEXT,'seed':0})
        active={'id':'active-i18n','status':'running','created':1,'payload':p,'progress':{'stage':'采样','value':2,'max':40},'actual_size':[1024,1024]}
        complete={**active,'id':'done-i18n','status':'done','workflow':build_workflow(**p),
                  'result':{'files':['fixture.png'],'seconds':1,'timings':{},'actual_size':[1024,1024],'prompt_id':'done-i18n'}}
        def setup(path,locale='en-US',saved=None,viewport=None):
            page=browser.new_page(locale=locale,viewport=viewport or {'width':1600,'height':1000})
            page.on('pageerror',lambda error:errors.append(str(error)))
            if saved:
                page.add_init_script('for (const [k,v] of Object.entries('+json.dumps(saved)+')) localStorage.setItem(k,JSON.stringify(v));')
            state={'mutations':[],'polls':0,'hold':False,'pending':[]}
            def handle(route):
                req=route.request;url=urlsplit(req.url);name=url.path
                if name.startswith('/static/'):
                    file=ROOT/'web'/name.rsplit('/',1)[1]
                    return route.fulfill(body=file.read_bytes(),content_type='application/javascript' if file.suffix=='.js' else 'text/css')
                if name in ('/','/pro'):
                    return route.fulfill(body=(ROOT/'web'/('pro.html' if name=='/pro' else 'index.html')).read_bytes(),content_type='text/html')
                if name.startswith('/help'):
                    lang=parse_qs(url.query).get('lang',['zh-CN'])[0]
                    doc=ROOT/('docs/en/guide.md' if lang=='en' else 'GUIDE.md')
                    content=MarkdownIt().render(doc.read_text())
                    return route.fulfill(body='<html><script src="/static/locales.js" defer></script><script src="/static/i18n.js" defer></script>'+header('help')+f'<article data-guide-page="guide" data-guide-locale="{lang}">'+content+'</article></html>',content_type='text/html')
                if name=='/api/config':return route.fulfill(json={'examples':EXAMPLES,'generation':GENERATION,'backend_ready':True,'queue_limit':5,'pro':{'defaults':PRO_DEFAULTS,'options':PRO_OPTIONS}})
                if name=='/api/pro/preview':
                    raw=req.post_data_json
                    try:
                        payload=normalize(raw)
                        data={'payload':payload,'actual_size':[payload['width'],payload['height']],'workflow':build_workflow(**payload),'warnings':['多图会增加资源需求；8GB机器建议从512参考大小开始。'],'models':MODELS}
                        return route.fulfill(json=data)
                    except ValueError as error:return route.fulfill(status=400,json={'error':str(error)})
                if name=='/api/pro/presets':return route.fulfill(json={'items':[{'name':'完成','parameters':p,'revision':2,'history':[{'revision':1,'parameters':p}]}]})
                if name=='/api/pro/batches':
                    if req.method=='POST':state['mutations'].append(req.post_data_json)
                    return route.fulfill(json={'items':[]})
                if name=='/api/gallery':return route.fulfill(json={'items':[{'name':'fixture.png','job_id':'done-i18n','prompt':USER_TEXT}],'next':None})
                if name=='/api/jobs':return route.fulfill(json={'items':[active],'next':None})
                if name=='/api/jobs/active-i18n':
                    state['polls']+=1
                    return route.fulfill(json=active)
                if name=='/api/jobs/done-i18n':return route.fulfill(json=complete)
                if name=='/api/generate':
                    state['mutations'].append({'key':req.headers['idempotency-key'],'payload':req.post_data_json})
                    return route.fulfill(json={'id':active['id'],'payload':active['payload']})
                if name.startswith(('/thumb/','/output/')):return route.fulfill(body=(ROOT/'examples/input_cat.png').read_bytes(),content_type='image/png')
                if req.method=='POST':state['mutations'].append(name)
                return route.fulfill(status=404)
            page.route(URL+'/**',handle)
            page.goto(URL+path)
            page.wait_for_function("typeof I18n !== 'undefined'")
            return page,state

        # Workbench: active task, zero seed, custom names, selected result and history.
        page,state=setup('/pro',saved={'proActive':'active-i18n','proSelected':'done-i18n',
            'proDraft':{'parameters':p,'references':[]}})
        page.wait_for_function("document.querySelector('#validation').textContent.includes('Validated')")
        page.wait_for_function("document.querySelector('#message').textContent.includes('Sampling')")
        page.wait_for_function("document.querySelector('#result-detail').textContent.includes('Actual result')")
        assert page.locator('html').get_attribute('lang')=='en'
        assert page.locator('#presets button').first.inner_text()=='完成'
        assert 'Multiple references' in page.locator('#warnings').inner_text()
        before=page.evaluate("({draft:localStorage.getItem('proDraft'),active:localStorage.getItem('proActive'),payload:JSON.stringify(payload()),selected:localStorage.getItem('proSelected')})")
        for language in ('zh-CN','en','zh-CN','en'):
            page.locator('[data-locale-select]').select_option(language)
            assert page.locator('html').get_attribute('lang')==language
            assert page.locator('#prompt').input_value()==USER_TEXT
            assert page.locator('#seed').input_value()=='0'
            assert page.locator('#presets button').first.inner_text()=='完成'
            assert page.evaluate("({draft:localStorage.getItem('proDraft'),active:localStorage.getItem('proActive'),payload:JSON.stringify(payload()),selected:localStorage.getItem('proSelected')})")==before
        assert 'Sampling' in page.locator('#message').inner_text()
        assert 'View' in page.locator('#jobs').inner_text()
        assert 'History' in page.locator('#presets select').inner_text()
        assert 'Default' in page.locator('#sampler').inner_text()
        assert page.locator('#preset-name').get_attribute('placeholder').startswith('For example:')
        assert page.locator('#prompt').get_attribute('placeholder').startswith('Subject,')
        assert state['mutations']==[]
        # Dynamic localized validation error survives another language switch.
        page.locator('#steps').fill('0')
        page.wait_for_function("document.querySelector('#validation').textContent.includes('between 1 and 60')")
        page.locator('[data-locale-select]').select_option('zh-CN')
        assert '步数需为1–60' in page.locator('#validation').inner_text()
        page.locator('#steps').fill('40')
        page.wait_for_function("document.querySelector('#validation').textContent.includes('参数已校验')")
        # Pending batch identity is never changed by language selection.
        pending={'key':'fixed-request-id','kind':'batch','body':{'parameters':p,'kind':'seeds','count':2}}
        page.evaluate('(p)=>{localStorage.setItem("proPending",JSON.stringify(p));controls();}',pending)
        snapshot=page.evaluate('localStorage.getItem("proPending")')
        page.locator('[data-locale-select]').select_option('en')
        assert page.evaluate('localStorage.getItem("proPending")')==snapshot
        assert page.locator('#run').is_disabled()
        page.evaluate('localStorage.removeItem("proPending");controls();')
        # Missing keys fall back without altering document/user content; placeholder values remain opaque.
        assert page.evaluate("String(I18n.msg('missing.test.key'))")=='missing.test.key'
        assert page.evaluate("String(I18n.server('种子 0'))")=='Seed 0'
        page.reload()
        page.wait_for_function("document.querySelector('#validation').textContent.includes('Validated')")
        assert page.locator('html').get_attribute('lang')=='en'
        assert page.locator('#prompt').input_value()==USER_TEXT
        # Every visible UI string is English except explicitly preserved user content.
        stray=page.evaluate('''() => {
          const skip = '#prompt, #negative_prompt, #result-detail, #presets, #gallery, #jobs, select[data-locale-select]';
          const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
          const texts=[]; let node;
          while(node=walker.nextNode()) {
            const el=node.parentElement;
            if(el && !el.closest(skip) && el.getClientRects().length && /[\u4e00-\u9fff]/.test(node.textContent)) texts.push(node.textContent.trim());
          }
          return texts.filter(Boolean);
        }''')
        assert not stray,stray
        page.screenshot(path='/tmp/orion-workbench-en.png',full_page=True)
        page.close()

        # Creation studio: keep pending request and draft unchanged, then reuse the exact key.
        pending={'key':'same-id-after-language-change','payload':p}
        page,state=setup('/',saved={'studioDraft':{'payload':p,'references':[]},'studioPending':pending})
        page.wait_for_function("document.querySelector('#health').textContent.includes('connected')")
        page.locator('#retry').wait_for(state='visible')
        original=page.evaluate('localStorage.getItem("studioPending")')
        page.locator('[data-locale-select]').select_option('zh-CN')
        assert page.evaluate('localStorage.getItem("studioPending")')==original
        assert page.locator('#prompt').input_value()==USER_TEXT
        page.locator('[data-locale-select]').select_option('en')
        page.locator('#retry').click()
        page.wait_for_function("document.querySelector('#status').textContent.includes('Sampling')")
        assert len(state['mutations'])==1 and state['mutations'][0]==pending
        assert page.locator('#prompt').input_value()==USER_TEXT
        assert 'View' in page.locator('#tasks').inner_text()
        # Navigation keeps the selected language, including rendered help content.
        page.locator('.studio-navigation a[href^="/help"]').click()
        page.wait_for_function("document.querySelector('[data-guide-page]').textContent.includes('User guide')")
        page.locator('[data-locale-select]').select_option('zh-CN')
        page.wait_for_function("document.querySelector('[data-guide-page]').textContent.includes('使用指南')")
        assert page.locator('html').get_attribute('lang')=='zh-CN'
        page.close()

        # Browser-locale detection and unsupported-language fallback.
        for language,expected in [('zh-TW','zh-CN'),('fr-FR','en')]:
            page,_=setup('/pro',locale=language,viewport={'width':390,'height':844})
            page.wait_for_function("document.querySelector('#validation').textContent.includes('✓')")
            assert page.locator('html').get_attribute('lang')==expected
            assert page.locator('[data-locale-select]').is_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
            if expected=='en':page.screenshot(path='/tmp/orion-workbench-en-mobile.png',full_page=True)
            page.close()
        assert not errors,errors
        browser.close()
        print('Bilingual UI PASS: locale persistence, active tasks, pending IDs, drafts, user text, errors, guides and mobile layout.')


if __name__=='__main__':main()
