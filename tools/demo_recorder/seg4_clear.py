# -*- coding: utf-8 -*-
"""清帧 -> 选择照片 -> 对话框"""
import sys, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
u = ctypes.windll.user32
tb = ctypes.create_unicode_buffer(128)
cb64 = ctypes.create_unicode_buffer(64)

def snap_all(vis_only=True):
    out = {}
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def _cb(h, l):
        pid = wt.DWORD(); u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if u.IsWindowVisible(h):
            u.GetWindowTextW(h, tb, 128)
            u.GetClassNameW(h, cb64, 64)
            out[int(h)] = (tb.value, cb64.value, pid.value)
        return True
    u.EnumWindows(_cb, 0)
    return out

w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
c = D.CDP(9223)
print("frames now:", c.js("(()=>{const m=document.body.innerText.match(/帧数：[^\\d]*(\\d+)\\/\\d+/);return m?m[1]:'?'})()"))

# 删除所有帧
t = w.resolve({"sel": "text:删除所有帧"})
print("删除所有帧 pt:", t and t["pt"])
if t:
    D.human_move(*t["pt"], 400); D.click(); time.sleep(1.2)
    # 可能弹确定
    ok = w.resolve({"sel": "text:确定"})
    if ok:
        print("有确定按钮:", ok["pt"])
        D.human_move(*ok["pt"], 300); D.click(); time.sleep(1.0)
print("frames after clear:", c.js("(()=>{const m=document.body.innerText.match(/帧数：[^\\d]*(\\d+)\\/\\d+/);return m?m[1]:'?'})()"))

# 选择照片
before = snap_all()
t2 = w.resolve({"sel": "text:选择照片"})
D.human_move(*t2["pt"], 400); D.click()
t0 = time.time()
while time.time() - t0 < 6:
    now = snap_all()
    for h, v in now.items():
        if h not in before and v[2] not in (0,):
            base = now.get(h, ("",))[0]
            if base != "Program Manager" and (int(h) not in [k for k in before]):
                pass
    diffs = [(h,) + v for h, v in now.items() if h not in before]
    if diffs:
        for d0 in diffs:
            print("NEW:", d0)
        break
    time.sleep(0.3)
else:
    print("NO new window after 6s")
