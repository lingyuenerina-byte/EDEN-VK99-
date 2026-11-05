# -*- coding: utf-8 -*-
# 小步视觉验证: overlay 假光标 + 高亮框 是否被 gdigrab 录到
import subprocess, sys, os, time, socket, json, ctypes
HERE = r"C:\Users\Lingy\vk99screen\tools\demo_recorder"
sys.path.insert(0, HERE)
import demo_lib as D
os.chdir(HERE)

py = r"I:\dania-tts\gsv\.venv\Scripts\pythonw.exe"
if not os.path.exists(py):
    py = r"I:\dania-tts\gsv\.venv\Scripts\python.exe"
ov = subprocess.Popen([py, "overlay_v2.py"], creationflags=0x00000008)
time.sleep(1.6)
import ctypes.wintypes as _wt
wins = []
for _ in range(20):
    pids = D.get_pid_by_name("eden.exe")
    if pids:
        wins = D.find_hwnd_by_pid(pids[0])
    if wins:
        break
    time.sleep(0.5)
if not wins:
    raise SystemExit("eden 窗口找不到")
hwnd, l, t, r, b = wins[0]
D.user32.ShowWindow(hwnd, 9); D.user32.SetForegroundWindow(hwnd)
time.sleep(0.4)
ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error",
                       "-f", "gdigrab", "-framerate", "15", "-draw_mouse", "0",
                       "-offset_x", str(l), "-offset_y", str(t),
                       "-video_size", f"{r-l}x{b-t}", "-i", "desktop",
                       "-t", "4", "-y", "ov_test.mp4"])
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
lx, ly = l + 400, t + 300
s.sendto(json.dumps({"cmd": "hl", "x": l + 300, "y": t + 200, "w": 320, "h": 220,
                     "dur": 2.2, "color": "#ff4fa3"}).encode(), ("127.0.0.1", 9377))
for i in range(20):
    D.abs_move(lx + int(120 * time.sin(i * 0.35) if hasattr(time, 'sin') else 120 * __import__('math').sin(i * 0.35)),
               ly + int(80 * __import__('math').cos(i * 0.35)))
    time.sleep(0.18)
ff.wait()
s.sendto(b'{"cmd":"quit"}', ("127.0.0.1", 9377))
time.sleep(0.5)
ov.terminate()
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "ov_test.mp4",
                "-vf", "select=eq(n\\,40)", "-vframes", "1", "-y", "ov_frame.png"])
print("mp4 size:", os.path.getsize("ov_test.mp4"))
