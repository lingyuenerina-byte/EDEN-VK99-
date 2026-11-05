#!/usr/bin/env python3
"""vk99_server.py — EDEN-VK99II「幻映」Tauri 版引擎 sidecar (无头, HTTP API).

把 vk99_studio.py 的全部业务逻辑 (参数计算/拆帧/官方UI自动化写入) 剥掉 Tk 壳,
经 127.0.0.1:8793 (被占则自增) 提供 JSON API + 静态帧服务, 供 WebView2 前端调用.
通道逻辑与已验证的 studio 完全一致: probe_video/extract_frames(vk99_prep) +
OfficialWriter(vk99_writer, CDP 驱动官方 UI), 零自制 HID.

用法: python -u vk99_server.py   (由 Tauri 壳负责拉起/回收; 打印 EDEN_PORT=)
"""
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
FRAMES_ROOT = os.path.join(ROOT, "studio_frames")
PREV_CACHE = os.path.join(os.environ.get("LOCALAPPDATA", FRAMES_ROOT),
                          "EDEN", "prev_cache")
OFFICIAL_MAX_FRAMES = 61          # 官方 GIF 槽物理上限 (见 studio 注释)
CAP_MS = OFFICIAL_MAX_FRAMES * 255  # ≈15.5s 原速上限

from vk99_prep import (ASPECT, TARGET_H, TARGET_W, compute_crop,  # noqa: E402
                       extract_frames, probe_video)
from vk99_writer import OfficialWriter, WriterError  # noqa: E402

MODE_ANIM, MODE_IMG = "动画", "单张图片"


def find_ffmpeg():
    """定位 ffmpeg: 优先随包的 ROOT/ffmpeg.exe (安装包自带, 解码零依赖),
    其次系统 PATH 与常见安装位置."""
    bundled = os.path.join(ROOT, "ffmpeg.exe")
    if os.path.exists(bundled):
        return bundled
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    up = os.environ.get("USERPROFILE", "")
    for cand in (os.path.join(up, "scoop", "shims", "ffmpeg.exe"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""),
                              "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
                 r"C:\ffmpeg\bin\ffmpeg.exe"):
        if os.path.exists(cand):
            return cand
    return None


# ---------- studio 同款 ffmpeg 快速拆帧 ----------
def extract_frames_fast(video, info, fps, zoom, panx, pany, outdir,
                        max_frames, prefix="f", t0=0.0, seg_len=None):
    ff = find_ffmpeg()
    if not ff or not info or info.get("fps", 0) <= 0:
        return 0
    crop = compute_crop(info["w"], info["h"], zoom, panx, pany)
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    if cw < 2 or ch < 2:
        return 0
    vf = (f"crop={cw}:{ch}:{crop[0]}:{crop[1]},"
          f"fps={fps},scale={TARGET_W}:{TARGET_H}:flags=lanczos")
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error"]
    if t0 > 0:
        cmd += ["-ss", f"{t0:.3f}"]
    cmd += ["-i", video]
    if seg_len:
        cmd += ["-t", f"{seg_len:.3f}"]
    cmd += ["-vf", vf, "-frames:v", str(max_frames),
            os.path.join(outdir, f"{prefix}_%03d.png")]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=900)
    except Exception:
        return 0
    if r.returncode != 0:
        return 0
    return len([n for n in os.listdir(outdir)
                if n.lower().endswith(".png")])


def make_preview_video(png_dir, fps, out_path, limit=None):
    ff = find_ffmpeg()
    if not ff or not os.path.exists(os.path.join(png_dir, "f_001.png")):
        return None
    cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
           "-framerate", f"{fps:.6f}",
           "-i", os.path.join(png_dir, "f_%03d.png")]
    if limit:
        cmd += ["-frames:v", str(int(limit))]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast",
            "-movflags", "+faststart", out_path]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        return out_path if r.returncode == 0 and os.path.exists(out_path) else None
    except Exception:
        return None


