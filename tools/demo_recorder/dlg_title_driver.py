# probe: 官方驱动「选择照片」打开的原生对话框标题是什么
import sys, os, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D
from recorder import Runner, bring_front

R = Runner(lambda *a: None, lambda *a: None)
R.cur_app = "driver"
R.cleanup_dialogs()
R.win = bring_front(("Valkyrie Driver",))
print("win:", bool(R.win))
cdp = R.get_cdp("driver")
R.do_step({"act": "cdpclick", "sel": "text:屏幕设置"}, 2)
time.sleep(1.5)
R.do_step({"act": "msclick", "sel": "text:选择照片"}, 3)
seen = set()
buf = ctypes.create_unicode_buffer(256)
for i in range(15):
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if D.user32.IsWindowVisible(h):
            D.user32.GetWindowTextW(h, buf, 256)
            if buf.value and buf.value not in seen:
                seen.add(buf.value)
                print(f"[{i*0.4:4.1f}s] {buf.value!r}")
        return True
    D.user32.EnumWindows(cb, 0)
    print("---")
    time.sleep(0.4)
