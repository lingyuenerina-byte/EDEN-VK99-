# probe: 真实点击 #btnPick 后枚举所有新窗口标题
import sys, os, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D
from recorder import Runner, bring_front

R = Runner(lambda *a: None, lambda *a: None)
R.cur_app = "eden"
R.ensure_eden()
R.cleanup_dialogs()
R.win = bring_front(("EDEN", "幻映"))
print("win:", bool(R.win))
cdp = R.get_cdp("eden")
s = {"act": "click", "sel": "#btnPick", "app": "eden"}
R.do_step(s, 6)
seen = set()
for i in range(20):
    buf = ctypes.create_unicode_buffer(256)
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if D.user32.IsWindowVisible(h):
            D.user32.GetWindowTextW(h, buf, 256)
            if buf.value and buf.value not in seen:
                seen.add(buf.value)
                print(f"[{i*0.4:4.1f}s] NEW: {buf.value!r} cls_pid")
        return True
    D.user32.EnumWindows(cb, 0)
    time.sleep(0.4)
print("picked now:", cdp.js('document.querySelector("#btnPick").nextElementSibling.textContent'))
