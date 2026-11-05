# probe2: JS click #btnPick 是否能弹出 rfd 对话框
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D
from recorder import Runner, bring_front

R = Runner(lambda *a: None, lambda *a: None)
R.cur_app = "eden"
R.ensure_eden()
R.cleanup_dialogs()
cdp = R.get_cdp("eden")
ok = cdp.js('document.querySelector("#btnPick").click() || 1')
print("js click fired:", ok)
for i in range(20):
    t = cdp.js('document.querySelector("#btnPick").nextElementSibling.textContent')
    for title in ("选择视频 / 图片素材", "打开", "Open"):
        h = D.user32.FindWindowW(None, title)      # 对话框自己的 HWND
        if h:
            print(f"[{i*0.4}s] DIALOG:", title)
            # 只对对话框发 WM_CLOSE。绝不全局 keybd_event(0x1B):
            # 全局 ESC 会落到当前前台窗口, 而 Hermes 桌面端的 Esc = 取消本回合,
            # 会把正在跑这条命令的 terminal 直接打断 (exit 130 / [Command interrupted])。
            D.user32.PostMessageW(h, 0x10, 0, 0)
            time.sleep(0.3)
            print("closed:", not D.user32.FindWindowW(None, title))
            sys.exit(0)
    time.sleep(0.4)
print("no dialog after 8s; picked:", cdp.js('document.querySelector("#btnPick").nextElementSibling.textContent'))
R.close()