def check_driver(log):
    """开工先查官方 Valkyrie Driver: 没有就拉起随包安装程序 (studio 同款).
    只负责弹出安装界面, 装不装由用户定夺."""
    exe = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                       "Programs", "Valkyrie Driver", "Valkyrie Driver.exe")
    if os.path.exists(exe):
        log("✓ 检测到官方 Valkyrie Driver")
        return True
    setup = os.path.join(ROOT, "redist",
                         "Valkyrie_setup_3.2.19_WIN20261021.exe")
    log("✗ 未检测到官方 Valkyrie Driver: 已为您启动安装程序, 装完即可写入…")
    if os.path.exists(setup):
        try:
            subprocess.Popen([setup])
        except Exception as ex:
            log(f"安装程序启动失败: {ex}")
    else:
        log(f"找不到随包安装包: {setup}")
    return False


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.phase = "idle"      # idle/opened/preparing/ready/writing/awaiting/done/error
        self.file = None
        self.info = None
        self.first = None        # np.ndarray RGB 首帧
        self.mode = MODE_ANIM
        # 参数 (与 studio 输入框一一对应)
        self.iv, self.maxn, self.minn = 50, 60, 1
        self.t0, self.seg = 0.0, 0.0     # 起点 / 时长(0=全片)
        self.zoom, self.panx, self.pany = 1.0, 0.5, 0.5
        # 拆帧/写入
        self.batch = None
        self.rels = []
        self.preview_mp4 = None
        self.busy = False
        self.cancel = False
        self.resume_evt = threading.Event()
        self.writer = None
        self.anim_name = ""
        self.driver_ok = None
        self.prog = (0, 0)
        self.logs = []
        self.log_seq = 0
        self.log_cv = threading.Condition()
        self._open_lock = threading.Lock()
        # 预览转码 (ffmpeg -> faststart H.264, WebView2 万能播)
        self.prev = None           # 转码产物路径
        self.prev_state = "none"   # none|run|ready|fail
        self.prev_pct = 0

    # ---------- 预览转码 ----------
    def _start_prev(self):
        import hashlib
        try:
            key = hashlib.md5(f"{self.file}|{os.path.getsize(self.file)}"
                              .encode("utf-8", "ignore")).hexdigest()[:16]
            out = os.path.join(PREV_CACHE, key + ".mp4")
        except OSError:
            self.prev_state = "fail"
            return
        self.prev, self.prev_pct = out, 0
        src, info = self.file, dict(self.info)
        ff = find_ffmpeg()
        if not ff:
            self.prev_state = "fail"
            self.log("!! 未找到 ffmpeg, 预览只显示首帧海报 (写入不受影响)")
            return

        def ok_file(p):
            """完整解码验证预览文件: 防多实例并发写坏的残次缓存再端出去 (黑屏元凶)"""
            try:
                pr = subprocess.run(
                    [ff, "-v", "error", "-i", p, "-map", "0:v:0",
                     "-f", "null", "-"], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=180,
                    creationflags=0x08000000)
                return pr.returncode == 0
            except Exception:
                return False

        if os.path.exists(out) and os.path.getsize(out) > 1024:
            if ok_file(out):
                self.prev_state = "ready"
                return
            try:
                os.remove(out)
            except OSError:
                pass
            self.log("⚠ 预览缓存已损坏, 重新转码")
        self.prev_state = "run"

        def transcode(extra):
            tmp = out + ".tmp.mp4"
            cmd = [ff, "-y", "-hide_banner", "-loglevel", "error",
                   "-progress", "pipe:1", "-i", src,
                   "-map", "0:v:0", "-vf", "scale='min(1280,iw)':-2",
                   "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-movflags", "+faststart", "-an", "-sn"] + extra + [tmp]
            pr = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            total = (info["frames"] / info["fps"]) if info.get("fps") else 0
            for ln in pr.stdout:
                kv = ln.decode("utf-8", "ignore").strip().split("=", 1)
                if len(kv) == 2 and kv[0] == "out_time_ms" and total:
                    try:
                        self.prev_pct = max(0, min(99, int(
                            int(kv[1]) / 1e6 / total * 100)))
                    except ValueError:
                        pass
            err = pr.stderr.read().decode("utf-8", "ignore").strip()
            code = pr.wait()
            ok = (code == 0 and os.path.exists(tmp)
                  and os.path.getsize(tmp) > 1024 and ok_file(tmp))
            if ok:
                if os.path.exists(out):
                    os.remove(out)
                os.replace(tmp, out)
            elif os.path.exists(tmp):
                os.remove(tmp)
            return code, err

        def run():
            os.makedirs(PREV_CACHE, exist_ok=True)
            try:
                code, err = transcode(["-preset", "veryfast", "-crf", "26"])
                if code != 0:
                    self.log(f"预览转码第一次失败 (exit {code}): "
                             f"{err[-180:] or '无报错输出'} … 低配重试")
                    code, err = transcode(["-preset", "ultrafast",
                                           "-crf", "30", "-threads", "4"])
                if code == 0:
                    self.prev_state = "ready"
                    self.log("预览转码完成 ✓")
                else:
                    self.prev_state = "fail"
                    self.log(f"!! 预览转码失败 (exit {code}): "
                             f"{err[-180:] or '无报错输出'} — 只显示首帧海报")
            except Exception as e:
                self.prev_state = "fail"
                self.log(f"!! 预览转码异常: {e}")
        threading.Thread(target=run, daemon=True).start()

    # ---------- 日志 ----------
    def log(self, msg):
        with self.log_cv:
            self.log_seq += 1
            self.logs.append({"seq": self.log_seq, "m": str(msg)})
            if len(self.logs) > 800:
                del self.logs[:len(self.logs) - 800]
            self.log_cv.notify_all()

    def log_since(self, cur):
        with self.lock:
            lines = [x for x in self.logs if x["seq"] > cur]
        return lines

    # ---------- 参数数学 (studio 逐行同款) ----------
    def full_dur(self):
        if not self.info:
            return 0.0
        return self.info["frames"] / max(self.info["fps"], 1)

    def dur(self):
        full = self.full_dur()
        if full <= 0:
            return 0.0
        if self.seg > 0:
            return max(0.1, min(self.seg, full - self.t0))
        return full

    def need_frames(self):
        return max(1, int(math.ceil(self.dur() * 1000.0 / 255)))

    def est_frames(self):
        if not self.info:
            return 0
        if self.info["fps"] <= 0 or self.info["frames"] <= 1 \
                or self.mode == MODE_IMG:
            return 1
        keep = int(self.dur() * 1000.0 / max(1, self.iv))
        est = max(keep, self.minn, self.need_frames())
        return max(1, min(est, self.maxn))

    def eff_iv(self):
        est = self.est_frames()
        dur = self.dur()
        if est <= 0 or dur <= 0 or self.mode == MODE_IMG:
            return self.iv
        return max(1, min(255, int(round(dur * 1000.0 / est))))

    # ---------- 参数动作 (返回给前端的提示在 self.logs 里) ----------
    def set_params(self, d):
        with self.lock:
            changed_mode = False
            if "mode" in d and d["mode"] in (MODE_ANIM, MODE_IMG):
                changed_mode = self.mode != d["mode"]
                self.mode = d["mode"]
            if "iv" in d:
                self.iv = max(1, min(255, int(d["iv"] or 50)))
            if "maxn" in d:
                self.maxn = max(1, min(OFFICIAL_MAX_FRAMES,
                                       int(d["maxn"] or 60)))
            if "minn" in d:
                self.minn = max(1, min(self.maxn, int(d["minn"] or 1)))
            if "t0" in d:
                v = float(d["t0"] or 0)
                self.t0 = max(0.0, min(v, max(self.full_dur() - 0.1, 0.0)))
            if "seg" in d:
                self.seg = max(0.0, float(d["seg"] or 0))
            if "zoom" in d:
                self.zoom = max(1.0, min(4.0, float(d["zoom"])))
            if "panx" in d:
                self.panx = min(max(float(d["panx"]), 0.0), 1.0)
            if "pany" in d:
                self.pany = min(max(float(d["pany"]), 0.0), 1.0)
            if changed_mode and self.mode == MODE_ANIM and self.info \
                    and self.info["fps"] <= 0:
                self.mode = MODE_IMG   # 图片没法做动画
            return self.state()

    def autofit(self):
        """一键贴合原速 (studio.auto_fit 同款语义)."""
        with self.lock:
            if not self.info or self.dur() <= 0 or self.info["frames"] <= 1:
                self.log("!! 先选个视频素材再点自动适配呀…")
                return self.state()
            if self.mode == MODE_IMG:
                self.mode = MODE_ANIM
            if self.dur() * 1000 > CAP_MS * 1.02:
                allow = max(0.1, self.full_dur() - self.t0)
                seg = min(allow, CAP_MS / 1000.0)
                self.seg = seg
                self.log(f"⚡ 官方 GIF 原速物理上限只有 {CAP_MS / 1000:.1f}s "
                         f"({OFFICIAL_MAX_FRAMES}帧×255ms): 已自动把片段时长改成 {seg:.1f}s,")
                self.log(f"   从 {self.t0:.1f}s 开始原速播放. 想播别的段落: 改「起点」再点一次~")
            if self.maxn < self.need_frames():
                self.maxn = min(self.need_frames(), OFFICIAL_MAX_FRAMES)
            self.iv = max(1, min(255, int(round(self.dur() * 1000.0 / self.maxn))))
            est = self.est_frames()
            real = est * self.eff_iv() / (self.dur() * 1000.0) if self.dur() else 1
            self.log(f"⚡ 自动适配: 片段 {self.dur():.1f}s → {est} 帧 · "
                     f"间隔 {self.eff_iv()}ms (速度×{real:.2f}, 写入前官方间隔自动同步)")
            return self.state()

    def preset(self, fps):
        """流畅度预设: 帧率(=1000/间隔)先定, 61 帧预算撑多长选多长."""
        with self.lock:
            iv = max(1, min(255, int(round(1000.0 / fps))))
            self.iv = iv
            self.maxn = OFFICIAL_MAX_FRAMES
            if self.info and self.full_dur() > 0:
                cap_seg = OFFICIAL_MAX_FRAMES * iv / 1000.0
                seg = min(cap_seg, max(0.1, self.full_dur() - self.t0))
                self.seg = seg
                self.log(f"🍃 流畅预设 {fps}fps: 间隔 {iv}ms, 片段取 {seg:.1f}s "
                         f"({OFFICIAL_MAX_FRAMES}帧撑满) — 想要更长只能牺牲流畅哦")
            else:
                self.log(f"🍃 流畅预设 {fps}fps: 间隔已设 {iv}ms (先选视频再拆帧)")
            return self.state()

    def set_frames(self, n):
        """指定帧数: 反推间隔 = 时长/帧数."""
        with self.lock:
            try:
                n = int(n)
            except Exception:
                self.log("!! 帧数得填数字哦…")
                return self.state()
            if n < 1 or n > OFFICIAL_MAX_FRAMES:
                self.log(f"!! 帧数请在 1~{OFFICIAL_MAX_FRAMES} 之间 (官方 GIF 容量上限)…")
                return self.state()
            if self.mode == MODE_IMG:
                self.mode = MODE_ANIM
            if self.info and self.dur() > 0 and self.info["frames"] > 1:
                iv = max(1, min(255, int(round(self.dur() * 1000.0 / n))))
                self.iv = iv
                self.maxn = max(self.maxn, n)
                self.minn = min(self.minn, n)
                if iv == 255 and n * 255 < self.dur() * 1000 * 0.95:
                    self.log(f"已按目标 {n} 帧: 间隔顶到官方最大 255ms, "
                             f"仍会比原视频快 {self.dur()*1000/(n*255):.1f} 倍… "
                             "帧数封顶没法再加了, 把「时长」改短些再点自动适配吧")
                else:
                    self.log(f"已按目标 {n} 帧反推: 间隔 {self.iv}ms → "
                             f"实际 {self.est_frames()} 帧")
            else:
                self.maxn = max(self.maxn, n)
                self.minn = n
            return self.state()

    # ---------- 素材 ----------
    def open_file(self, path):
        with self._open_lock:
            if not os.path.exists(path):
                self.log(f"!! 文件不存在: {path}")
                return None
            try:
                info, first = probe_video(path)
            except Exception as e:
                self.log(f"!! 读取失败: {e}")
                return None
            with self.lock:
                self.file, self.info, self.first = path, info, first
                self.batch, self.rels, self.preview_mp4 = None, [], None
                if info["fps"] <= 0:
                    self.mode = MODE_IMG
                else:
                    self.mode = MODE_ANIM
                    self.seg = 0.0
                    self.t0 = 0.0
                self.phase = "opened"
                stem = os.path.splitext(os.path.basename(path))[0]
                self.anim_name = ("".join(c for c in stem
                                          if c.isalnum() or c in "-_ ")[:20].strip()
                                  or "vk99")
            d = info["w"] / info["h"]
            self.log(f"✓ 已载入 {os.path.basename(path)} "
                     f"({info['w']}x{info['h']}, fps={info['fps']:.1f}, "
                     f"{self.full_dur():.1f}s, 长宽比{d:.2f})")
            if self.driver_ok is None:
                self.driver_ok = check_driver(self.log)
            if info["fps"] > 0:
                self._start_prev()
            return True

    # ---------- 拆帧 ----------
    def _extract(self):
        mode = self.mode
        self.batch = time.strftime("%Y%m%d_%H%M%S")
        outdir = os.path.join(FRAMES_ROOT, self.batch)
        os.makedirs(outdir, exist_ok=True)
        if mode == MODE_IMG or (self.info and self.info["fps"] <= 0):
            self.log("== 单图模式: 裁切导出 1 帧")
            from PIL import Image
            h, w = self.first.shape[:2]
            crop = compute_crop(w, h, self.zoom, self.panx, self.pany)
            Image.fromarray(self.first).crop(crop).resize(
                (TARGET_W, TARGET_H), Image.LANCZOS).save(
                os.path.join(outdir, "f_001.png"))
            rels = [f"{self.batch}/f_001.png"]
        else:
            est = self.est_frames()
            iv = self.eff_iv()
            fps = 1000.0 / iv
            t0 = self.t0
            seg = self.dur()
            if t0 > 0 or abs(seg - self.full_dur()) > 0.01:
                self.log(f"== 拆帧片段: {t0:.1f}s → {t0 + seg:.1f}s (原片 {self.full_dur():.1f}s)")
            self.log(f"== 拆帧: 间隔 {iv}ms → {fps:.2f} fps, 片段取 {est} 帧")
            n = extract_frames_fast(self.file, self.info, fps, self.zoom,
                                    self.panx, self.pany, outdir, est,
                                    t0=t0, seg_len=seg)
            if n > 0:
                self.log(f"   ffmpeg 快速拆帧完成: {n} 帧")
            else:
                self.log("   (ffmpeg 不可用, 改用逐帧扫描…)")
                n = extract_frames(self.file, 1000.0 / self.eff_iv(), self.zoom,
                                   self.panx, self.pany, outdir, max_frames=est,
                                   prefix="f", t0=t0, seg_len=seg,
                                   progress=lambda m: self.log("   " + m))
            if n <= 0:
                raise WriterError("一帧都没拆出来")
            rels = [f"{self.batch}/{nm}" for nm in
                    sorted(x for x in os.listdir(outdir)
                           if x.lower().endswith(".png"))]
        self.rels = rels
        self.log(f"== 拆帧完成: {len(rels)} 帧 → {outdir}")
        pv = make_preview_video(outdir, 1000.0 / self.eff_iv(),
                                os.path.join(outdir, "preview.mp4"),
                                limit=len(rels))
        with self.lock:
            self.preview_mp4 = pv
        return rels

    def prepare(self):
        with self.lock:
            if self.busy:
                return "busy"
            if not self.file:
                self.log("!! 还没有素材…请先点「选择视频 / 图片」")
                return "nofile"
            self.busy, self.cancel = True, False
            self.phase = "preparing"
            self.prog = (0, 0)

        def job():
            try:
                t = time.time()
                self._extract()
                self.log(f"   拆帧耗时 {time.time() - t:.1f}s")
                with self.lock:
                    self.phase = "ready"
            except Exception as e:
                with self.lock:
                    self.phase = "error" if self.file else "idle"
                self.log(f"!! 拆帧失败: {type(e).__name__}: {e}")
            finally:
                with self.lock:
                    self.busy = False
        threading.Thread(target=job, daemon=True).start()
        return "ok"

    # ---------- 写入 ----------
    def _pause_gate(self):
        self.log("⏸ 帧已全部导入官方编辑器, 等你确认画面后点「▶ 继续写入」")
        with self.lock:
            self.phase = "awaiting"
        while not self.resume_evt.wait(0.25):
            if self.cancel:
                raise WriterError("已取消")
        with self.lock:
            self.phase = "writing"
        self.log("▶ 继续写入")
        return self.eff_iv()

    def write_start(self, name):
        with self.lock:
            if self.busy:
                return "busy"
            if not self.file:
                self.log("!! 还没有素材…请先点「选择视频 / 图片」")
                return "nofile"
            if not self.rels:
                self.log("!! 请先「拆帧预览」再写入 (点右上角准备按钮)")
                return "noframes"
            self.anim_name = (name or "").strip() or self.anim_name
            self.busy, self.cancel = True, False
            self.resume_evt.clear()
            self.phase = "writing"
            self.prog = (0, len(self.rels))
            self.log(f"作品命名: {self.anim_name}")

        def work():
            try:
                self.resume_evt.clear()
                rels = self.rels
                self.log("== 连接官方驱动 (没开的话会自动拉起)…")
                w = OfficialWriter(FRAMES_ROOT, log=self.log,
                                   progress=lambda c, t:
                                   self.__dict__.__setitem__("prog", (c, t)))
                self.writer = w
                if self.cancel:
                    raise WriterError("已取消")
                port = w.connect()
                w.write(rels, port, name=self.anim_name,
                        interval=self.eff_iv(), pause_cb=self._pause_gate)
                w.close()
                self.writer = None
                with self.lock:
                    self.phase = "done"
                self.log("✅ 写入完成! 去键盘副屏看看效果吧~")
            except WriterError as e:
                if self.writer:
                    try:
                        self.writer.close()
                    except Exception:
                        pass
                    self.writer = None
                with self.lock:
                    self.phase = "error"
                self.log(f"✗ {'已取消' if self.cancel else e}")
            except Exception as e:
                if self.writer:
                    try:
                        self.writer.close()
                    except Exception:
                        pass
                    self.writer = None
                with self.lock:
                    self.phase = "error"
                self.log(f"✗ {type(e).__name__}: {e}")
                traceback.print_exc()
            finally:
                with self.lock:
                    self.busy = False
        threading.Thread(target=work, daemon=True).start()
        return "ok"

    def resume(self):
        self.resume_evt.set()
        return self.state()

    def cancel_job(self):
        self.cancel = True
        self.resume_evt.set()
        if self.writer:
            try:
                self.writer.cancel = True
            except Exception:
                pass
        self.log("… 正在取消 (等当前步骤收尾)")
        return self.state()

    # ---------- 状态 ----------
    def state(self):
        with self.lock:
            return {
                "phase": self.phase,
                "busy": self.busy,
                "file": os.path.basename(self.file) if self.file else None,
                "mode": self.mode,
                "info": None if not self.info else {
                    "w": self.info["w"], "h": self.info["h"],
                    "fps": round(self.info["fps"], 3),
                    "frames": self.info["frames"],
                    "dur": round(self.full_dur(), 2),
                    "prev": self.prev_state, "prev_pct": self.prev_pct},
                "params": {"iv": self.iv, "maxn": self.maxn, "minn": self.minn,
                           "t0": round(self.t0, 2), "seg": round(self.seg, 2),
                           "zoom": self.zoom, "panx": self.panx,
                           "pany": self.pany},
                "est_frames": self.est_frames(),
                "eff_iv": self.eff_iv(),
                "need_frames": self.need_frames(),
                "dur": round(self.dur(), 2),
                "cap_ms": CAP_MS,
                "max_frames": OFFICIAL_MAX_FRAMES,
                "batch": self.batch,
                "nframes": len(self.rels),
                "preview": bool(self.preview_mp4),
                "name": self.anim_name,
                "driver_ok": self.driver_ok,
                "prog": list(self.prog),
            }


