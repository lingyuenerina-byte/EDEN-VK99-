# -*- coding: utf-8 -*-
"""EDEN 演示步骤编辑器 — 鼠标宏式 GUI + 助手 API

雪羽酱负责: 点「拾取目标」→ 鼠标移到要指引的按钮上 → 按 F8, 自动识别元素;
调每一步的时刻(秒)/动作/延时。梅露露负责: 通过 http://127.0.0.1:9378
读改计划、跑录屏。保存后写回 demo_plan.json (recorder 直接可用)。

API:
  GET  /plan               当前完整计划 (at 比例格式, 与 demo_plan.json 一致)
  GET  /plan?raw=1         GUI 格式 (steps 用绝对秒 t)
  POST /plan               {"segment":"第四段","clips":[{"n":1,"app":"driver","steps":[{"t":0.5,"act":"hl","sel":"text:选择照片"}]}]}
  GET  /clips?segment=第四段   每条语音 n/文件名/时长
  GET  /status             编辑器状态
  POST /run                {"segment":"第四段","clips":"1,2"}  启动 recorder 录制(异步)
  GET  /runlog             最近录屏日志行
"""
import ctypes
import ctypes.wintypes as wt
import glob
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D

HERE = os.path.dirname(os.path.abspath(__file__))
PLAN_FILE = os.path.join(HERE, "demo_plan.json")
VO_ROOT = "H:/EDENVK/语音"
API_PORT = 9378
APP_PORTS = {"driver": 9223, "eden": 9224}
ACTS = ["hl", "move", "click", "cdpclick", "msclick", "physclick", "dialog_click", "dialog_nav", "dialog_input",
        "wait", "wait_dom", "wait_frames", "move_win", "key", "drag_seg"]
ZH = {
    "hl": "高亮框", "move": "鼠标滑向", "click": "真实点击", "cdpclick": "页面JS点击",
    "msclick": "驱动页可信点击", "physclick": "物理点击(可拾取)", "dialog_click": "鼠标点开文件夹", "dialog_nav": "对话框两步选文件",
    "dialog_input": "对话框直填路径",
    "wait": "干等", "wait_dom": "等页面元素", "wait_frames": "等帧数达标",
    "move_win": "移到窗口位置", "key": "按键", "drag_seg": "拖时间轴",
}
ZH2ACT = {v: k for k, v in ZH.items()}
u = D.user32
k32 = ctypes.windll.kernel32

ACT_TIP = {
    "hl": '高亮框  {"dur":1.0}  sel 支持 text:xxx / #id  (教程片不配台词, PR后期字幕)',
    "move": '鼠标滑向  {"ms":700}',
    "click": '真实点击(物理鼠标)',
    "cdpclick": 'JS click(菜单/切页/#btnPick 用它)',
    "msclick": 'CDP可信点击(开原生对话框/确认框用它)',
    "dialog_click": '真鼠标: 树点盘符->双击EDENVK/assets->点文件->点打开  {"asset":"photo1","dwell":0.9}',
    "dialog_nav": '先展示素材文件夹停 dwell 秒再选文件  {"asset":"photo1","dwell":1.6}',
    "dialog_input": '对话框一步直填完整路径  {"asset":"photo1"} 或 {"text":"C:/..."}',
    "wait": '干等  {"sec":1.5}',
    "wait_dom": '等元素  {"sel":"#btnWrite","state":"!disabled","timeout":10}',
    "wait_frames": '等驱动帧数达标  {"n":1,"timeout":15}',
    "move_win": '移到窗口相对位  {"frac":[0.5,0.5],"ms":700}',
    "key": '按键  {"vk":"SPACE"}',
    "drag_seg": '拖时间轴片段  {"dx":100,"ms":900}',
}


def clip_list(segment):
    d = os.path.join(VO_ROOT, segment)
    out = []
    for f in glob.glob(os.path.join(d, "*.wav")):
        m = re.match(r"^(\d+)", os.path.basename(f))
        out.append((int(m.group(1)) if m else 99, f, D.wav_dur(f)))
    out.sort()
    return out


