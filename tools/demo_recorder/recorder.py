# -*- coding: utf-8 -*-
"""recorder.py — EDEN 首发视频自动演示录制器
点开始 → 置顶目标窗口 → ffmpeg 录窗口区域 → 按 H:/EDENVK/语音/<段> 的分条音频逐条:
播放音频 → 按 demo_plan.json 时间轴动鼠标/高亮 → 音频刚好放完 → 停 2 秒 → 下一条
用法: python recorder.py
"""
import ctypes
import ctypes.wintypes as wt
import glob
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D

HERE = os.path.dirname(os.path.abspath(__file__))
VO_ROOT = r"H:\EDENVK\语音"
OUT_DIR = r"H:\EDENVK\record"
PLAN_PATH = os.path.join(HERE, "demo_plan.json")
EDEN_EXE = r"C:\Users\Lingy\vk99screen\eden-tauri\src-tauri\target\release\eden.exe"
CDP_PORTS = {"eden": 9224, "driver": 9223}
VK = {"SPACE": 0x20, "ENTER": 0x0D, "ESC": 0x1B}

# ---------- 窗口 ----------
def bring_front(keyword):
    D.dpi_aware()
    b = ctypes.create_unicode_buffer(256)
    out = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, l):
        if D.user32.IsWindowVisible(h) and D.user32.GetWindowTextLengthW(h):
            D.user32.GetWindowTextW(h, b, 256)
            if any(k in b.value for k in keyword) and "编辑器" not in b.value:
                out.append((h, b.value))
        return True
    D.user32.EnumWindows(cb, 0)
    if not out:
        return None
    h, title = out[0]
    if "Valkyrie" in title:
        D.user32.ShowWindow(h, 3)  # SW_MAXIMIZE: 窗口太矮时提示文字会盖住底部按钮
        time.sleep(0.5)
    else:
        D.user32.ShowWindow(h, 9)  # SW_RESTORE: 最小化的也拉回正常尺寸
        time.sleep(0.3)
    D.user32.SetForegroundWindow(h)
    D.user32.BringWindowToTop(h)
    time.sleep(0.35)
    r = wt.RECT(); D.user32.GetWindowRect(h, ctypes.byref(r))
    pt = wt.POINT(0, 0)
    D.user32.ClientToScreen(h, ctypes.byref(pt))
    return {"hwnd": h, "title": title, "rect": (r.left, r.top, r.right, r.bottom),
            "client": (pt.x, pt.y)}


