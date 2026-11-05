# -*- coding: utf-8 -*-
"""再试: 点选择照片, 监控 8s, 不要求有标题, 记录新窗口 class/pid"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
cls = ctypes.create_unicode_buffer(64)

def snap():
    out = {}
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if u.IsWindowVisible(h):
            tb = ctypes.create_unicode_buffer(128)
            u.GetWindowTextW(h, tb, 128)
            u.GetClassNameW(h, cls, 64)
            pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out[int(h)] = (tb.value, cls.value, pid.value)
        return True
    u.EnumWindows(cb, 0)
    return out

w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
w.cdp = {"driver": D.CDP(9223)}
# 检查驱动页面确实显示选择照片按钮(可能在别的tab)
print("页面上有选择照片:", w.cdp["driver"].js("[...document.querySelectorAll('button,span,div')].some(e=>e.textContent.trim()==='选择照片')"))
t2 = w.resolve({"sel": "text:选择照片"})
print("pt:", t2 and t2["pt"], "box:", t2 and t2["box"])
before = snap()
D.human_move(*t2["pt"], 400)
time.sleep(0.3)
D.click()
t0 = time.time()
seen = []
while time.time() - t0 < 8:
    for h, v in snap().items():
        if h not in before and v[0] != "Program Manager" and v not in seen:
            seen.append(v)
            print("NEW:", h, v, flush=True)
    if seen:
        break
    time.sleep(0.3)
if not seen:
    print("no new window; dialog maybe hidden input route")
    # 看是否出现 hidden file input
    print("file inputs:", w.cdp["driver"].js("document.querySelectorAll('input[type=file]').length"))