class Editor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("EDEN 指引步骤编辑器 — 保存即写 demo_plan.json")
        self.root.geometry("1020x680")
        self.lock = threading.Lock()
        self.q = queue.Queue()
        self.seg = None
        self.clips = {}          # GUI 模型: seg -> [{"n":..,"app":..,"steps":[{"t":..,...}]}]
        self.assets = {}
        self.durs = {}           # (seg,n) -> wav 秒
        self.pick_until = 0.0
        self.run_proc = None
        self.run_log = []
        self.build_ui()
        self.load_file()
        threading.Thread(target=self.api_loop, daemon=True).start()
        self.root.after(60, self.tick)
        self.root.after(100, self.drain)

    # ---------- UI ----------
    def build_ui(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="段落").pack(side="left")
        self.cb_seg = ttk.Combobox(top, width=10, state="readonly")
        self.cb_seg.pack(side="left", padx=4)
        self.cb_seg.bind("<<ComboboxSelected>>", lambda e: self.show_segment())
        ttk.Label(top, text="语音条").pack(side="left")
        self.cb_clip = ttk.Combobox(top, width=42, state="readonly")
        self.cb_clip.pack(side="left", padx=4)
        self.cb_clip.bind("<<ComboboxSelected>>", lambda e: self.show_clip())
        ttk.Label(top, text="app").pack(side="left")
        self.cb_app = ttk.Combobox(top, width=8, values=["eden", "driver"], state="readonly")
        self.cb_app.pack(side="left", padx=4)
        self.cb_app.bind("<<ComboboxSelected>>", lambda e: self.set_app())
        ttk.Button(top, text="试听本条", command=self.audition).pack(side="left", padx=4)
        ttk.Button(top, text="试录本条", command=self.record_this).pack(side="left", padx=4)
        self.demo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="只指引(OBS录)", variable=self.demo_var).pack(side="left", padx=4)
        ttk.Button(top, text="保存", command=self.save_file).pack(side="left", padx=4)
        ttk.Button(top, text="重载文件", command=self.load_file).pack(side="left", padx=4)

        mid = ttk.Frame(self.root, padding=(6, 0))
        mid.pack(fill="both", expand=True)
        cols = ("t", "act", "sel", "extra")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", height=14)
        for c, w, txt in zip(cols, (70, 110, 300, 380),
                             ("时刻(秒)", "动作", "目标 sel", "参数")):
            self.tree.heading(c, text=txt)
            self.tree.column(c, width=w)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.edit_sel())
        sb = ttk.Scrollbar(mid, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        side = ttk.Frame(mid)
        side.pack(side="left", fill="y", padx=6)
        for txt, cmd in (("新增步骤", self.add_step), ("更新步骤", self.update_step),
                         ("删除步骤", self.del_step), ("上移", lambda: self.swap(-1)),
                         ("下移", lambda: self.swap(1))):
            ttk.Button(side, text=txt, command=cmd).pack(fill="x", pady=2)
        self.btn_pick = ttk.Button(side, text="拾取目标\n(移鼠标→F8)", command=self.arm_pick)
        self.btn_pick.pack(fill="x", pady=8)
        ttk.Label(side, text="F8 拾取时自动用\nelementFromPoint 识别\n生成 sel", foreground="#666").pack()

        ef = ttk.LabelFrame(self.root, text="步骤编辑", padding=6)
        ef.pack(fill="x", padx=6, pady=4)
        r1 = ttk.Frame(ef)
        r1.pack(fill="x")
        ttk.Label(r1, text="时刻").pack(side="left")
        self.en_t = ttk.Entry(r1, width=7)
        self.en_t.pack(side="left", padx=2)
        ttk.Label(r1, text="动作").pack(side="left")
        self.en_act = ttk.Combobox(r1, values=[ZH[a] for a in ACTS], width=15)
        self.en_act.pack(side="left", padx=2)
        self.en_act.bind("<<ComboboxSelected>>",
                         lambda e: self.lbl_tip.config(
                             text=ACT_TIP.get(ZH2ACT.get(self.en_act.get(), self.en_act.get()), "")))
        ttk.Label(r1, text="目标(sel)").pack(side="left")
        self.en_sel = ttk.Entry(r1, width=46)
        self.en_sel.pack(side="left", padx=2)
        ttk.Label(r1, text="时长(高亮dur)").pack(side="left")
        self.en_dur = ttk.Entry(r1, width=5)
        self.en_dur.pack(side="left", padx=2)
        r2 = ttk.Frame(ef)
        r2.pack(fill="x", pady=3)
        ttk.Label(r2, text="附加参数JSON").pack(side="left")
        self.en_extra = ttk.Entry(r2, width=70)
        self.en_extra.pack(side="left", padx=4)
        self.lbl_tip = ttk.Label(ef, text="", foreground="#0a7")
        self.lbl_tip.pack(anchor="w")
        self.lbl_stat = ttk.Label(self.root, text="就绪", anchor="w", padding=4)
        self.lbl_stat.pack(fill="x")

    # ---------- 模型 ----------
    def load_file(self):
        with self.lock:
            with open(PLAN_FILE, encoding="utf-8") as f:
                plan = json.load(f)
            self.assets = plan.get("assets", {})
            self.clips = {}
            durs = {}
            for seg in plan:
                if seg == "assets":
                    continue
                cl = clip_list(seg)
                dn = {n: d for n, _, d in cl}
                durs.update({(seg, n): v for n, v in dn.items()})
                out = []
                for c in plan[seg]:
                    dur = dn.get(c["n"], 1.0)
                    steps = []
                    for s in c["steps"]:
                        s2 = dict(s)
                        s2["t"] = round(s2.pop("at", 0) * dur, 2)
                        steps.append(s2)
                    out.append({"n": c["n"], "app": c.get("app", "driver"),
                                "steps": sorted(steps, key=lambda x: x["t"])})
                self.clips[seg] = out
            self.durs = durs
            segs = list(self.clips.keys())
        self.cb_seg["values"] = segs
        if not self.seg and segs:
            self.seg = segs[-1]
            self.cb_seg.set(self.seg)
        self.show_segment()
        self.stat(f"已载入 {os.path.basename(PLAN_FILE)} · API http://127.0.0.1:{API_PORT}")

    def save_file(self, silent=False):
        with self.lock:
            plan = {"assets": self.assets}
            for seg, cs in self.clips.items():
                out = []
                for c in cs:
                    dur = self.durs.get((seg, c["n"]), 1.0)
                    steps = []
                    for s in c["steps"]:
                        s2 = dict(s)
                        s2["at"] = round(s2.pop("t", 0) / dur, 4)
                        steps.append(s2)
                    out.append({"n": c["n"], "app": c["app"],
                                "steps": sorted(steps, key=lambda x: x["at"])})
                plan[seg] = out
            tmp = PLAN_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            os.replace(tmp, PLAN_FILE)
        if not silent:
            self.stat("已保存 demo_plan.json (recorder 可直接录)")

    def cur_clip(self):
        for c in self.clips.get(self.seg, []):
            if c["n"] == self.cur_n():
                return c
        return None

    def cur_n(self):
        v = self.cb_clip.get()
        m = re.match(r"^(\d+)", v)
        return int(m.group(1)) if m else None

    def show_segment(self):
        self.seg = self.cb_seg.get()
        self.cb_clip["values"] = []
        cs = clip_list(self.seg)
        vals = []
        for n, f, d in cs:
            self.durs[(self.seg, n)] = d
            vals.append(f"{n} · {os.path.basename(f)[:34]} · {d:.1f}s")
        self.cb_clip["values"] = vals
        if vals:
            self.cb_clip.current(0)
        self.show_clip()

    def show_clip(self):
        c = self.cur_clip()
        if c:
            self.cb_app.set(c["app"])
        self.tree.delete(*self.tree.get_children())
        if not c:
            return
        for i, s in enumerate(c["steps"]):
            self.tree.insert("", "end", iid=str(i), values=(
                s["t"], ZH.get(s["act"], s["act"]), s.get("sel", ""), self.step_extra(s)))

    @staticmethod
    def step_extra(s):
        d = {k: v for k, v in s.items() if k not in ("t", "act", "sel")}
        return json.dumps(d, ensure_ascii=False) if d else ""

    def set_app(self):
        c = self.cur_clip()
        if c:
            c["app"] = self.cb_app.get()

    def edit_sel(self):
        c = self.cur_clip()
        if not c or not self.tree.selection():
            return
        s = c["steps"][int(self.tree.selection()[0])]
        self.en_t.delete(0, "end")
        self.en_t.insert(0, s["t"])
        self.en_act.set(ZH.get(s["act"], s["act"]))
        self.en_sel.delete(0, "end")
        self.en_sel.insert(0, s.get("sel", ""))
        self.en_dur.delete(0, "end")
        self.en_dur.insert(0, s.get("dur", ""))
        self.en_extra.delete(0, "end")
        self.en_extra.insert(0, self.step_extra(s))
        self.lbl_tip.config(text=ACT_TIP.get(s["act"], ""))

    def collect_form(self):
        try:
            t = float(self.en_t.get())
        except ValueError:
            raise ValueError("时刻不是数字")
        a = self.en_act.get().strip()
        step = {"t": t, "act": ZH2ACT.get(a, a)}
        if self.en_sel.get().strip():
            step["sel"] = self.en_sel.get().strip()
        if self.en_dur.get().strip():
            step["dur"] = float(self.en_dur.get())
        ex = self.en_extra.get().strip()
        if ex:
            step.update(json.loads(ex))
        return step

    def add_step(self):
        c = self.cur_clip()
        if not c:
            self.stat("⚠ 先选段落/语音条")
            return
        try:
            c["steps"].append(self.collect_form())
            c["steps"].sort(key=lambda x: x["t"])
        except Exception as e:
            self.stat(f"⚠ 参数错: {e}")
            return
        self.show_clip()
        self.stat(f"新增 {ZH.get(c['steps'][-1]['act'], c['steps'][-1]['act'])} @ {c['steps'][-1]['t']}s")

    def update_step(self):
        c = self.cur_clip()
        if not c or not self.tree.selection():
            self.stat("⚠ 先选中一行")
            return
        idx = int(self.tree.selection()[0])
        try:
            c["steps"][idx] = self.collect_form()
            c["steps"].sort(key=lambda x: x["t"])
        except Exception as e:
            self.stat(f"⚠ 参数错: {e}")
            return
        self.show_clip()
        self.stat("步骤已更新 (别忘了保存)")

    def del_step(self):
        c = self.cur_clip()
        if c and self.tree.selection():
            c["steps"].pop(int(self.tree.selection()[0]))
            self.show_clip()

    def swap(self, d):
        c = self.cur_clip()
        if not c or not self.tree.selection():
            return
        i = int(self.tree.selection()[0])
        j = i + d
        if 0 <= j < len(c["steps"]):
            c["steps"][i], c["steps"][j] = c["steps"][j], c["steps"][i]
            self.show_clip()
            self.tree.selection_set(str(j))

    # ---------- 拾取 ----------
    def arm_pick(self):
        self.pick_until = time.time() + 15
        self.stat("拾取模式: 把鼠标移到目标上, 按 F8 (15s)…")

    def tick(self):
        try:
            if self.pick_until and time.time() < self.pick_until:
                if k32.GetAsyncKeyState(0x77) & 0x8000:  # F8, 与提示一致
                    self.pick_until = 0
                    self.do_pick()
            self.q.get_nowait()()
        except queue.Empty:
            pass
        except Exception as e:
            self.stat(f"⚠ {e}")
        self.root.after(60, self.tick)

    def drain(self):
        try:
            while True:
                fn = self.q.get_nowait()
                fn()
        except queue.Empty:
            pass
        self.root.after(120, self.drain)

    def top_window_at(self, x, y):
        pt = wt.POINT(x, y)
        h = u.WindowFromPoint(pt)
        h = u.GetAncestor(h, 2)  # GA_ROOT
        buf = ctypes.create_unicode_buffer(256)
        u.GetWindowTextW(h, buf, 256)
        title = buf.value
        for key, app in (("Valkyrie", "driver"), ("EDEN", "eden"), ("幻映", "eden")):
            if key in title:
                return int(h), app
        return int(h), None

    def do_pick(self):
        p = wt.POINT()
        u.GetCursorPos(ctypes.byref(p))
        hwnd, app = self.top_window_at(p.x, p.y)
        if not app:
            self.stat(f"⚠ 指针下不是 EDEN/驱动窗口")
            return
        rc = wt.RECT()
        u.GetWindowRect(hwnd, ctypes.byref(rc))
        crect = wt.RECT()
        u.GetClientRect(wt.HWND(hwnd), ctypes.byref(crect))
        tl = wt.POINT(0, 0)
        u.ClientToScreen(wt.HWND(hwnd), ctypes.byref(tl))
        vx, vy = tl.x, tl.y
        try:
            cdp = D.CDP(APP_PORTS[app])
            dpr = cdp.js("window.devicePixelRatio") or 1
            cx, cy = (p.x - vx) / dpr, (p.y - vy) / dpr
            info = cdp.js(
                "(function(){var e=document.elementFromPoint(%d,%d);if(!e)return null;"
                "var r=e.getBoundingClientRect();var cls=(e.className&&String(e.className).split(' ')[0])||'';"
                "return {tag:e.tagName,id:e.id,cls:cls,txt:e.textContent?e.textContent.trim().slice(0,18):'',"
                "rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]})()"
                % (cx, cy))
        except Exception as e:
            self.stat(f"⚠ CDP 不通 ({app}): {e}")
            return
        if not info:
            self.stat("⚠ 页面上没取到元素")
            return
        sel = ""
        if info.get("id"):
            sel = "#" + info["id"]
        elif info.get("txt") and len(info["txt"]) <= 14:
            sel = "text:" + info["txt"]
        elif info.get("cls"):
            sel = info["cls"]
        self.en_sel.delete(0, "end")
        self.en_sel.insert(0, sel)
        # 雪羽酱软件同款: F8 即入录一条物理点击步骤 (sel 实时解析优先, x/y 兜底)
        c = self.cur_clip()
        if c is not None:
            try:
                t = float(self.en_t.get())
            except ValueError:
                t = 0.0
            c["steps"].append({"t": t, "act": "physclick", "sel": sel,
                               "x": p.x, "y": p.y, "app": app})
            c["steps"].sort(key=lambda x: x["t"])
            self.show_clip()
            self.stat(f"入录[物理点击][{app}] sel={sel or '(空)'} @({p.x},{p.y}) t={t}s — 保存前可再调时刻")
        else:
            self.stat(f"拾取[{app}] {info['tag']} '{info.get('txt','')}' → sel={sel or '(空,手动填)'} (未选语音条, 只填表)")

    # ---------- 运行 ----------
    def audition(self):
        cs = clip_list(self.seg or "")
        for n, f, d in cs:
            if n == self.cur_n():
                D.play_wav(f)
                self.stat(f"播放 {os.path.basename(f)} ({d:.1f}s)")
                return

    def record_this(self):
        self.start_run(self.seg, str(self.cur_n()))

    def start_run(self, segment, clips):
        if self.run_proc and self.run_proc.poll() is None:
            self.stat("⚠ 已有录屏在跑")
            return False
        py = sys.executable
        if "pythonw" in os.path.basename(py).lower():
            py = os.path.join(os.path.dirname(py), "python.exe")
        cmd = [py, os.path.join(HERE, "recorder.py"), "--cli", segment]
        if clips:
            cmd.append(clips)
        if getattr(self, "demo_var", None) and self.demo_var.get():
            cmd.append("--demo")
        self.save_file(silent=True)

        def pump():
            self.run_log.append("$ " + " ".join(cmd[-3:]))
            for line in self.run_proc.stdout:
                self.run_log.append(line.rstrip())
                self.q.put(lambda l=line.rstrip(): self.stat("录屏| " + l))
            self.run_log.append(f"[exit {self.run_proc.wait()}]")
        flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW: 不弹控制台窗
        self.run_proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, bufsize=1,
                                         creationflags=flags)
        threading.Thread(target=pump, daemon=True).start()
        return True

    def stat(self, m):
        self.lbl_stat.config(text=m)

    # ---------- HTTP API ----------
    def api_loop(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        ed = self

        class H(BaseHTTPRequestHandler):
            def _send(self, code, obj):
                b = json.dumps(obj, ensure_ascii=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                from urllib.parse import urlparse, parse_qs
                pr = urlparse(self.path)
                q = parse_qs(pr.query)
                try:
                    if pr.path == "/plan":
                        seg = q.get("segment", [None])[0]
                        if q.get("raw", [""])[0] == "1":
                            data = {"assets": ed.assets, "segments": ed.clips}
                        else:
                            with open(PLAN_FILE, encoding="utf-8") as f:
                                data = json.load(f)
                        if seg:
                            data = data.get(seg, [])
                        self._send(200, data)
                    elif pr.path == "/clips":
                        seg = q.get("segment", [ed.seg])[0]
                        self._send(200, [{"n": n, "file": os.path.basename(f), "dur": d}
                                         for n, f, d in clip_list(seg)])
                    elif pr.path == "/status":
                        self._send(200, {"seg": ed.seg, "api": API_PORT,
                                         "running": bool(ed.run_proc and ed.run_proc.poll() is None)})
                    elif pr.path == "/runlog":
                        self._send(200, {"lines": ed.run_log[-80:]})
                    else:
                        self._send(404, {"error": "no route"})
                except Exception as e:
                    self._send(500, {"error": str(e)})

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except Exception as e:
                    self._send(400, {"error": f"bad json: {e}"})
                    return
                try:
                    if self.path == "/plan":
                        seg = body["segment"]
                        with ed.lock:
                            ed.clips[seg] = body["clips"]
                        if seg == ed.seg:
                            ed.q.put(ed.show_clip)
                        self._send(200, {"ok": True, "segment": seg,
                                         "clips": len(body["clips"])})
                    elif self.path == "/save":
                        ed.q.put(ed.save_file)
                        self._send(200, {"ok": True})
                    elif self.path == "/run":
                        ok = ed.start_run(body["segment"], body.get("clips", ""))
                        self._send(200, {"started": ok})
                    else:
                        self._send(404, {"error": "no route"})
                except Exception as e:
                    self._send(500, {"error": str(e)})

            def log_message(self, *a):
                pass

        ThreadingHTTPServer(("127.0.0.1", API_PORT), H).serve_forever()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Editor().run()
