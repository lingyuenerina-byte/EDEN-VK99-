# -*- coding: utf-8 -*-
"""demo_lib.py — 录屏演示公共件: CDP 定位 / 真实鼠标 / 高亮 overlay / MCI 音频"""
import ctypes
from ctypes import wintypes
import json
import subprocess
import time
import urllib.request

import websocket

user32 = ctypes.windll.user32
winmm = ctypes.windll.winmm

# ---------- DPI ----------
def dpi_aware():
    try:
        user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
    except Exception:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)

def screen_size():
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

# ---------- 窗口 ----------
def find_hwnd_by_pid(pid):
    EnumWindows = user32.EnumWindows
    GetWindowThreadProcessId = user32.GetWindowThreadProcessId
    result = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, lparam):
        pd = ctypes.c_ulong()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pd))
        if pd.value == pid and user32.IsWindowVisible(hwnd):
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            if r.right - r.left > 200:
                result.append((hwnd, r.left, r.top, r.right, r.bottom))
        return True

    EnumWindows(cb, 0)
    return result  # [(hwnd,left,top,right,bottom)]

def get_pid_by_name(name):
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    pids = []
    for line in out.splitlines():
        parts = line.strip('"').split('","')
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            pids.append(int(parts[1]))
    return pids

# ---------- 鼠标 (SendInput) ----------
INPUT_MOUSE, MOUSEEVENTF_MOVE, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0, 1, 2, 4
INPUT_KEYBOARD, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 1, 2, 4

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_ushort), ("wParamH", ctypes.c_ushort)]

class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("iu", INPUT_UNION)]

def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))

def _minput(flags, x=0, y=0, data=0):
    i = INPUT(); i.type = INPUT_MOUSE
    i.iu.mi = MOUSEINPUT(x, y, data, flags, 0, None)
    return i

def _kinput(flags, vk=0, scan=0):
    i = INPUT(); i.type = INPUT_KEYBOARD
    i.iu.ki = KEYBDINPUT(vk, scan, flags, 0, None)
    return i

def abs_move(x, y):
    """绝对坐标移动: 用 SetCursorPos.
    教训: mouse_event 的 ABSOLUTE|VIRTUALDESK 归一化在多屏跨负坐标虚拟桌面上会被静默忽略,
    光标一动不动也不报错. SetCursorPos 物理坐标(进程 DPI-aware 时) 100% 可靠."""
    if not user32.SetCursorPos(int(x), int(y)):
        raise RuntimeError(f"SetCursorPos failed to {(x, y)}")

def set_mouse_pos(x, y):
    """[workflow_automator 同款] 物理移动鼠标 + 0.1s 到位缓冲"""
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.1)

def hardware_click(double=False):
    """[workflow_automator 同款] 硬件级鼠标点击 (mouse_event, 穿透焦点限制)
    0x0002 左按下 / 0x0004 左抬起; 按下抬起间 0.02s, 双击再间隔 0.06s 模拟人手"""
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.02)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    if double:
        time.sleep(0.06)
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.02)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

def human_move(x, y, ms=650):
    """缓入缓出的人味移动"""
    cur = ctypes.wintypes.POINT(); user32.GetCursorPos(ctypes.byref(cur))
    sx, sy = cur.x, cur.y
    steps = max(12, int(ms / 10))
    t0 = time.perf_counter()
    for i in range(1, steps + 1):
        f = i / steps; e = 1 - (1 - f) ** 3  # ease-out cubic
        abs_move(int(sx + (x - sx) * e), int(sy + (y - sy) * e))
        wait = t0 + ms * f / 1000 - time.perf_counter()
        if wait > 0: time.sleep(wait)
    abs_move(x, y)

def click(x=None, y=None, pre_ms=300, glide=420):
    """重构版: 滑行到位 -> 人手停顿(0.3s, workflow_automator 同款) -> 硬件点击"""
    if x is not None:
        human_move(x, y, glide)
    time.sleep(pre_ms / 1000)
    hardware_click()

