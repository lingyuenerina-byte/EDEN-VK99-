# -*- coding: utf-8 -*-
"""验证 overlay_v2: 假箭头跟随 + 点击穿透不挡 EDEN"""
import subprocess, sys, os, time, socket, json, ctypes, ctypes.wintypes as wt
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import demo_lib as D

def send(msg):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto((json.dumps(msg) + "\n").encode(), ("127.0.0.1", 9377))

u = ctypes.windll.user32
py = r"I:\dania-tts\gsv\.venv\Scripts\pythonw.exe"
ov = subprocess.Popen([py, "overlay_v2.py"], cwd=HERE, creationflags=0x00000008)
try:
    time.sleep(1.6)
    D.dpi_aware()
    # overlay 根窗样式(枚举小窗)
    def ov_wins():
        out = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, l):
            if u.IsWindowVisible(h):
                r = wt.RECT(); u.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left in (140,) or (r.right-r.left, r.bottom-r.top) == (412, 272):
                    ex = u.GetWindowLongW(h, -20)
                    out.append(((r.left, r.top, r.right, r.bottom), hex(ex)))
            return True
        u.EnumWindows(cb, 0)
        return out

    D.abs_move(1000, 400); time.sleep(0.5)
    print("mouse(1000,400):", ov_wins())
    D.abs_move(1500, 600); time.sleep(0.5)
    print("mouse(1500,600):", ov_wins())

    # overlay 开着时真实点击 EDEN 按钮 → 对话框应弹出
    c = D.CDP(9224)
    D.bring_front_eden = None
    from recorder import bring_front
    bring_front(("EDEN", "幻映"))
    time.sleep(0.4)
    r = D.el_center(c, "#btnPick")
    D.human_move(r["x"], r["y"], 0.5)
    D.click()
    time.sleep(2.0)
    h = u.FindWindowW(None, "选择视频 / 图片素材")
    print("dialog after overlay-click:", bool(h))
    if h:
        D.press_key(0x1B)
        time.sleep(0.5)
    # 文件对话框输入完整路径→打开→EDEN 状态
    r2 = D.el_center(c, "#btnPick")
    D.click_at(r2["x"], r2["y"]) if False else None
finally:
    send({"cmd": "quit"})
    time.sleep(0.3)
    ov.terminate()
