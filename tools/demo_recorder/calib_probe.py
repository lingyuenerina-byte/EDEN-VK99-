# -*- coding: utf-8 -*-
"""calib_probe.py — 重启 EDEN 带 CDP 口, 校准屏幕坐标, 把光标放到指定 selector 中心"""
import ctypes, ctypes.wintypes as wintypes, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D

EDEN_EXE = r"C:\Users\Lingy\vk99screen\eden-tauri\src-tauri\target\release\eden.exe"
CDP_PORT = 9224

def ensure_eden():
    try:
        D.CDP(CDP_PORT)
        return
    except Exception:
        pass
    for pid in D.get_pid_by_name("eden.exe"):
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    time.sleep(1.2)
    env = dict(os.environ,
               WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=f"--remote-debugging-port={CDP_PORT} --remote-allow-origins=*")
    subprocess.Popen(EDEN_EXE, env=env, creationflags=0x00000008)
    for _ in range(30):
        time.sleep(1.5)
        try:
            D.CDP(CDP_PORT); return
        except Exception:
            continue
    raise SystemExit("EDEN CDP 起不来")

def eden_window():
    D.dpi_aware()
    pids = D.get_pid_by_name("eden.exe")
    for pid in pids:
        for hwnd, l, t, r, b in D.find_hwnd_by_pid(pid):
            pt = ctypes.wintypes.POINT(0, 0)
            D.user32.ClientToScreen(hwnd, ctypes.byref(pt))
            return hwnd, l, t, r, b, pt.x, pt.y
    raise SystemExit("找不到 EDEN 窗口")

def resolve(selector):
    """selector → 屏幕物理坐标 (中心 + 尺寸)"""
    cdp = D.CDP(CDP_PORT)
    c = D.el_center(cdp, selector)
    if not c: return None
    hwnd, wl, wt, wr, wb, vx, vy = eden_window()
    dpr = c["dpr"]
    sx = vx + c["x"] * dpr
    sy = vy + c["y"] * dpr
    return {"screen": (int(sx), int(sy)), "size": (int(c["w"]*dpr), int(c["h"]*dpr)),
            "dpr": dpr, "viewport": (vx, vy), "win": (wl, wt, wr, wb)}

if __name__ == "__main__":
    ensure_eden()
    sel = sys.argv[1] if len(sys.argv) > 1 else "#btnPick"
    info = resolve(sel)
    print(sel, "->", info)
    if info and len(sys.argv) > 2 and sys.argv[2] == "cursor":
        D.dpi_aware()
        D.abs_move(*info["screen"])
        print("cursor moved to", info["screen"])
