# -*- coding: utf-8 -*-
"""hide_term.py — 看门狗: 保持 Hermes Agent 执行终端窗隐藏, 防止录制时弹出遮挡"""
import ctypes as C
import time

u = C.windll.user32
Proc = C.WINFUNCTYPE(C.c_bool, C.c_void_p, C.c_void_p)

def sweep():
    n = 0
    def cb(h, _):
        nonlocal n
        cn = C.create_unicode_buffer(256)
        u.GetClassNameW(h, cn, 256)
        if "CASCADIA" not in cn.value:
            return True
        b = C.create_unicode_buffer(256)
        u.GetWindowTextW(h, b, 256)
        t = b.value
        if t == "Hermes Agent" or "Scripts\\" in t or "Scripts/" in t \
                or t.endswith("python.exe") or t.endswith("pythonw.exe"):
            if u.IsWindowVisible(h):
                u.ShowWindow(h, 0)  # SW_HIDE
                n += 1
        return True
    u.EnumWindows(Proc(cb), 0)
    return n

while True:
    sweep()
    time.sleep(1.5)
