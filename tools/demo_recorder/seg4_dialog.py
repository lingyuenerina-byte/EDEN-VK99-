# -*- coding: utf-8 -*-
"""续测: 对驱动'选择照片'对话框输入 photo1 -> 回车 -> 帧数/画面变化"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
h = u.FindWindowW(None, "选择视频 / 图片素材")
print("dialog:", bool(h))
if h:
    h = int(h)
    pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
    print("dialog pid:", pid.value, "(driver pids differ from eden 55004)")
    u.SetForegroundWindow(h); time.sleep(0.6)
    D.type_text(r"H:\EDENVK\assets\photo1.png"); time.sleep(0.5)
    D.press_key(0x0D); time.sleep(2.5)
    print("dialog still:", bool(u.FindWindowW(None, "选择视频 / 图片素材")))
    ed = u.FindWindowW(None, "选择视频 / 图片素材")
    pid2 = wt.DWORD()
    if ed:
        u.GetWindowThreadProcessId(ed, ctypes.byref(pid2))
    print("remaining dialog pid:", pid2.value if ed else "-")
c = D.CDP(9223)
print("driver frames:", c.js("(()=>{const m=document.body.innerText.match(/帧数：\\s*\\n?\\s*(\\d+)\\/(\\d+)/);return m?m[1]+'/'+m[2]:'?'} )()"))
print("driver tail:", (c.js("document.body.innerText.slice(0,120)") or "").replace("\n", " | "))