ENG = Engine()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # Range 流播必需: keep-alive + 精确 Content-Length
    def log_message(self, *a):          # 静音访问日志
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods",
                        "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            import json
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        import json
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        try:
            if p == "/api/ping":
                self._send(200, {"ok": True, "port": ENG_PORT[0]})
            elif p == "/api/state":
                self._send(200, ENG.state())
            elif p == "/api/log":
                cur = int((q.get("since") or ["0"])[0])
                lines = ENG.log_since(cur)
                self._send(200, {"lines": lines,
                                 "cursor": lines[-1]["seq"] if lines else cur})
            elif p == "/api/poster.jpg":
                if ENG.first is None:
                    return self._send(404, {"e": "no media"}, "text/plain")
                from PIL import Image
                im = Image.fromarray(ENG.first)
                s = 720 / im.width
                im = im.resize((720, int(im.height * s)), Image.LANCZOS)
                import io
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=82)
                self._send(200, buf.getvalue(), "image/jpeg")
            elif p == "/api/shot.jpg":
                if ENG.first is None:
                    return self._send(404, {"e": "no media"}, "text/plain")
                from PIL import Image
                import io
                h, w = ENG.first.shape[:2]
                crop = compute_crop(w, h, ENG.zoom, ENG.panx, ENG.pany)
                im = Image.fromarray(ENG.first).crop(crop).resize(
                    (TARGET_W * 2, TARGET_H * 2), Image.LANCZOS)
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=85)
                self._send(200, buf.getvalue(), "image/jpeg")
            elif p == "/api/video.mp4":
                if not ENG.preview_mp4 or not os.path.exists(ENG.preview_mp4):
                    return self._send(404, {"e": "no preview"}, "text/plain")
                with open(ENG.preview_mp4, "rb") as fp:
                    self._send(200, fp.read(), "video/mp4")
            elif p == "/api/source":
                # 预览流: 转码产物优先 (H.264 faststart, 万能播);
                # 编码中 503 / 失败回退原文件
                fp = ENG.prev if ENG.prev_state == "ready" and ENG.prev else ENG.file
                if ENG.prev_state == "run" or not fp or not os.path.isfile(fp):
                    if ENG.prev_state in ("run", "none"):
                        return self._send(503, {"e": "transcoding",
                                                "pct": ENG.prev_pct},
                                          "text/plain")
                    return self._send(404, {"e": "no source"}, "text/plain")
                size = os.path.getsize(fp)
                rng = self.headers.get("Range")
                if rng:
                    m = re.match(r"bytes=(\d*)-(\d*)", rng)
                    lo = int(m.group(1)) if m and m.group(1) else 0
                    hi = (int(m.group(2)) if m and m.group(2)
                          else size - 1)
                    hi = min(hi, size - 1)
                    if lo > hi:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    with open(fp, "rb") as f:
                        f.seek(lo)
                        data = f.read(hi - lo + 1)
                    self.send_response(206)
                    self._cors()
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(data)))
                    self.send_header(
                        "Content-Range", f"bytes {lo}-{hi}/{size}")
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    with open(fp, "rb") as f:
                        data = f.read()
                    self.send_response(200)
                    self._cors()
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
            elif p.startswith("/frames/"):
                rel = unquote(p[len("/frames/"):])
                fp = os.path.normpath(os.path.join(FRAMES_ROOT, rel))
                if not fp.startswith(FRAMES_ROOT) or not os.path.isfile(fp):
                    return self._send(404, {"e": "nf"}, "text/plain")
                ext = fp.lower().rsplit(".", 1)[-1]
                ctype = {"png": "image/png", "jpg": "image/jpeg",
                         "jpeg": "image/jpeg", "mp4": "video/mp4"}.get(ext,
                                                                       "application/octet-stream")
                with open(fp, "rb") as f:
                    self._send(200, f.read(), ctype)
            else:
                self._send(404, {"e": "route"}, "text/plain")
        except BrokenPipeError:
            pass
        except Exception as e:
            self._send(500, {"e": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        d = self._json_body()
        try:
            if p == "/api/open":
                r = ENG.open_file(str(d.get("path", "")))
                self._send(200, {"r": r, "state": ENG.state()})
            elif p == "/api/params":
                self._send(200, {"state": ENG.set_params(d)})
            elif p == "/api/autofit":
                self._send(200, {"state": ENG.autofit()})
            elif p == "/api/preset":
                self._send(200, {"state": ENG.preset(float(d.get("fps", 20)))})
            elif p == "/api/setframes":
                self._send(200, {"state": ENG.set_frames(d.get("n"))})
            elif p == "/api/prepare":
                self._send(200, {"r": ENG.prepare(), "state": ENG.state()})
            elif p == "/api/write":
                self._send(200, {"r": ENG.write_start(str(d.get("name", ""))),
                                 "state": ENG.state()})
            elif p == "/api/resume":
                self._send(200, {"state": ENG.resume()})
            elif p == "/api/cancel":
                self._send(200, {"state": ENG.cancel_job()})
            elif p == "/api/quit":
                self._send(200, {"bye": True})
                threading.Thread(target=lambda: os._exit(0),
                                 daemon=True).start()
            else:
                self._send(404, {"e": "route"}, "text/plain")
        except Exception as e:
            self._send(500, {"e": f"{type(e).__name__}: {e}"})


def parent_watchdog():
    """EDEN_PPID 壳进程一旦消失 (崩溃/被杀), 引擎自杀, 不留孤儿占端口."""
    ppid = os.environ.get("EDEN_PPID")
    if not ppid:
        return
    import ctypes
    import ctypes.wintypes as wt
    k32 = ctypes.windll.kernel32
    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    h = k32.OpenProcess(0x100000, False, int(ppid))  # SYNCHRONIZE
    if h:
        k32.WaitForSingleObject(h, 0xFFFFFFFF)       # INFINITE
        os._exit(0)


ENG_PORT = [8793]


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    srv = None
    for port in range(8793, 8813):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            ENG_PORT[0] = port
            break
        except OSError:
            continue
    if srv is None:
        print("EDEN_PORT=FAIL", flush=True)
        sys.exit(1)
    print(f"EDEN_PORT={ENG_PORT[0]}", flush=True)
    threading.Thread(target=parent_watchdog, daemon=True).start()
    ENG.log("EDEN 引擎已就绪 (Tauri 壳)")
    ENG.driver_ok = check_driver(ENG.log)
    srv.serve_forever()


if __name__ == "__main__":
    main()
