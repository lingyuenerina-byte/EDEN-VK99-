# -*- coding: utf-8 -*-
"""第四段链实测: 屏幕设置 -> 真鼠标点'选择照片' -> 对话框标题/输入/确认 -> 帧数变化"""
import sys, time, ctypes, ctypes.wintypes as wt, json
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
w = R.Runner(print, lambda m: None)
h = w.recover_driver()
print("driver hwnd:", h)
w.win = R.bring_front(("Valkyrie Driver",))
print("win:", w.win["rect"], "client:", w.win["client"])
w.cur_app = "driver"
w.cdp = {"driver": D.CDP(9223)}

# 先确保在屏幕设置页 (点菜单)
t = w.resolve({"sel": "text:屏幕设置"})
print("屏幕设置:", t and t["pt"])
if t:
    D.human_move(*t["pt"], 400); D.click(); time.sleep(1.5)

# 帧数现状
def frames():
    return w.cdp["driver"].js("(()=>{const m=document.body.innerText.match(/帧数：\\s*(\\d+)\\/(\\d+)/);return m?m[0]:null})()")
print("frames before:", frames())

# 点'选择照片'
t2 = w.resolve({"sel": "text:选择照片"})
print("选择照片:", t2 and t2["pt"])
if not t2:
    sys.exit("no 选择照片")
D.human_move(*t2["pt"], 500); D.click(); time.sleep(1.5)

titles = []
b = ctypes.create_unicode_buffer(256)
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(hh, l):
    if u.IsWindowVisible(hh) and u.GetWindowTextLengthW(hh):
        u.GetWindowTextW(hh, b, 256)
        if any(k in b.value for k in ("打开", "Open", "选择", "照片")):
            titles.append(b.value)
    return True
u.EnumWindows(cb, 0)
print("dialog titles:", titles)
