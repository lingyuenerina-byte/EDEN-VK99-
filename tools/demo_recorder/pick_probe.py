# -*- coding: utf-8 -*-
"""步进 probe: btnPick 点击 -> 对话框 -> 输入 -> 回车 -> UI 状态"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

u = ctypes.windll.user32
D.dpi_aware()
w = R.bring_front(("EDEN", "幻映"))
hwnd = int(w["hwnd"])
co = w["client"]
print("win", w["rect"], "client", co)

c = D.CDP(9224)
e = D.el_center(c, "#btnPick")
sx, sy = int(co[0] + e["x"] * e["dpr"]), int(co[1] + e["y"] * e["dpr"])
print("btnPick screen:", (sx, sy))

D.human_move(sx, sy, 400); D.click(); time.sleep(1.5)
h = u.FindWindowW(None, "选择视频 / 图片素材")
print("dialog:", bool(h))
if h:
    h = int(h)
    u.SetForegroundWindow(h); time.sleep(0.5)
    b = ctypes.create_unicode_buffer(128)
    u.GetWindowTextW(u.GetForegroundWindow(), b, 128)
    print("foreground now:", repr(b.value))
    D.type_text(r"H:\EDENVK\assets\eden_demo.mp4")
    time.sleep(0.5)
    # 看文件名字段现在装了啥
    e2 = ctypes.create_unicode_buffer(512)
    edit = u.FindWindowExW(h, 0, "Edit", None) or u.FindWindowExW(h, 0, "ComboBoxEx32", None)
    if edit:
        SendMessageW = u.SendMessageWW if False else None
    D.press_key(0x0D); time.sleep(1.8)
    print("dialog still open:", bool(u.FindWindowW(None, "选择视频 / 图片素材")))
    txt = c.js("(document.body.innerText.match(/已选\\S*|未选择|eden_demo\\S*/g)||[]).slice(0,5).join(' | ')")
    print("UI state:", txt)
