# -*- coding: utf-8 -*-
"""第四段 CDP 可信点击链实测: 清帧 -> 选择照片 -> 对话框 -> photo1 -> 帧数+1"""
import sys, time
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
w.cdp = {"driver": D.CDP(9223)}

w.do_step({"act": "cdpclick", "sel": "text:删除所有帧"}, 0)
time.sleep(1.2)
t = w.resolve({"sel": "text:确定"})
print("确定 popconfirm:", bool(t))
if t:
    w.do_step({"act": "cdpclick", "sel": "text:确定"}, 0)
    time.sleep(1.5)
w.do_step({"act": "wait_frames", "n": 0, "timeout": 8}, 0)

print("--- 选择照片 ---")
w.do_step({"act": "cdpclick", "sel": "text:选择照片"}, 0)
w.do_step({"act": "dialog_input", "text": "H:\\EDENVK\\assets\\photo1.png"}, 0)
time.sleep(1.0)
w.do_step({"act": "wait_frames", "n": 1, "timeout": 12}, 0)
print("frames:", w.cdp["driver"].js("(function(){var t=document.body.innerText;var i=t.indexOf('帧数');return t.slice(i,i+20)})()"))
