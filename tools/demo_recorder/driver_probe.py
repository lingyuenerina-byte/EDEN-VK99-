# -*- coding: utf-8 -*-
"""第四段校准: 打开驱动窗口 -> 真鼠标点'屏幕设置' -> 页面结构 dump"""
import sys, time, ctypes, ctypes.wintypes as wt, json
sys.path.insert(0, ".")
import demo_lib as D

D.dpi_aware()
u = ctypes.windll.user32
h = 133768
u.ShowWindow(h, 9)
time.sleep(0.6)
u.SetForegroundWindow(h)
u.BringWindowToTop(h)
time.sleep(0.8)
co = D.client_origin(h)
r = wt.RECT()
u.GetWindowRect(h, ctypes.byref(r))
print("win", (r.left, r.top, r.right, r.bottom), "client", co)

c = D.CDP(9223)
# 先探活
alive = c.js("1+1")
print("cdp alive:", alive)

expr = """(() => {
  const els = [...document.querySelectorAll('*')].filter(e => e.childElementCount === 0 && e.textContent.trim() === '屏幕设置');
  if (!els.length) return 'NOELEM';
  const e = els[0], b = e.getBoundingClientRect();
  return JSON.stringify({x: b.left + b.width/2, y: b.top + b.height/2, w: b.width, h: b.height,
                         dpr: window.devicePixelRatio, iw: innerWidth, ih: innerHeight});
})()"""
d = c.js(expr)
print("menu:", d)
if d and d != "NOELEM":
    dd = json.loads(d)
    sx, sy = int(co[0] + dd["x"] * dd["dpr"]), int(co[1] + dd["y"] * dd["dpr"])
    print("click screen:", (sx, sy))
    D.human_move(sx, sy, 500)
    D.click()
    time.sleep(2.2)
    txt = c.js("document.body.innerText.slice(0,500)")
    print("PAGE:", txt.replace("\n", " | ")[:420])
