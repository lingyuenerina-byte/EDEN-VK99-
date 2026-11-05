# -*- coding: utf-8 -*-
"""连环试验: 哪个动作能弹出驱动文件对话框"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
tb = ctypes.create_unicode_buffer(128)
cb64 = ctypes.create_unicode_buffer(64)

def new_windows(before):
    found = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(h, l):
        if u.IsWindowVisible(h):
            u.GetWindowTextW(h, tb, 128)
            u.GetClassNameW(h, cb64, 64)
            if h not in before and tb.value not in ("", "Program Manager"):
                found.append((int(h), tb.value, cb64.value))
        return True
    u.EnumWindows(_cb, 0)
    return found

def snap_ids():
    ids = set()
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(h, l):
        if u.IsWindowVisible(h):
            ids.add(int(h))
        return True
    u.EnumWindows(_cb, 0)
    return ids

w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
c = D.CDP(9223)

# A) input.click() 直连
before = snap_ids()
r = c.js("(()=>{const i=document.querySelector('input[type=file]');if(!i)return 'no input';i.click();return 'input.click()'})()")
print("A:", r)
time.sleep(2.5)
print("A new:", new_windows(before))

# B) 外层 button/div[class*=button] click
if not new_windows(before):
    before = snap_ids()
    r = c.js("""(() => {
      const leaf = [...document.querySelectorAll('*')].find(e => e.childElementCount === 0 && e.textContent.trim() === '选择照片');
      let el = leaf; let path = [];
      while (el && el !== document.body) { path.push(el.tagName + '.' + String(el.className).slice(0, 25)); el = el.parentElement; }
      const btn = leaf.closest('button') || leaf.closest('[class*=button]');
      if (btn) { btn.click(); return 'clicked ' + btn.tagName + '.' + String(btn.className).slice(0, 30); }
      return 'ancestors: ' + path.join(' < ');
    })()""")
    print("B:", r)
    time.sleep(2.5)
    print("B new:", new_windows(before))

# C) 真鼠标 double click
if not new_windows(before):
    before = snap_ids()
    t2 = w.resolve({"sel": "text:选择照片"})
    D.human_move(*t2["pt"], 300)
    D.click(); time.sleep(0.12); D.click()
    time.sleep(2.5)
    print("C new:", new_windows(before))
