/* Explicit UI bindings only. Never translate user text or workflow data. */
"use strict";
window.I18n = (() => {
  const catalogs = window.ORION_LOCALES;
  const supported = new Set(["en", "zh-CN"]);
  const key = "orion.locale";
  const detect = (value) => /^zh(?:-|$)/i.test(value || "") ? "zh-CN" : "en";
  let locale;
  try { locale = localStorage.getItem(key); } catch { /* Private browsing. */ }
  if (!supported.has(locale)) locale = detect(navigator.language);
  class Message {
    constructor(render) { this.render = render; }
    toString() { return this.render(); }
    toJSON() { return String(this); }
  }
  const msg = (id, values = {}) => new Message(() => {
    const pattern = catalogs[locale]?.[id] ?? catalogs.en[id] ?? id;
    return pattern.replace(/\{(\w+)\}/g, (whole, name) => Object.hasOwn(values, name) ? String(values[name] ?? "") : whole);
  });
  const join = (items) => {
    const render = () => items.map(v => String(v ?? "")).join("");
    return items.some(v => v instanceof Message) ? new Message(render) : render();
  };
  const plus = (a, b) => a instanceof Message || b instanceof Message ? join([a, b]) : a + b;
  const parts = (items, separator) => items.some(v => v instanceof Message)
    ? join(items.flatMap((v, i) => i ? [separator, v] : [v])) : items.join(separator);
  const bindings = new Map();
  let writes = 0;
  function bind(node, value, attribute = "textContent") {
    if (!node) return node;
    if (!bindings.has(node)) bindings.set(node, new Map());
    // Once populated dynamically, a control no longer uses its initial static text.
    if (attribute === "textContent") node.removeAttribute("data-i18n");
    if (value instanceof Message) bindings.get(node).set(attribute, value);
    else bindings.get(node).delete(attribute);
    if (attribute === "textContent" || attribute === "alt") node[attribute] = String(value ?? "");
    else node.setAttribute(attribute, String(value ?? ""));
    if (++writes % 128 === 0) queueMicrotask(() => { for (const n of bindings.keys()) if (!n.isConnected) bindings.delete(n); });
    return node;
  }
  function applyStatic(root = document) {
    root.querySelectorAll('[data-i18n]').forEach(node => {
      node.textContent = String(msg(node.dataset.i18n));
    });
    for (const attribute of ['placeholder', 'title', 'aria-label']) {
      root.querySelectorAll(`[data-i18n-${attribute}]`).forEach(node => {
        node.setAttribute(attribute, String(msg(node.getAttribute(`data-i18n-${attribute}`))));
      });
    }
  }
  const escapeRE = (value) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const serverRules = window.ORION_SERVER_KEYS.map(id => {
    const source = catalogs['zh-CN'][id];
    const names = [...source.matchAll(/\{(\w+)\}/g)].map(m => m[1]);
    const pattern = source.split(/\{\w+\}/).map(escapeRE).join('([\\s\\S]*?)');
    return { id, source, names, regex: new RegExp('^' + pattern + '$') };
  });
  function server(value) {
    if (value instanceof Message || typeof value !== 'string') return value;
    for (const rule of serverRules) {
      const match = value.match(rule.regex);
      if (match) {
        const values = Object.fromEntries(rule.names.map((n, i) => [n, match[i + 1]]));
        // Only developer-defined integer field labels, never filenames or prompts.
        if (rule.source === '{p0}必须是整数') {
          const field = serverRules.find(r => !r.names.length && r.source === values.p0);
          if (field) values.p0 = msg(field.id);
        }
        return msg(rule.id, values);
      }
    }
    // Known diagnostic prefixes/suffixes may accompany raw upstream details.
    for (const rule of serverRules) {
      if (!rule.names.length && rule.source.endsWith('：') && value.startsWith(rule.source))
        return join([msg(rule.id), value.slice(rule.source.length)]);
      if (!rule.names.length && rule.source.startsWith('；') && value.endsWith(rule.source))
        return join([value.slice(0, -rule.source.length), msg(rule.id)]);
    }
    return value; // Unknown provider details are preserved verbatim.
  }
  function error(value) {
    const e = new Error(String(value));
    Object.defineProperty(e, 'message', { configurable: true, get: () => server(value) });
    return e;
  }
  function option(label, value) {
    return bind(new Option('', value), label);
  }
  function updateLinks() {
    document.querySelectorAll('a[href^="/help"]').forEach(a => {
      const url = new URL(a.getAttribute('href'), location.origin);
      url.searchParams.set('lang', locale); a.href = url.pathname + url.search;
    });
  }
  async function updateGuide() {
    const guide = document.querySelector('[data-guide-page]');
    if (!guide || guide.dataset.guideLocale === locale) return;
    const targetLocale = locale;
    try {
      const url = new URL(location.href); url.searchParams.set('lang', targetLocale);
      const response = await fetch(url, { headers: { 'X-Orion-Guide': '1' } });
      if (!response.ok) throw new Error('Guide unavailable');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const next = doc.querySelector('[data-guide-page]');
      if (!next || locale !== targetLocale) return;
      guide.replaceChildren(...next.childNodes);
      guide.dataset.guideLocale = targetLocale;
      history.replaceState(null, '', url.pathname + url.search);
      updateLinks();
    } catch { /* Keep the readable previous guide; never reload an active editor. */ }
  }
  function setLocale(value, save = true) {
    locale = supported.has(value) ? value : 'en';
    if (save) try { localStorage.setItem(key, locale); } catch { /* Session-only preference. */ }
    document.documentElement.lang = locale;
    applyStatic();
    for (const [node, values] of bindings) {
      if (!node.isConnected) { bindings.delete(node); continue; }
      for (const [attribute, value] of values) {
        if (attribute === 'textContent' || attribute === 'alt') node[attribute] = String(value ?? '');
        else node.setAttribute(attribute, String(value ?? ''));
      }
    }
    document.querySelectorAll('[data-locale-select]').forEach(s => { s.value = locale; });
    updateLinks(); updateGuide();
    document.dispatchEvent(new CustomEvent('orion:locale-changed', { detail: { locale } }));
  }
  function init() {
    document.querySelectorAll('[data-locale-select]').forEach(s => s.addEventListener('change', () => setLocale(s.value)));
    setLocale(locale, false);
  }
  window.addEventListener('storage', e => { if (e.key === key) setLocale(e.newValue, false); });
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
  return { msg, join, plus, parts, text: bind, attr: bind, option, server, error, setLocale,
    get locale() { return locale; }, string: value => String(value ?? '') };
})();
