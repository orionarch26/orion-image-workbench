"""Consistent header for the studio's three main destinations."""

def header(active='create'):
    links=[('create','/','创作画室','<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m3 15 5-5 5 5 3-3 5 5"/><circle cx="16" cy="8" r="1"/>'),
           ('pro','/pro','专业工作台','<rect x="3" y="4" width="6" height="6" rx="1.5"/><rect x="15" y="14" width="6" height="6" rx="1.5"/><path d="M9 7h6a3 3 0 0 1 3 3v4M6 10v7h9"/>'),
           ('help','/help','使用指南','<path d="M12 5v15M3 4h5a4 4 0 0 1 4 2 4 4 0 0 1 4-2h5v15h-5a5 5 0 0 0-4 1 5 5 0 0 0-4-1H3Z"/>')]
    items=''.join(f'<a class="studio-nav-link" href="{url}"'+(' aria-current="page"' if active==key else '')+f'><svg viewBox="0 0 24 24" aria-hidden="true">{icon}</svg><span>{title}</span></a>' for key,url,title,icon in links)
    state_id='connection' if active=='pro' else 'health'
    state='使用帮助' if active=='help' else '检查服务…'
    return f'''<header class="studio-header"><a class="studio-brand" href="/" aria-label="猎户画室首页"><span class="studio-brand-icon" aria-hidden="true"><svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/></svg></span><span class="studio-brand-copy"><strong>猎户画室</strong><small>Qwen Image 2.1</small></span></a><nav class="studio-navigation" aria-label="主导航">{items}</nav><div class="studio-service"><span class="studio-local">LOCAL WORKSPACE</span><span id="{state_id}" class="studio-health" role="status">{state}</span></div></header>'''
