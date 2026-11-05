# -*- coding: utf-8 -*-
"""枚举文件对话框 UIA 结构: 盘符树名/文件夹项名, 为 dialog_click 定位选择器"""
import sys, time, ctypes
sys.path.insert(0, ".")
import demo_lib as D
from pywinauto import Desktop

c = D.CDP(9224)
c.js("document.querySelector('#btnPick').click()")
time.sleep(1.2)
dlg = Desktop(backend="uia").window(title="选择视频 / 图片素材")
dw = dlg.wait("visible ready", timeout=3)
print("DLG:", dw.window_text())
for ct in ("TreeItem", "ListItem", "DataItem", "Group", "Tab"):
    try:
        items = dw.descendants(control_type=ct)
        print(ct, len(items), [i.window_text()[:24] for i in items[:40]])
    except Exception as e:
        print(ct, "err", str(e)[:60])
hwnd = dw.handle
time.sleep(0.5)
ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
print("closed")
