# -*- coding: utf-8 -*-
"""overlay_proc.py — 独立进程演示覆盖层:
- 自绘鼠标箭头(跟随真实光标) + 按下波纹  (gdigrab 抓不到硬件光标, 用假箭头入镜)
- 高亮框: UDP json {"cmd":"hl","x","y","w","h","dur","color"} / {"cmd":"clear"} / {"cmd":"quit"}
- 全屏置顶、点击穿透、透明色背景
"""
import ctypes
import json
import socket
import tkinter as tk

user32 = ctypes.windll.user32
GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = -20, 0x80000, 0x20, 0x80
TRANSPARENT = "#01fe02"
PORT = 9377

class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("eden_demo_overlay")
        vx, vy = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
        vw, vh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
        self.ox, self.oy = vx, vy
        self.root.overrideredirect(True)
        self.root.geometry(f"{vw}x{vh}+{vx}+{vy}")
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.cv = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0)
        self.cv.pack(fill="both", expand=True)
        self.root.update_idletasks()
        hwnd = self._hwnd()
        st = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        self.hls = []      # [(x,y,w,h,deadline,color,pulse)]
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", PORT))
        self.sock.settimeout(0.03)
        import ctypes.wintypes as wt
        self.POINT = wt.POINT()

    def _hwnd(self):
        return self.root.winfo_id() & 0xFFFFFFFF

    def tick(self):
        import time
        import struct
        now = time.time()
        try:
            data, _ = self.sock.recvfrom(4096)
            for line in data.split(b"\n"):
                if not line:
                    continue
                m = json.loads(line)
                if m.get("cmd") == "hl":
                    self.hls.append([m["x"], m["y"], m["w"], m["h"], now + m.get("dur", 2), m.get("color", "#ff4fa3"), m.get("pulse", True)])
                elif m.get("cmd") == "clear":
                    self.hls.clear()
                elif m.get("cmd") == "quit":
                    self.root.destroy()
                    return
        except socket.timeout:
            pass
        self.cv.delete("all")
        self.hls = [h for h in self.hls if h[4] > now]
        for x, y, w, h, dl, color, pulse in self.hls:
            lx, ly = x - self.ox, y - self.oy
            remain = dl - now
            if remain > 1.6:
                self.cv.create_rectangle(lx - 3, ly - 3, lx + w + 3, ly + h + 3, outline=color, width=4)
                if pulse and int(remain * 3) % 2 == 0:
                    self.cv.create_rectangle(lx - 7, ly - 7, lx + w + 7, ly + h + 7, outline=color, width=1)
            elif remain > 0:
                a = max(0.15, min(1, remain / 1.6))
                self.cv.create_rectangle(lx - 3, ly - 3, lx + w + 3, ly + h + 3,
                                         outline=color, width=max(1, int(4 * a)))
        user32.GetCursorPos(ctypes.byref(self.POINT))
        cx, cy = self.POINT.x - self.ox, self.POINT.y - self.oy
        down = user32.GetAsyncKeyState(0x01) & 0x8000
        self.draw_cursor(cx, cy, down)
        self.root.after(33, self.tick)

    def draw_cursor(self, x, y, down):
        s = 1.0
        pts = [(x, y), (x, y + 17 * s), (x + 4, y + 13 * s), (x + 7.5, y + 19 * s),
               (x + 10, y + 18 * s), (x + 6.6, y + 12 * s), (x + 12, y + 12 * s)]
        if down:
            pts = [(x - dx * 0.2, y - dy * 0.2) for dx, dy in pts]
        self.cv.create_polygon(pts, fill="white", outline="black", width=1)
        if down:
            r = 14
            self.cv.create_oval(x - r, y - r + 6, x + r, y + r + 6, outline="#ff4fa3", width=3)

def main():
    ov = Overlay()
    ov.root.after(33, ov.tick)
    ov.root.mainloop()

if __name__ == "__main__":
    import ctypes.wintypes
    main()