class Runner:
    def __init__(self, gui_log, gui_status):
        self.log = gui_log
        self.status = gui_status
        self.abort = threading.Event()
        self.plan = json.load(open(PLAN_PATH, encoding="utf-8"))
        self.assets = self.plan.get("assets", {})
        self.cdp = {}
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ov_proc = None
        self.win = None  # 当前段目标窗口信息

    # ---------- 基础设施 ----------
    def ensure_eden(self):
        try:
            D.CDP(CDP_PORTS["eden"]); return
        except Exception:
            pass
        for pid in D.get_pid_by_name("eden.exe"):
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
        time.sleep(1.2)
        env = dict(os.environ, WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS=
                   f"--remote-debugging-port={CDP_PORTS['eden']} --remote-allow-origins=*")
        subprocess.Popen(EDEN_EXE, env=env, creationflags=0x00000008)
        for _ in range(30):
            time.sleep(1.5)
            try:
                D.CDP(CDP_PORTS["eden"]); self.log("EDEN 已带调试口重启")
                return
            except Exception:
                continue
        raise RuntimeError("EDEN CDP 起不来")

    def get_cdp(self, app):
        if app not in self.cdp:
            self.cdp[app] = D.CDP(CDP_PORTS[app])
        return self.cdp[app]

    def start_overlay(self):
        py = sys.executable
        if py.endswith("pythonw.exe") or not py.endswith(".exe"):
            pass
        ov_cmd = [py, os.path.join(HERE, "overlay_v2.py")]
        self.ov_proc = subprocess.Popen(ov_cmd, creationflags=0x00000008)
        time.sleep(1.2)

    def stop_overlay(self):
        try:
            self.udp.sendto(b'{"cmd":"quit"}', ("127.0.0.1", 9377))
        except Exception:
            pass
        if self.ov_proc:
            time.sleep(0.4)
            self.ov_proc.terminate()

    # ---------- 坐标 ----------
    def _dismiss_toast(self, app):
        """驱动页更新通知(如 v2.1.3)会盖住按钮, 真实坐标点击前先从 DOM 关掉它"""
        if app != "driver":
            return
        try:
            r = self.get_cdp("driver").js("""(() => {
              const leaf = [...document.querySelectorAll('*')].find(e =>
                e.childElementCount === 0 && (e.textContent || '').includes('官网下载'));
              if (!leaf) return 0;
              let box = leaf;
              for (let i = 0; i < 6 && box.parentElement; i++) {
                box = box.parentElement;
                if ((box.className || '').toString().match(/toast|notice|message|modal|dialog/)) break;
              }
              const x = box.querySelector('[class*=close], [aria-label*=关闭], .el-icon-close') ||
                        [...box.querySelectorAll('*')].find(b => b.childElementCount === 0 &&
                          (b.title || b.textContent || '').trim() === '关闭');
              if (x) { x.click(); return 1; }
              box.remove(); return 2;
            })()""")
            if r:
                self.log(f"  已关掉驱动弹窗 (方式{r})")
                time.sleep(0.6)
        except Exception:
            pass

    def resolve(self, target):
        app = target.get("app", self.cur_app)
        sel = target.get("sel")
        if sel and sel.startswith("text:"):
            c = D.el_center_text(self.get_cdp(app), sel[5:])
        elif sel:
            c = D.el_center(self.get_cdp(app), sel)
        else:
            c = None
        if sel and not c:
            return None
        if sel:
            vx, vy = self.win["client"]
            dpr = c["dpr"]
            cx = vx + c["x"] * dpr
            cy = vy + c["y"] * dpr
            fx, fy = target.get("fx", 0.5), target.get("fy", 0.5)
            px = vx + (c["x"] - c["w"] / 2 + c["w"] * fx) * dpr
            py = vy + (c["y"] - c["h"] / 2 + c["h"] * fy) * dpr
            box = (vx + (c["x"] - c["w"] / 2) * dpr, vy + (c["y"] - c["h"] / 2) * dpr,
                   c["w"] * dpr, c["h"] * dpr)
            return {"pt": (int(px), int(py)), "center": (int(cx), int(cy)),
                    "css": (c["x"], c["y"]),
                    "box": [int(box[0]), int(box[1]), int(box[2]), int(box[3])]}
        if target.get("win"):
            l, t, r, b = self.win["rect"]
            fx, fy = target.get("frac", [0.5, 0.5])
            return {"pt": (int(l + (r - l) * fx), int(t + (b - t) * fy)),
                    "box": [l, t, r - l, b - t]}
        return {"pt": tuple(target["xy"]), "box": None}

    def hl(self, box, dur=1.0, color="#ff4fa3", label=""):
        if not box:
            return
        m = json.dumps({"cmd": "hl", "x": box[0], "y": box[1], "w": box[2], "h": box[3],
                        "dur": dur, "color": color, "label": label})
        self.udp.sendto(m.encode(), ("127.0.0.1", 9377))

    def wait_dom(self, sel, state, timeout):
        js_map = {"!disabled": f"(()=>{{const e=document.querySelector('{sel}');return !!e&&!e.disabled}})()",
                  "true": f"(()=>{{const e=document.querySelector('{sel}');return !!e}})()",
                  "visible": f"(()=>{{const e=document.querySelector('{sel}');return !!(e&&e.offsetParent)}})()",
                  "hidden": f"(()=>{{const e=document.querySelector('{sel}');return !e||!e.offsetParent}})()"}
        expr = js_map.get(state, js_map["true"])
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < timeout and not self.abort.is_set():
            try:
                if self.get_cdp(self.cur_app).js(expr):
                    return True
            except Exception:
                pass
            time.sleep(0.4)
        self.log(f"  ⚠ wait_dom {sel} [{state}] 超时 {timeout}s")
        return False

    # ---------- 步骤 ----------
    def do_step(self, s, dur):
        if self.abort.is_set():
            return
        act = s["act"]
        if act in ("move", "click"):
            tgt = self.resolve(s)
            if not tgt:
                self.log(f"  ⚠ 找不到 {s.get('sel')}")
                return
            if act == "move":
                D.human_move(*tgt["pt"], ms=s.get("ms", 700))
            else:
                if s.get("allow_disabled"):
                    e = self.get_cdp(s.get("app", self.cur_app)).js(
                        f"(()=>{{const x=document.querySelector('{s['sel']}');return x?x.disabled:null}})()")
                    if e is True:
                        self.log(f"  ⚠ {s['sel']} 仍禁用, 跳过点击")
                        return
                D.click(*tgt["pt"])
        elif act == "drag_seg":
            t = self.resolve({"sel": s.get("sel", "#tlSeg")})
            if t:
                x, y = t["center"]
                D.drag(x, y, x + s.get("dx", 100), y, ms=s.get("ms", 900))
        elif act == "hl":
            t = self.resolve(s)
            if t:
                self.hl(t["box"], dur=s.get("dur", 1.0))  # 纯教程: 不显示台词文字(PR配字幕)
        elif act == "cdpclick":
            # 驱动 React 菜单不认合成鼠标事件, 只认 element.click()
            cdp = self.get_cdp(s.get("app", self.cur_app))
            sel = s.get("sel", "")
            if sel.startswith("text:"):
                txt = sel[5:].replace("'", "\\'")
                ok = cdp.js(
                    "(function(){var els=[...document.querySelectorAll('*')].filter(function(e){"
                    "return e.childElementCount===0&&e.textContent.trim()==='" + txt + "'});"
                    "var t=els.find(function(e){return e.offsetParent})||els[0];if(!t)return 0;"
                    "var b=t.closest('button,li,[class*=menu-item-text],[class*=button]')||t;b.click();return 1})()")
            else:
                ok = cdp.js("(function(){var t=document.querySelector('" + sel +
                            "');if(!t||!t.offsetParent)return 0;t.click();return 1})()")
            if not ok:
                if not s.get("soft"):
                    self.log(f"  ⚠ cdpclick 找不到 {sel}")
            # 假光标移到 + 纯视觉波纹 (不发真实点击, 避免二次触发)
            tgt = self.resolve(s)
            if tgt and tgt.get("box"):
                b = tgt["box"]
                D.human_move(b[0] + b[2] // 2, b[1] + b[3] // 2, ms=400)
                self.udp.sendto(json.dumps({"cmd": "ripple"}).encode(),
                                ("127.0.0.1", 9377))
        elif act in ("physclick", "msclick"):
            # [底层重构] 全部走 workflow_automator 同款硬件路径:
            # SetCursorPos/mouse_event, 不碰 CDP 伪事件. 可见滑行(教程观感) + 人手停顿 + 硬件点击
            self._dismiss_toast(s.get("app", self.cur_app))
            tgt = self.resolve(s) if s.get("sel") else None
            if tgt:
                sx, sy = tgt["css"]
                if tgt.get("box"):
                    b = tgt["box"]
                    sx, sy = b[0] + b[2] // 2, b[1] + b[3] // 2
            elif s.get("x") is not None:
                sx, sy = float(s["x"]), float(s["y"])
            else:
                self.log(f"  ⚠ 找不到 {s.get('sel')}")
                return
            glide = int(s.get("glide", 500))
            if glide > 0:
                D.human_move(sx, sy, ms=glide)      # 可见的人味滑行
            else:
                D.set_mouse_pos(sx, sy)             # 瞬移 (0.1s 到位缓冲)
            time.sleep(float(s.get("dwell", 0.3)))  # 人手停顿
            D.hardware_click(double=bool(s.get("double")))
            time.sleep(float(s.get("settle", 1.0)))
            _h = D.user32.FindWindowW(None, "打开") or D.user32.FindWindowW(None, "选择视频 / 图片素材")
            self.log(f"  ▪ {act}({int(sx)},{int(sy)}) sel={s.get('sel')} 对话框={'开' if _h else '未开'}")
            self.udp.sendto(json.dumps({"cmd": "ripple", "x": int(sx), "y": int(sy)}).encode(),
                            ("127.0.0.1", 9377))
        elif act == "wait_frames":
            want = s.get("n")
            t0 = time.perf_counter()
            ok = False
            while time.perf_counter() - t0 < s.get("timeout", 15) and not self.abort.is_set():
                v = self.get_cdp("driver").js(
                    "(function(){var t=document.body.innerText;var i=t.indexOf('\\u5e27\\u6570\\uff1a');if(i<0)return -1;"
                    "var d=t.slice(i).replace(/[^0-9]/g,'');return d?parseInt(d.slice(0,3),10):-1;})()")
                if v is not None and v >= 0 and (want is None or v >= want):
                    ok = True
                    break
                time.sleep(0.5)
            if not ok:
                self.log(f"  ⚠ wait_frames {want} 超时")
        elif act == "key":
            D.press_key(VK.get(s.get("vk"), 0x20))
        elif act in ("dialog_input", "dialog_nav"):
            path = self.assets.get(s.get("asset"), s.get("text", ""))
            # 等系统文件对话框出现(最多3s)
            import ctypes.wintypes
            t0 = time.perf_counter()
            got = False
            while time.perf_counter() - t0 < 3.0:
                for title in ("选择视频 / 图片素材", "打开", "Open"):
                    hh = D.user32.FindWindowW(None, title)
                    if hh:
                        got = title
                        D.user32.SetForegroundWindow(int(hh))
                        break
                if got:
                    break
                time.sleep(0.2)
            if not got:
                self.log("  ⚠ 未见文件对话框, 拒接输入 (防止打进页面)")
                return
            time.sleep(0.6)
            import os
            if act == "dialog_nav":
                # 教程式两步: 先打开素材文件夹展示, 再选文件 (导航必须反斜杠, 正斜杠报"文件名无效")
                adir = os.path.dirname(path).replace("/", "\\")
                if adir and s.get("show_dir", True):
                    D.type_text(adir)
                    time.sleep(0.25)
                    D.press_key(VK["ENTER"])
                    time.sleep(s.get("dwell", 1.6))
                D.type_text(os.path.basename(path) if adir else path)
            else:
                # 一步直填完整路径 (对话框接受带正斜杠的完整文件路径)
                D.type_text(path)
            time.sleep(0.25)
            D.press_key(VK["ENTER"])
            time.sleep(0.6)
            # 兜底: 若对话框还在(名字未确认), 再回车一次
            for t2 in ("选择视频 / 图片素材", "打开", "Open"):
                h = D.user32.FindWindowW(None, t2)
                if h:
                    D.press_key(VK["ENTER"])
                    break
        elif act == "dialog_click":
            # 纯鼠标教程: 树里点盘符 -> 双击文件夹 -> 单击文件 -> 点「打开」, 找不到就退回键盘直填
            import os as _os
            path = self.assets.get(s.get("asset"), s.get("text", ""))
            if not self._uia_click_dialog(path, s):
                s2 = dict(s); s2["act"] = "dialog_nav"
                self.do_step(s2, dur)
        elif act == "wait":
            time.sleep(s.get("sec", 1))
        elif act == "wait_dom":
            self.wait_dom(s["sel"], s.get("state", "true"), s.get("timeout", 10))
        elif act == "move_win":
            tgt = self.resolve({"win": True, "frac": s.get("frac", [0.5, 0.5])})
            D.human_move(*tgt["pt"], ms=s.get("ms", 700))

    # ---------- 录制 ----------
    def start_ffmpeg(self, rect, out):
        l, t, r, b = rect
        w, h = r - l, b - t
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "0",
               "-offset_x", str(l), "-offset_y", str(t),
               "-video_size", f"{w}x{h}", "-i", "desktop",
               "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-y", out]
        ff_flags = 0x08000000 if os.name == "nt" else 0
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, creationflags=ff_flags)

    # ---------- 主流程 ----------
    def load_clips(self, segment):
        d = os.path.join(VO_ROOT, segment)
        files = []
        for f in glob.glob(os.path.join(d, "*.wav")):
            m = re.match(r"^(\d+)", os.path.basename(f))
            files.append((int(m.group(1)) if m else 99, f))
        files.sort()
        return [(n, f, D.wav_dur(f)) for n, f in files]

    def recover_driver(self):
        """驱动窗口标题 Valkyrie Driver 但可能被隐藏: 无 visible 过滤枚举, 强制唤出"""
        b = ctypes.create_unicode_buffer(256)
        found = []
        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, l):
            D.user32.GetWindowTextW(h, b, 256)
            if b.value == "Valkyrie Driver":
                found.append(int(h))
            return True
        D.user32.EnumWindows(cb, 0)
        if not found:
            return None
        h = found[0]
        D.user32.ShowWindow(h, 9)
        time.sleep(0.5)
        D.user32.SetForegroundWindow(h)
        D.user32.BringWindowToTop(h)
        time.sleep(0.6)
        return h

    def cleanup_dialogs(self):
        """关掉所有残留的 #32770 文件对话框, 防遮挡/骗过 dialog_input"""
        u = D.user32
        killed = []
        Enum = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _):
            c = ctypes.create_unicode_buffer(64)
            u.GetClassNameW(h, c, 64)
            if c.value == "#32770" and u.IsWindowVisible(h):
                t = ctypes.create_unicode_buffer(128)
                u.GetWindowTextW(h, t, 128)
                if any(k in t.value for k in ("选择", "打开", "Open")):
                    u.PostMessageW(int(h), 0x10, 0, 0)
                    killed.append(t.value)
            return True
        u.EnumWindows(Enum(cb), 0)
        if killed:
            time.sleep(0.5)
            self.log(f"  清理残留对话框 x{len(killed)}")

    def _uia_find(self, dw, name):
        for ct in ("TreeItem", "ListItem", "DataItem", "Button"):
            try:
                c = dw.child_window(title=name, control_type=ct)
                if c.exists(timeout=0.4):
                    return c.wrapper_object()
            except Exception:
                pass
        try:
            c = dw.child_window(title=name)
            if c.exists(timeout=0.4):
                return c.wrapper_object()
        except Exception:
            pass
        return None

    def _uia_click_dialog(self, path, s):
        """真鼠标在文件对话框里逐级点开文件夹再选文件; 成功 True / 放弃 False"""
        try:
            from pywinauto import Desktop
        except ImportError:
            self.log("  ⚠ pywinauto 未安装, dialog_click 退回键盘方式")
            return False
        import os as _os
        dw = None
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 7.0 and dw is None:
            # UIA 标题全枚举会被完整性级别挡住, 先 win32 拿句柄再 UIA 直连
            for title in ("选择视频 / 图片素材", "打开", "Open"):
                h = D.user32.FindWindowW(None, title)
                if not h:
                    continue
                try:
                    spec = Desktop(backend="uia").window(handle=h)
                    if spec.exists(timeout=2.0):
                        dw = spec
                        break
                except Exception:
                    continue
            if dw is None:
                time.sleep(0.2)
        if dw is None:
            self.log("  ⚠ dialog_click 没找到对话框")
            return False
        try:
            dw.set_focus()
            time.sleep(0.4)
            dwell = s.get("dwell", 0.9)
            apath = path.replace("/", "\\")
            drive = apath.split("\\")[0]  # 如 H:
            folders = [f for f in apath.split("\\")[1:-1]]
            fname = _os.path.basename(apath)
            # 树节点显示卷标(如 "开发 (H:)"); 先试卷标再试裸盘符
            label = drive
            try:
                import ctypes
                k32 = ctypes.windll.kernel32
                buf = ctypes.create_unicode_buffer(260)
                if k32.GetVolumeInformationW(drive + "\\", buf, 260, None, None, None, None, 0):
                    if buf.value:
                        label = f"{buf.value} ({drive})"
            except Exception:
                pass
            hit = self._uia_find(dw, label) or self._uia_find(dw, drive)
            if hit is None:
                for ct in ("TreeItem", "ListItem", "DataItem", "*"):
                    try:
                        c = dw.child_window(title_re=r".*\\%s" % drive[-1], control_type=ct)
                        if c.exists(timeout=0.5):
                            hit = c.wrapper_object()
                            break
                    except Exception:
                        continue
            if not hit:
                self.log(f"  ⚠ dialog_click 找不到盘符 {label}")
                return False
            hit.click_input()
            time.sleep(dwell)
            for fold in folders:
                hit = self._uia_find(dw, fold)
                if not hit:
                    self.log(f"  ⚠ dialog_click 找不到文件夹 {fold}")
                    return False
                hit.double_click_input()
                time.sleep(dwell)
            hit = self._uia_find(dw, fname)
            if not hit:
                self.log(f"  ⚠ dialog_click 找不到文件 {fname}")
                return False
            hit.click_input()
            time.sleep(max(0.5, dwell * 0.6))
            ok = None
            for spec_kw in ({"auto_id": "1", "control_type": "Button"},
                            {"title": "打开(O)", "control_type": "Button"},
                            {"title_re": ".*(打开|Open|保存|选择)\\(.*",
                             "control_type": "Button"}):
                try:
                    c0 = dw.child_window(**spec_kw)
                    if c0.exists(timeout=0.8):
                        ok = c0.wrapper_object()
                        break
                except Exception:
                    continue
            if ok is None:
                self.log("  ⚠ dialog_click 没有打开按钮, 用文件名回车收尾")
                D.press_key(VK["ENTER"])
                return True
            ok.click_input()
            time.sleep(0.6)
            return True
        except Exception as e:
            self.log(f"  ⚠ dialog_click 异常({str(e)[:40]}), 退回键盘方式")
            return False

    def run_segment(self, segment, only_clips=None, demo=False):
        self.cur_app = "eden" if segment == "第五段" else "driver"
        kw = ("幻映",) if self.cur_app == "eden" else ("Valkyrie Driver",)
        if self.cur_app == "eden":
            self.ensure_eden()
        else:
            self.recover_driver()
        self.cleanup_dialogs()
        self.win = bring_front(kw)
        if not self.win:
            raise RuntimeError(f"找不到 {segment} 目标窗口 {kw}")
        if self.cur_app == "driver":
            # 复位: 帧数>=2 才删 (1帧时删除所有帧是禁用的), 空了直接跳过
            cdp = self.get_cdp("driver")
            if cdp:
                import re as _re
                cdp.js(
                    "(function(){var els=[...document.querySelectorAll('*')].filter(function(e){"
                    "return e.childElementCount===0&&e.textContent.trim()==='屏幕设置'});"
                    "var e=els.find(function(x){return x.offsetParent})||els[0];if(e){"
                    "var b=e.closest('li,[class*=menu-item-text],[class*=button]')||e;b.click();return 1}"
                    "return 0})()")
                time.sleep(0.35)
                t = (cdp.js("document.body.innerText") or "").replace("\n", " ")
                m = _re.search(r"帧数：\s*(\d+)/", t)
                cur = int(m.group(1)) if m else -1
                if cur >= 2:
                    self.log(f"帧数 {cur}, 删除所有帧")
                    self.do_step({"act": "msclick", "sel": "text:删除所有帧", "at": 0}, 5.0)
                    for _ in range(20):
                        time.sleep(0.3)
                        t = (cdp.js("document.body.innerText") or "").replace("\n", " ")
                        m = _re.search(r"帧数：\s*(\d+)/", t)
                        if m and int(m.group(1)) == 0:
                            break
                    else:
                        self.log("⚠ 删除帧超时, 继续")
                elif cur == 1:
                    self.log("帧数 1: 删除按钮禁用, 留着这帧继续")

        clips = self.load_clips(segment)
        if only_clips:
            clips = [c for c in clips if c[0] in only_clips]
        plan = {c["n"]: c for c in self.plan.get(segment, [])}
        self.log(f"{segment}: {len(clips)} 条音频, 总时长 {sum(c[2] for c in clips):.1f}s + 间隔 {2*(len(clips)-1)}s")
        out = None
        ff = None
        if not demo:
            os.makedirs(OUT_DIR, exist_ok=True)
            out = os.path.join(OUT_DIR, f"rec_{segment}_{time.strftime('%m%d_%H%M%S')}.mp4")
        else:
            self.log("演示模式: 不启动 ffmpeg, 由 OBS 自行录制")
        self.start_overlay()
        self.log("覆盖层已启动 (假光标+高亮)")
        self.status("3 秒后开始…别动鼠标")
        time.sleep(3)
        if self.abort.is_set():
            self.stop_overlay(); return None
        if not demo:
            ff = self.start_ffmpeg(self.win["rect"], out)
            self.log(f"录制开始 → {out}")
        try:
            for n, wav, dur in clips:
                if self.abort.is_set():
                    break
                self.status(f"[{segment}] clip{n} 播放中 {dur:.1f}s")
                self.log(f"— clip{n} ({dur:.1f}s) {os.path.basename(wav)[:28]}")
                if demo:
                    self.log(f"— clip{n} ({dur:.1f}s) [静音参考, 配音由 PR 导入]")
                else:
                    D.play_wav(wav)
                steps = sorted(plan.get(n, {}).get("steps", []), key=lambda s: s["at"])
                t0 = time.perf_counter()
                for s in steps:
                    if self.abort.is_set():
                        break
                    target_t = s["at"] * dur
                    wait = target_t - (time.perf_counter() - t0)
                    if wait > 0:
                        # 分片睡眠便于响应 abort
                        end = time.perf_counter() + wait
                        while time.perf_counter() < end and not self.abort.is_set():
                            time.sleep(min(0.15, end - time.perf_counter()))
                    self.do_step(s, dur)
                remain = dur - (time.perf_counter() - t0)
                if remain > 0:
                    time.sleep(remain)
                self.udp.sendto(b'{"cmd":"clear"}', ("127.0.0.1", 9377))
                time.sleep(2.0)
        finally:
            if ff is not None:
                ff.stdin.write(b"q")
                try:
                    ff.communicate(timeout=15)
                except Exception:
                    ff.kill()
            self.stop_overlay()
        if demo:
            self.log("✔ 指引演示完成 (未录屏)")
        else:
            self.log(f"✔ 录制完成: {out} ({os.path.getsize(out)/1e6:.1f} MB)" if os.path.exists(out) else "✘ 无输出")
        return out

    def run_all(self):
        for seg in ("第四段", "第五段"):
            if self.abort.is_set():
                break
            self.run_segment(seg)


