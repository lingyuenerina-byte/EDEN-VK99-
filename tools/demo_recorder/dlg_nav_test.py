# 最小复现: 驱动"选择照片"对话框两步导航截图验证
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D
from recorder import Runner, VK, bring_front

R = Runner(lambda *a: None, lambda *a: None)
R.cur_app = "driver"
R.win = bring_front(("Valkyrie Driver",))
R.recover_driver()
R.win = bring_front(("Valkyrie Driver",))
R.cleanup_dialogs()
cdp = R.get_cdp("driver")
# 复位: 屏幕设置 + 删除所有帧 + 点选择照片
R.do_step({"act": "cdpclick", "sel": "text:屏幕设置", "app": "driver"}, 1)
time.sleep(1.5)
R.do_step({"act": "msclick", "sel": "text:删除所有帧", "app": "driver"}, 1)
time.sleep(1.2)
R.do_step({"act": "msclick", "sel": "text:选择照片", "app": "driver"}, 1)
time.sleep(1.2)
dlg = None
for _ in range(15):
    for title in ("选择视频 / 图片素材", "打开", "Open"):
        h = D.user32.FindWindowW(None, title)
        if h:
            dlg = (title, int(h))
            break
    if dlg:
        break
    time.sleep(0.3)
print("dialog:", dlg)
if not dlg:
    sys.exit(1)
D.user32.SetForegroundWindow(dlg[1])
time.sleep(0.8)
D.type_text("H:\\EDENVK\\assets")
time.sleep(0.3)
D.press_key(VK["ENTER"])
time.sleep(1.8)
from PIL import ImageGrab
g = wt = None
import ctypes.wintypes as wtt
r = wtt.RECT()
D.user32.GetWindowRect(dlg[1], ctypes_byref := __import__("ctypes").byref(r))
ImageGrab.grab(bbox=(r.left, r.top, r.right, r.bottom)).save("dlg_nav.png")
print("saved dlg_nav.png rect:", (r.left, r.top, r.right, r.bottom))
# 读文件名框当前内容与列表项
# 直接再走第二步看能否选中
D.type_text("photo1.png")
time.sleep(0.3)
D.press_key(VK["ENTER"])
time.sleep(1.5)
t = cdp.js("(function(){var s=document.body.innerText;var i=s.indexOf('\u5e27\u6570\uff1a');return i<0?'NO':s.slice(i,i+8)})()")
print("frames after:", repr(t))
R.close()
