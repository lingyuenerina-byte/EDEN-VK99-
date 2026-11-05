# -*- coding: utf-8 -*-
"""干净重测: 关尽对话框 -> 点驱动选择照片 -> 枚举新窗口标题/pid -> 输入 photo1 -> 帧数"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
b = ctypes.create_unicode_buffer(256)

def snap():
    out = {}
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if u.IsWindowVisible(h) and u.GetWindowTextLengthW(h):
            u.GetWindowTextW(h, b, 256)
            pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
            out[int(h)] = (b.value, pid.value)
        return True
    u.EnumWindows(cb, 0)
    return out

# 1) 关闭一切标题含 选择/打开/Open 的对话框 (post WM_CLOSE)
s = snap()
closed = 0
for h, (t, pid) in s.items():
    if pid in (55004,) or any(k in t for k in ("选择视频", "选择照片", "打开", "Open")):
        cls = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, cls, 64)
        if ("#32770" in cls.value) or ("选择视频 / 图片素材" == t) or t in ("打开", "Open"):
            u.PostMessageW(h, 0x10, 0, 0); closed += 1
time.sleep(1.0)
print("closed dialogs:", closed)

# 2) 驱动窗口 + 点选择照片
w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
w.cdp = {"driver": D.CDP(9223)}
t2 = w.resolve({"sel": "text:选择照片"})
print("选择照片 pt:", t2 and t2["pt"])
before = snap()
D.human_move(*t2["pt"], 500); D.click()

# 3) 3 秒内监控新窗口
new = None
t0 = time.time()
while time.time() - t0 < 4:
    for h, (t, pid) in snap().items():
        if h not in before and t != "Program Manager":
            new = (h, t, pid); break
    if new:
        break
    time.sleep(0.3)
print("NEW WINDOW:", new)
if new:
    u.SetForegroundWindow(new[0]); time.sleep(0.6)
    D.type_text(r"H:\EDENVK\assets\photo1.png"); time.sleep(0.5)
    D.press_key(0x0D); time.sleep(2.5)
    print("frame text:", w.cdp["driver"].js("(()=>{const m=document.body.innerText.match(/帧数：[^\\d]*(\\d+)\\/\\d+/);return m?m[1]:'?'})()"))
