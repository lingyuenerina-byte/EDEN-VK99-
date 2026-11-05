# -*- coding: utf-8 -*-
"""JS 触发选择照片按钮 + 监控对话框"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32

def snap():
    out = {}
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if u.IsWindowVisible(h):
            tb = ctypes.create_unicode_buffer(128)
            u.GetWindowTextW(h, tb, 128)
            u.GetClassNameW(tb and h or h, (clsbuf), 64)
            pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out[int(h)] = (tb.value, clsbuf.value, pid.value)
        return True
    clsbuf = ctypes.create_unicode_buffer(64)
    u.EnumWindows(cb, 0)
    return out

w = R.Runner(print, lambda m: None)
w.recover_driver()
w.cur_app = "driver"
w.cdp = {"driver": D.CDP(9223)}
before = snap()
r = w.cdp["driver"].js("""(() => {
  const leaf = [...document.querySelectorAll('*')].find(e => e.childElementCount === 0 && e.textContent.trim() === '选择照片');
  if (!leaf) return 'no leaf';
  let el = leaf;
  for (let i = 0; i < 5 && el; i++) {
    if (el.tagName === 'BUTTON' || /button/i.test(el.className)) break;
    el = el.parentElement;
  }
  const target = el || leaf;
  target.click();
  return 'clicked ' + target.tagName + '.' + String(target.className).slice(0, 30);
})()""")
print(r)
t0 = time.time()
seen = []
while time.time() - t0 < 6:
    for h, v in snap().items():
        if h not in before and v[0] != "Program Manager" and v not in seen:
            seen.append((h,) + v)
            print("NEW:", (h,) + v, flush=True)
    if seen:
        break
    time.sleep(0.3)
if not seen:
    print("still no dialog")
    # 输入框直塞文件(保底方案验证): CDP DOM input 设置
    print("inputs:", w.cdp["driver"].js("[...document.querySelectorAll('input[type=file]')].map(i=>i.accept+':'+i.multiple).join(',')"))
