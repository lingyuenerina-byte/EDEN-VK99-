# -*- coding: utf-8 -*-
"""verify_cursor.py — 把目标窗口置前, 光标移到 selector 中心, gdigrab 裁剪截图验证"""
import sys, os, time, ctypes, ctypes.wintypes as wt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D
import calib_probe as C

def bring_front(keyword):
    D.dpi_aware()
    b = ctypes.create_unicode_buffer(256)
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if D.user32.IsWindowVisible(h) and D.user32.GetWindowTextLengthW(h):
            D.user32.GetWindowTextW(h, b, 256)
            r = wt.RECT(); D.user32.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 250 and any(k in b.value for k in keyword):
                out.append((h, b.value, (r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True
    D.user32.EnumWindows(cb, 0)
    if not out:
        return None
    h, title, rect = out[0]
    D.user32.ShowWindow(h, 9)      # SW_RESTORE
    D.user32.SetForegroundWindow(h)
    D.user32.BringWindowToTop(h)
    time.sleep(0.4)
    return h, title, rect

if __name__ == "__main__":
    sel = sys.argv[1] if len(sys.argv) > 1 else "#btnPick"
    r = bring_front(("EDEN", "幻映"))
    print("front:", r)
    info = C.resolve(sel)
    print("resolve:", sel, info)
    if info:
        D.abs_move(*info["screen"])
        time.sleep(0.5)
        import subprocess
        x, y, w, hh = r[2]
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shot_verify.png")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "gdigrab",
                        "-framerate", "10", "-offset_x", str(x), "-offset_y", str(y),
                        "-video_size", f"{w}x{hh}", "-i", "desktop", "-frames:v", "1", "-y", out])
        print("saved", out, os.path.getsize(out))
