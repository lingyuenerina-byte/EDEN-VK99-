# -*- coding: utf-8 -*-
"""overlay_v2.py — 演示覆盖层(多小窗方案)
教训: tkinter transparentcolor 在跨整个虚拟桌面的超大窗口上会被 DWM 合成成纯黑,
     必须用小窗口。v2: 跟随鼠标的假箭头小窗 + 每个高亮框一个短命窗口。
UDP 127.0.0.1:9377: {"cmd":"hl","x","y","w","h","dur","color"} / clear / quit
"""
import ctypes
import ctypes.wintypes as wt
import json
import socket
import time
import tkinter as tk

u = ctypes.windll.user32
# python.exe 无 DPI manifest: 必须显式 awareness, 否则 tk geometry 坐标会被
# 系统缩放虚拟化(乘 1.5), 高亮框画偏且录屏抓不到. pythonw 清单自带会静默失败.
try:
    u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # PER_MONITOR_AWARE_V2
except Exception:
    u.SetProcessDPIAware()
# 注意: pythonw.exe 清单自带 per-monitor_v2, SetProcessDpiAwareness 调用会静默失败.
# 统一用 tkinter(winfo) 逻辑坐标移动窗口, GetCursorPos 物理坐标 -> 除以缩放.
GWL_EXSTYLE, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_LAYERED, GA_ROOT = -20, 0x20, 0x80, 0x80000, 3
TRANS = "#01fe02"
PORT = 9377
AW = 140   # 箭头窗尺寸
AC = AW // 2

def make_clickthrough(tl):
    tl.update_idletasks()
    hwnd = u.GetAncestor(tl.winfo_id(), GA_ROOT)
    st = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
    u.SetWindowLongW(hwnd, GWL_EXSTYLE, st | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED)
    # SWP_NOSIZE|SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE|SWP_SHOWWINDOW
    u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0040)
    if not u.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TRANSPARENT:
        def retry():
            s2 = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u.SetWindowLongW(hwnd, GWL_EXSTYLE, s2 | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW)
        tl.after(60, retry)
    return hwnd

class Overlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("eden_demo_overlay")
        self.root.withdraw()
        self.scale = self.root.winfo_fpixels("1i") / 72.0   # 系统缩放 150%->1.5
        self.pt = wt.POINT()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", PORT))
        self.sock.settimeout(0.02)
        # 箭头窗(跟随鼠标)
        self.aw = tk.Toplevel(self.root)
        self.aw.overrideredirect(True)
        self.aw.attributes("-transparentcolor", TRANS)
        self.aw.attributes("-topmost", True)
        self.acv = tk.Canvas(self.aw, bg=TRANS, highlightthickness=0)
        self.acv.pack(fill="both", expand=True)
        self.aw.geometry(f"{AW}x{AW}+-{AW}+-{AW}")
        make_clickthrough(self.aw)
        self._arrow_pos = None
        self.aw_hwnd = u.GetAncestor(self.aw.winfo_id(), GA_ROOT)
        self.hls = []  # (toplevel, canvas, deadline, t0, geom)

    def tick(self):
        try:
            self._tick()
        except Exception as e:
            print("tick err:", e)
        if self.root.winfo_exists():
            self.root.after(30, self.tick)

    def _tick(self):
        now = time.time()
        try:
            data, _ = self.sock.recvfrom(4096)
            for line in data.split(b"\n"):
                if not line:
                    continue
                m = json.loads(line)
                cmd = m.get("cmd")
                if cmd == "hl":
                    self.spawn_hl(m)
                elif cmd == "clear":
                    self.kill_hls()
                elif cmd == "ripple":
                    self._ripple_t = time.time()
                elif cmd == "quit":
                    self.root.destroy()
                    return
        except socket.timeout:
            pass
        u.GetCursorPos(ctypes.byref(self.pt))
        tx, ty = self.pt.x - AC, self.pt.y - AC
        cur = self._arrow_pos
        if cur != (tx, ty):
            hwnd = u.GetAncestor(self.aw.winfo_id(), GA_ROOT)
            u.MoveWindow(hwnd, tx, ty, AW, AW, True)
            self._arrow_pos = (tx, ty)
        down = bool(u.GetAsyncKeyState(0x01) & 0x8000)
        if down and not getattr(self, "_down_prev", False):
            self._ripple_t = time.time()
        self._down_prev = down
        self.draw_arrow(down)
        keep = []
        for w, cv, dl, t0, geom in self.hls:
            if now < dl:
                self.redraw_hl(cv, dl - now, t0, geom)
                keep.append((w, cv, dl, t0, geom))
            else:
                w.destroy()
        self.hls = keep

    def draw_arrow(self, down):
        cv = self.acv
        cv.delete("all")
        x, y = AC, AC
        off = 2 if down else 0
        pts = [(x + off, y + off), (x + off, y + 20 + off), (x + 4 + off, y + 16 + off),
               (x + 8 + off, y + 23 + off), (x + 11 + off, y + 22 + off),
               (x + 7 + off, y + 15 + off), (x + 13 + off, y + 15 + off)]
        rt = getattr(self, "_ripple_t", 0)
        if rt:
            dt = time.time() - rt
            if dt < 0.3:
                rr = 10 + int(dt / 0.3 * 26)
                col = "#ff9ecb" if dt > 0.15 else "#ff4fa3"
                cv.create_oval(x - rr, y - rr, x + rr, y + rr, outline=col, width=3)
            else:
                self._ripple_t = 0
        cv.create_oval(x - 12, y - 12, x + 12, y + 12,
                       fill="#ffd1e8", outline="", stipple="gray25")
        shadow = [(px + 2, py + 2) for px, py in pts]
        cv.create_polygon(shadow, fill="#555555", outline="", stipple="gray50")
        cv.create_polygon(pts, fill="white", outline="black", width=2)

    def spawn_hl(self, m):
        import math
        x, y, w, h = m["x"], m["y"], m["w"], m["h"]
        dur = m.get("dur", 1.0)
        color = m.get("color", "#ff4fa3")
        label = m.get("label", "")
        pad = 22
        lab_h = 40 if label else 0
        tl = tk.Toplevel(self.root)
        tl.overrideredirect(True)
        tl.attributes("-transparentcolor", TRANS)
        tl.attributes("-topmost", True)
        cv = tk.Canvas(tl, bg=TRANS, highlightthickness=0)
        cv.pack(fill="both", expand=True)
        tl.geometry(f"{w + pad * 2}x{h + pad * 2 + lab_h}+{x - pad}+{y - pad - lab_h}")
        make_clickthrough(tl)
        now = time.time()
        geom = (pad, pad + lab_h, w, h, color, label)
        self.redraw_hl(cv, dur, now, geom)
        self.hls.append((tl, cv, now + dur, now, geom))

    @staticmethod
    def _round_rect(cv, x1, y1, x2, y2, r, **kw):
        pts = [(x1 + r, y1), (x2 - r, y1), (x2, y1), (x2, y1 + r), (x2, y2 - r),
               (x2, y2), (x2 - r, y2), (x1 + r, y2), (x1, y2), (x1, y2 - r),
               (x1, y1 + r), (x1, y1)]
        return cv.create_line(*pts, smooth=True, capstyle="round", joinstyle="round", **kw)

    def redraw_hl(self, cv, remain, t0, geom):
        import math
        pad, top, w, h, color, label = geom
        cv.delete("all")
        age = time.time() - t0
        if remain > 1.2:
            pulse = math.sin(age * 4.0) * 0.5 + 0.5           # 呼吸 0..1
            r = 12 + int(pulse * 3)
            # 外光晕: 三层递减
            self._round_rect(cv, pad - 9, top - 9, pad + w + 9, top + h + 9, r + 4,
                             fill=color, width=1)
            self._round_rect(cv, pad - 6, top - 6, pad + w + 6, top + h + 6, r + 2,
                             fill=color, width=2)
            self._round_rect(cv, pad - 2, top - 2, pad + w + 2, top + h + 2, r,
                             fill=color, width=max(2, 3 + int(pulse * 2)))
            if label:
                tw = len(label) * 15 + 28
                bx1, by1 = pad + w / 2 - tw / 2, 4
                bx2, by2 = pad + w / 2 + tw / 2, 34
                self._round_rect(cv, bx1, by1, bx2, by2, 15, fill=color, width=2)
                cv.create_rectangle(bx1 + 6, by1 + 6, bx2 - 6, by2 - 6,
                                    fill=color, outline=color)
                cv.create_text(pad + w / 2, 19, text=label, fill="white",
                               font=("Microsoft YaHei UI", 10, "bold"))
        else:
            a = max(0.1, remain / 1.2)
            self._round_rect(cv, pad - 2, top - 2, pad + w + 2, top + h + 2, 12,
                             fill=color, width=max(1, int(4 * a)))
            if label:
                tw = len(label) * 15 + 28
                cv.create_rectangle(pad + w / 2 - tw / 2, 4, pad + w / 2 + tw / 2, 34,
                                    fill=color, outline=color)
                cv.create_text(pad + w / 2, 19, text=label, fill="white",
                               font=("Microsoft YaHei UI", 10, "bold"))

    def kill_hls(self):
        for w, cv, dl, t0, geom in self.hls:
            w.destroy()
        self.hls = []

def main():
    ov = Overlay()
    ov.root.after(30, ov.tick)
    ov.root.mainloop()

if __name__ == "__main__":
    main()