def drag(x1, y1, x2, y2, ms=900):
    human_move(x1, y1, 400); time.sleep(0.3)
    user32.mouse_event(0x0002, 0, 0, 0, 0); time.sleep(0.15)
    steps = max(20, int(ms / 10)); t0 = time.perf_counter()
    for i in range(1, steps + 1):
        f = i / steps
        abs_move(int(x1 + (x2 - x1) * f), int(y1 + (y2 - y1) * f))
        wait = t0 + ms * f / 1000 - time.perf_counter()
        if wait > 0: time.sleep(wait)
    time.sleep(0.12)
    user32.mouse_event(0x0004, 0, 0, 0, 0)

def press_key(vk, hold=0.05):
    _send(_kinput(0, vk=vk)); time.sleep(hold); _send(_kinput(KEYEVENTF_KEYUP, vk=vk))

def type_text(s):
    for ch in s:
        i = INPUT(); i.type = INPUT_KEYBOARD
        i.iu.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, None)
        _send(i); time.sleep(0.02)
        _send(_kinput(KEYEVENTF_KEYUP | KEYEVENTF_UNICODE, 0, ord(ch)))
        time.sleep(0.015)

# ---------- CDP ----------
class CDP:
    def __init__(self, port, url_match=""):
        data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3))
        pages = [t for t in data if t.get("type") == "page"]
        if url_match:
            pages = [t for t in pages if url_match in t.get("url", "")] or pages
        self.ws = websocket.create_connection(pages[0]["webSocketDebuggerUrl"], timeout=15,
                                              header=[f"Origin: http://127.0.0.1:{port}"])
        self.id = 0

    def call(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg: raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

def el_center(cdp, selector):
    """元素视口中心 (CSS px) + dpr"""
    return cdp.js("""(() => {
      const el = document.querySelector(%r);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {x: r.left + r.width/2,
              y: r.top + r.height/2,
              w: r.width, h: r.height, dpr: window.devicePixelRatio,
              iw: window.innerWidth, ih: window.innerHeight};
    })()""" % selector)


def el_center_text(cdp, text):
    """按精确文本匹配叶子元素 (官方驱动按钮无 id, 只有文案)"""
    return cdp.js("""(() => {
      const els = [...document.querySelectorAll('button,span,div,li,a')].filter(e =>
        e.childElementCount === 0 && e.textContent.trim() === %r);
      const el = els.find(e => e.offsetParent !== null) || els[0];
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return {x: r.left + r.width/2,
              y: r.top + r.height/2,
              w: r.width, h: r.height, dpr: window.devicePixelRatio,
              iw: window.innerWidth, ih: window.innerHeight};
    })()""" % text)

# ---------- MCI 音频 ----------
_errbuf = ctypes.create_unicode_buffer(256)
def mci(cmd):
    winmm.mciSendStringW(cmd, _errbuf, 255, 0)
    return _errbuf.value if _errbuf.value else ""

def play_wav(path, alias="vo"):
    mci(f"close {alias}")
    mci(f'open "{path}" alias {alias}')
    mci(f"play {alias}")

# ---------- WAV 时长 ----------
import wave as _wave
def wav_dur(path):
    w = _wave.open(path, "rb")
    return w.getnframes() / w.getframerate()

def find_window(keyword):
    """按标题关键字找可见窗口, 返回 (hwnd, title, rect_tuple) 或 None"""
    dpi_aware()
    b = ctypes.create_unicode_buffer(256)
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def cb(h, l):
        if user32.IsWindowVisible(h) and user32.GetWindowTextLengthW(h):
            user32.GetWindowTextW(h, b, 256)
            if keyword in b.value:
                r = wintypes.RECT(); user32.GetWindowRect(h, ctypes.byref(r))
                if r.right - r.left > 200:
                    out.append((h, b.value, (r.left, r.top, r.right, r.bottom)))
        return True
    user32.EnumWindows(cb, 0)
    return out[0] if out else None

def hwnd_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return (r.left, r.top, r.right, r.bottom)

def client_origin(hwnd):
    p = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(p))
    return (p.x, p.y)
