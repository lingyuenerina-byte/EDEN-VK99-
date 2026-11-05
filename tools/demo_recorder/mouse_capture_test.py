# -*- coding: utf-8 -*-
"""mouse_capture_test.py — 录一段「鼠标缓慢划过 btnPick」的裁剪视频, 验证 gdigrab 是否画出光标"""
import os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D, verify_cursor as V, calib_probe as C

here = os.path.dirname(os.path.abspath(__file__))
V.bring_front(("EDEN", "幻映"))
time.sleep(0.5)
info = C.resolve("#btnPick")
x, y = info["screen"]
D.dpi_aware()
D.abs_move(x - 150, y + 60)
time.sleep(0.3)

# 裁剪区域: 以按钮中心 200x120
crop_x, crop_y, cw, ch = x - 100, y - 60, 200, 120
out = os.path.join(here, "mouse_test.mp4")
ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-f", "gdigrab", "-framerate", "15", "-draw_mouse", "1",
                       "-offset_x", str(crop_x), "-offset_y", str(crop_y),
                       "-video_size", f"{cw}x{ch}", "-i", "desktop", "-t", "2", "-y", out])
time.sleep(0.8)
D.human_move(x, y, 700)      # 慢慢移到按钮中心
# 持续小幅抖动, 防止 Windows 空闲隐藏指针
t_end = time.perf_counter() + 1.1
while time.perf_counter() < t_end:
    D.abs_move(x + 2, y); time.sleep(0.2); D.abs_move(x - 2, y + 1); time.sleep(0.2)
D.click()
ff.wait(timeout=10)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", out,
                "-vf", "select=eq(n\\,24)", "-vframes", "1", "-y",
                os.path.join(here, "mouse_frame.png")])
print("done", os.path.getsize(out))
