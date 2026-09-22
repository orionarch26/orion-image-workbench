"""Regression probes for professional workbench recovery, comparison and request races. No GPU jobs."""
import json,sys,time
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studio_app.workflow import normalize,build_workflow,PRO_OPTIONS,PRO_DEFAULTS
from studio_app.config import GENERATION,EXAMPLES,MODELS
URL='http://127.0.0.1:7897'
report={}

def job(id,**changes):
 p=normalize({'prompt':'review fixture','seed':0,**changes})
 wf=build_workflow(**p)
 return {'id':id,'prompt_id':id,'created':1,'status':'done','payload':p,'workflow':wf,'actual_size':[768,768],
         'result':{'files':['fixture.png'],'seconds':10,'timings':{'backend_execution_seconds':10},'actual_size':[768,768]}}

with sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,args=['--disable-gpu'])
 def setup(initial=None):
  page=browser.new_page(locale="zh-CN");state={'requests':[],'held':{},'responses':{},'hold':set(),'pending':[],'posts':[]}
  if initial:page.add_init_script('for (const [k,v] of Object.entries('+json.dumps(initial)+')) localStorage.setItem(k,JSON.stringify(v));')
  def handler(route):
   path=route.request.url.removeprefix(URL);state['requests'].append(path)
   if route.request.method=='POST':state['posts'].append({'path':path,'body':route.request.post_data_json,'key':route.request.headers.get('idempotency-key')})
   if path=='/api/pro/batches' and route.request.method=='GET':return route.fulfill(json={'items':[]})
   if path in state['hold']:state['held'][path]=route;state['pending'].append(route);return
   if path in state['responses']:
    code,value=state['responses'][path];return route.fulfill(status=code,json=value)
   if path=='/pro':return route.fulfill(body=(ROOT/'web/pro.html').read_bytes(),content_type='text/html')
   if path.startswith('/static/'):
    file=ROOT/'web'/path.rsplit('/',1)[1]
    return route.fulfill(body=file.read_bytes(),content_type='text/css' if file.suffix=='.css' else 'application/javascript')
   if path=='/api/config':return route.fulfill(json={'backend_ready':True,'examples':EXAMPLES,'generation':GENERATION,'queue_limit':5})
   if path=='/api/pro/preview':
    p=normalize(route.request.post_data_json);return route.fulfill(json={'payload':p,'actual_size':[768,768],'workflow':build_workflow(**p),'warnings':[],'models':MODELS,'defaults':PRO_DEFAULTS,'options':PRO_OPTIONS})
   if path=='/api/pro/presets':return route.fulfill(json={'items':[]})
   if path.startswith('/api/gallery'):return route.fulfill(json={'items':[],'next':None})
   if path.startswith('/api/jobs?'):return route.fulfill(json={'items':[],'next':None})
   if path.startswith(('/output/','/thumb/','/reference/')):return route.fulfill(body=(ROOT/'examples/input_cat.png').read_bytes(),content_type='image/png')
   return route.fulfill(status=404,json={'error':'任务不存在'})
  page.route(URL+'/**',handler)
  return page,state

 # Restoring a missing selected result must not block the independent active task.
 page,state=setup({'proSelected':'missing-selection','proActive':'active-task'})
 state['responses']['/api/jobs/active-task']=(200,{**job('active-task'),'status':'running'})
 page.goto(URL+'/pro');page.wait_for_timeout(4200)
 report['startup_missing_selection']={'saved_active':page.evaluate("localStorage.getItem('proActive')"),
  'active_queries':state['requests'].count('/api/jobs/active-task'),'message':page.locator('#message').inner_text(),
  'in_memory_active':page.evaluate('active')}
 assert report['startup_missing_selection']['active_queries']>=1
 page.close()

 # Reference differences and seed zero must remain visible.
 page,state=setup();page.goto(URL+'/pro');page.wait_for_function("!document.querySelector('#run').disabled")
 a=job('A',mode='edit',images=['studio_a.png']);b=job('B',mode='edit',images=['studio_b.png'])
 page.evaluate('([a,b])=>{comparison=[a,b];renderComparison();view("compare");}',[a,b])
 report['comparison_omits_references']={'different_rows':page.locator('#compare-table tr.different').count(),
  'seed_row':page.locator('#compare-table tr').filter(has_text='种子').inner_text(),
  'reference_row_present':'参考图片' in page.locator('#compare-table').inner_text()}
 assert report['comparison_omits_references']['different_rows']==1
 assert '空' not in report['comparison_omits_references']['seed_row']
 assert report['comparison_omits_references']['reference_row_present']
 # Equivalent effective cache settings must compare equal.
 a=job('A',cache_dtype='auto');b=job('B',cache_dtype='default')
 page.evaluate('([a,b])=>{comparison=[a,b];renderComparison();}',[a,b])
 report['cache_comparison']={'actual_dtype_a':a['workflow']['2']['inputs']['dtype'],'actual_dtype_b':b['workflow']['2']['inputs']['dtype'],
 'reported_row':page.locator('#compare-table tr').filter(has_text='缓存精度').inner_text()}
 assert page.locator('#compare-table tr.different').count()==0
 page.close()

 # Later user selection must win even when the older request returns last.
 page,state=setup();a=job('slow',prompt='A slow selection');b=job('fast',prompt='B latest selection')
 state['responses']['/api/gallery?offset=0']=(200,{'items':[{'name':'fixture.png','job_id':'slow','prompt':'A'},{'name':'fixture.png','job_id':'fast','prompt':'B'}],'next':None})
 state['hold'].add('/api/jobs/slow');state['responses']['/api/jobs/fast']=(200,b)
 page.goto(URL+'/pro');page.wait_for_function("!document.querySelector('#run').disabled")
 page.locator('#gallery button').nth(0).click();page.locator('#gallery button').nth(1).click()
 page.wait_for_function("selected?.id==='fast'")
 state['held']['/api/jobs/slow'].fulfill(json=a)
 page.wait_for_timeout(300)
 assert page.evaluate("selected.id")=="fast"
 report['out_of_order_selection']={'last_clicked':'fast','displayed_after_late_response':page.evaluate('selected.id')}
 page.close()

 # A slow backend must not receive overlapping polls.
 page,state=setup();page.goto(URL+'/pro');page.wait_for_function("!document.querySelector('#run').disabled")
 state['hold'].add('/api/jobs/slow-poll')
 page.evaluate("active='slow-poll'");page.wait_for_timeout(6000)
 report['overlapping_polls']={'unanswered_requests_in_six_seconds':state['requests'].count('/api/jobs/slow-poll')}
 assert report['overlapping_polls']['unanswered_requests_in_six_seconds']==1
 page.evaluate('active=null')
 for route in state['pending']:route.abort()
 page.wait_for_timeout(100)
 page.close()

 # Preview must retry a transient failure without requiring a parameter edit.
 page,state=setup();state['responses']['/api/pro/preview']=(503,{'error':'temporary outage'})
 page.goto(URL+'/pro');page.wait_for_timeout(1000)
 del state['responses']['/api/pro/preview']
 page.wait_for_timeout(3000)
 report['preview_reconnect']={'requests':state['requests'].count('/api/pro/preview'),'run_still_disabled':page.locator('#run').is_disabled(),
 'status':page.locator('#validation').inner_text()}
 assert not report['preview_reconnect']['run_still_disabled']
 page.close()

 # A batch retry must preserve the original endpoint, parameters and request ID.
 page,state=setup();page.goto(URL+'/pro');page.wait_for_function("!document.querySelector('#run').disabled")
 page.locator('#run-kind').select_option('seeds');page.locator('#batch-count').fill('2')
 state['responses']['/api/pro/batches']=(503,{'error':'response unavailable'})
 page.locator('#run').click();page.wait_for_function("!document.querySelector('#retry').hidden && !document.querySelector('#retry').disabled")
 original=page.evaluate("JSON.parse(localStorage.getItem('proPending'))")
 page.locator('#prompt').fill('newer draft must not replace submitted batch')
 state['responses']['/api/pro/batches']=(200,{'id':'batch-one','job_ids':['member-one','member-two']})
 state['responses']['/api/jobs/member-one']=(200,{**job('member-one'),'status':'running'})
 page.locator('#retry').click();page.wait_for_function("localStorage.getItem('proPending')===null")
 posts=[p for p in state['posts'] if p['path']=='/api/pro/batches']
 assert len(posts)==2 and posts[0]==posts[1]
 assert page.locator('#prompt').input_value()=='newer draft must not replace submitted batch'
 report['batch_retry']={'same_key_and_body':posts[0]==posts[1],'count':original['parameters']['count'],'newer_draft_preserved':True}
 page.close();browser.close()
(ROOT/'docs/pro-review-regression.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print(json.dumps(report,ensure_ascii=False,indent=2))