def main_gui():
    root = tk.Tk()
    root.title("EDEN 演示录制器")
    root.geometry("430x420+20+20")
    logq = []
    txt = scrolledtext.ScrolledText(root, width=52, height=22, font=("Microsoft YaHei UI", 9))
    status = tk.StringVar(value="就绪")
    seg = tk.StringVar(value="第五段")

    def gui_log(m):
        txt.insert("end", m + "\n")
        txt.see("end")
        txt.update_idletasks()

    runner = Runner(gui_log, lambda m: status.set(m))
    demo_var = tk.BooleanVar(value=False)

    def worker(fn):
        threading.Thread(target=fn, daemon=True).start()

    def start():
        runner.abort.clear()
        mode = seg.get()
        dm = demo_var.get()
        def fn():
            try:
                if mode == "两段连录":
                    for sg in ("第四段", "第五段"):
                        if runner.abort.is_set():
                            break
                        runner.run_segment(sg, demo=dm)
                else:
                    runner.run_segment(mode, demo=dm)
            except Exception as e:
                gui_log(f"✘ 出错: {e}")
            finally:
                status.set("完成/中止")
        worker(fn)

    def stop():
        runner.abort.set()
        gui_log("收到中止请求…")

    tk.Label(root, textvariable=status, font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=8, pady=4)
    row = tk.Frame(root); row.pack(fill="x", padx=8)
    ttk.Combobox(row, textvariable=seg, values=["第四段", "第五段", "两段连录"], width=12, state="readonly").pack(side="left")
    tk.Button(row, text="开始录制", command=start, bg="#ff4fa3", fg="white").pack(side="right")
    tk.Button(row, text="中止", command=stop).pack(side="right", padx=6)
    tk.Checkbutton(row, text="只指引(OBS录)", variable=demo_var).pack(side="left", padx=8)
    txt.pack(fill="both", expand=True, padx=8, pady=6)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # 无 GUI: python recorder.py --cli 第五段 1,2  [--demo 只指引不录屏]
        seg = sys.argv[2] if len(sys.argv) > 2 else "第五段"
        demo = "--demo" in sys.argv
        only = None
        for a in sys.argv[3:]:
            if "," in a or a.isdigit():
                only = {int(x) for x in a.split(",") if x.strip().isdigit()}
        r = Runner(print, lambda m: None)
        r.run_segment(seg, only, demo=demo)
    else:
        main_gui()
