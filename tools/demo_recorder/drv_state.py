# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
import demo_lib as D

c = D.CDP(9223)
tail = c.js("document.body.innerText.slice(400,900)")
print("tail:", (tail or "").replace("\n", " | ")[:420])
sel = '[class*=modal],[class*=Modal],[class*=dialog],[class*=Dialog],[class*=confirm],[class*=toast],[class*=pop]'
expr = """(() => {
  const ms = [...document.querySelectorAll('%s')].filter(e => e.offsetParent !== null && e.innerText.trim());
  return ms.map(e => String(e.className).slice(0,40) + ' => ' + e.innerText.slice(0,80).replace(/\\n/g,' ')).slice(0,8).join(' /// ') || 'NO-VISIBLE-MODAL';
})()""" % sel
print("modal:", c.js(expr))
# 写入动画按钮状态
expr2 = """(() => {
  const b = [...document.querySelectorAll('button')].find(e => e.textContent.trim() === '写入动画');
  if (!b) return 'no btn';
  const r = b.getBoundingClientRect();
  return JSON.stringify({vis: r.width>0 && r.height>0 && b.offsetParent!==null, dis: b.disabled, cls: String(b.className).slice(0,50)});
})()"""
print("写入动画 btn:", c.js(expr2))
