#!/usr/bin/env python3
"""vk99_prep.py — VK 99 Max V2 视频预处理工具（阶段一）

导入视频 → 在预览里选 172:320 竖屏裁剪区域 → 按目标帧率拆帧 →
导出编号 PNG（正好 172×320，无黑边）→ 用官方驱动「屏幕设置 → 选择照片」批量顺序导入。

GUI 启动:
  uv run --python 3.12 --with customtkinter,opencv-python,pillow python vk99_prep.py
自检(不开GUI):
  uv run --python 3.12 --with opencv-python,pillow python vk99_prep.py --selftest
"""
import os
import sys
import math

TARGET_W, TARGET_H = 172, 320
ASPECT = TARGET_W / TARGET_H


# ---------- 纯逻辑（GUI / CLI 共用） ----------

def compute_crop(w, h, zoom, panx, pany):
    """zoom>=1, panx/pany∈[0,1]；返回宽高比恒为 172:320 的裁剪框 (x0,y0,x1,y1)。"""
    crop_w0 = min(w, int(round(h * ASPECT)))
    crop_h0 = min(h, int(round(w / ASPECT)))
    cw = max(2, int(round(crop_w0 / zoom)))
    ch = max(2, int(round(cw / ASPECT)))
    if ch > h:
        ch = h
        cw = int(round(ch * ASPECT))
    cw = min(cw, w)
    ch = min(ch, h)
    x0 = int(round(panx * (w - cw)))
    y0 = int(round(pany * (h - ch)))
    return x0, y0, x0 + cw, y0 + ch


def _save_frame(rgb_np, crop, path):
    from PIL import Image
    img = Image.fromarray(rgb_np).crop(crop).resize(
        (TARGET_W, TARGET_H), Image.LANCZOS)
    img.save(path)


def extract_frames(video, target_fps, zoom, panx, pany, outdir,
                   max_frames=999, prefix="vkframe", progress=None,
                   t0=0.0, seg_len=None):
    """逐帧导出；返回保存帧数。支持普通视频(cv2)与 gif(PIL 兜底)。
    t0/seg_len: 只取 [t0, t0+seg_len] 秒这一段 (原速片段选择)."""
    import cv2
    os.makedirs(outdir, exist_ok=True)
    cap = cv2.VideoCapture(video)
    saved = 0
    if cap.isOpened():
        vfps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        step = max(1.0, vfps / float(target_fps))
        if t0 > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(vfps * t0))
        i, next_take = 0, 0.0
        limit = int(seg_len * vfps) if seg_len else 1 << 60
        while saved < max_frames:
            ok, frame = cap.read()
            if not ok or i >= limit:
                break
            if i >= next_take:
                crop = compute_crop(w, h, zoom, panx, pany)
                _save_frame(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), crop,
                            os.path.join(outdir, f"{prefix}_{saved+1:03d}.png"))
                saved += 1
                next_take = i + step
            i += 1
            if progress and i % 100 == 0:
                progress(f"扫描 {i} 帧, 已存 {saved}")
        cap.release()
        return saved
    cap.release()

    # gif 兜底
    from PIL import Image, ImageSequence
    im = Image.open(video)
    w, h = im.size
    for fr in ImageSequence.Iterator(im):
        if saved >= max_frames:
            break
        rgb = fr.convert("RGB")
        _save_frame(__import__("numpy").array(rgb),
                    compute_crop(w, h, zoom, panx, pany),
                    os.path.join(outdir, f"{prefix}_{saved+1:03d}.png"))
        saved += 1
    return saved


def probe_video(video):
    import cv2
    cap = cv2.VideoCapture(video)
    if cap.isOpened():
        info = {
            "fps": cap.get(cv2.CAP_PROP_FPS) or 25.0,
            "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        }
        ok, fr = cap.read()
        first = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB) if ok else None
        cap.release()
        return info, first
    cap.release()
    from PIL import Image
    im = Image.open(video).convert("RGB")
    import numpy as np
    return {"fps": 0, "frames": -1, "w": im.width, "h": im.height}, np.array(im)


# ---------- GUI ----------

def main_gui():
    import customtkinter as ctk
    from tkinter import filedialog, messagebox
    from PIL import Image, ImageTk
    import threading

    ctk.set_appearance_mode("dark")
    CW, CH = 356, 660  # 画布（约 2 倍目标分辨率, 等比）

    class App(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("VK99 副屏视频预处理 — 阶段一 (172×320)")
            self.geometry("900x700")
            self.video = None
            self.rgb = None
            self.w = self.h = 0
            self.info = {}
            self._imgtk = None

            left = ctk.CTkFrame(self)
            left.pack(side="left", fill="y", padx=10, pady=10)
            self.canvas = ctk.CTkCanvas(left, width=CW, height=CH,
                                        bg="black", highlightthickness=1,
                                        highlightcolor="#2aa", takefocus=1)
            self.canvas.pack(padx=8, pady=8)

            r = ctk.CTkFrame(self)
            r.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            ctk.CTkButton(r, text="打开视频 / GIF", command=self.open_video).pack(pady=(12, 4), padx=14, fill="x")
            self.info_lbl = ctk.CTkLabel(r, text="未加载", wraplength=420, justify="left")
            self.info_lbl.pack(padx=14, anchor="w")

            ctk.CTkLabel(r, text="缩放（1=铺满整幅最大区域）").pack(anchor="w", padx=14, pady=(14, 0))
            self.zoom = ctk.CTkSlider(r, from_=100, to=1200, command=self.refresh)
            self.zoom.set(100)
            self.zoom.pack(fill="x", padx=14)
            ctk.CTkLabel(r, text="裁剪框水平位置").pack(anchor="w", padx=14, pady=(10, 0))
            self.panx = ctk.CTkSlider(r, from_=0, to=1000, command=self.refresh)
            self.panx.set(500)
            self.panx.pack(fill="x", padx=14)
            ctk.CTkLabel(r, text="裁剪框垂直位置").pack(anchor="w", padx=14, pady=(10, 0))
            self.pany = ctk.CTkSlider(r, from_=0, to=1000, command=self.refresh)
            self.pany.set(500)
            self.pany.pack(fill="x", padx=14)

            row = ctk.CTkFrame(r, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(14, 0))
            ctk.CTkLabel(row, text="导出帧率 fps:").pack(side="left")
            self.fps = ctk.CTkEntry(row, width=60)
            self.fps.insert(0, "8")
            self.fps.pack(side="left", padx=6)
            ctk.CTkLabel(row, text="最大帧数:").pack(side="left")
            self.maxf = ctk.CTkEntry(row, width=60)
            self.maxf.insert(0, "40")
            self.maxf.pack(side="left", padx=6)

            self.est = ctk.CTkLabel(r, text="", wraplength=420, justify="left",
                                    text_color="#8cc7ff")
            self.est.pack(padx=14, anchor="w", pady=(8, 0))

            ctk.CTkButton(r, text="导出编号帧 PNG", fg_color="#1f8", text_color="black",
                          hover_color="#0d6", command=self.export).pack(pady=(16, 4), padx=14, fill="x")
            self.status = ctk.CTkLabel(r, text="", wraplength=420)
            self.status.pack(padx=14, anchor="w")

            tip = ("流程: 导出后 → 官方驱动「屏幕设置 → 选择照片」\n"
                   "按文件名顺序多选导入 → 写入图片 → 断电重启验证。\n"
                   "注意: 副屏最多 7 页; 视频帧只能做成一页动图, 帧数越少越稳。")
            ctk.CTkLabel(r, text=tip, wraplength=420, justify="left",
                         text_color="#999").pack(padx=14, anchor="w", side="bottom", pady=10)

        def open_video(self):
            path = filedialog.askopenfilename(
                filetypes=[("视频/GIF", "*.mp4 *.mkv *.avi *.mov *.webm *.gif"), ("所有", "*.*")])
            if not path:
                return
            info, first = probe_video(path)
            if first is None:
                messagebox.showerror("错误", "读不了这个文件……")
                return
            self.video, self.info = path, info
            self.rgb = first
            self.h, self.w = first.shape[:2]
            dur = f"{info['frames']/info['fps']:.1f}s" if info["fps"] else "GIF"
            self.info_lbl.configure(
                text=f"{os.path.basename(path)}\n{self.w}×{self.h} @ {info['fps']:.1f}fps, "
                     f"{info['frames']} 帧, 约 {dur}")
            self.refresh()

        def params(self):
            return (self.zoom.get() / 100.0,
                    self.panx.get() / 1000.0,
                    self.pany.get() / 1000.0)

        def refresh(self, *_):
            if self.rgb is None:
                return
            zoom, panx, pany = self.params()
            s = min(CW / self.w, CH / self.h)
            dw, dh = int(self.w * s), int(self.h * s)
            img = Image.fromarray(self.rgb).resize((dw, dh), Image.NEAREST)
            self._imgtk = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(CW // 2, CH // 2, image=self._imgtk)
            x0, y0, x1, y1 = compute_crop(self.w, self.h, zoom, panx, pany)
            ox, oy = (CW - dw) // 2, (CH - dh) // 2
            self.canvas.create_rectangle(ox + x0 * s, oy + y0 * s,
                                         ox + x1 * s, oy + y1 * s,
                                         outline="#0f6", width=2)
            try:
                tf = max(1, int(float(self.fps.get())))
                mf = max(1, int(float(self.maxf.get())))
                vf = self.info.get("frames", -1)
                got = min(mf, int(vf * tf / self.info["fps"]) + 1) if self.info.get("fps") else mf
                self.est.configure(text=f"预计导出 ≈{got} 帧 = {got*110080/1048576:.1f} MB 原始数据 "
                                        f"(官方会压缩)\n每帧传输约 {got and 1966} 包 @7ms ≈ {got*13.8:.0f}s")
            except ValueError:
                self.est.configure(text="")

        def export(self):
            if not self.video:
                messagebox.showinfo("提示", "先打开视频哦")
                return
            outdir = os.path.join(os.path.dirname(self.video),
                                  f"frames_{os.path.splitext(os.path.basename(self.video))[0]}")
            zoom, panx, pany = self.params()
            try:
                tf = max(1.0, float(self.fps.get()))
                mf = max(1, int(self.maxf.get()))
            except ValueError:
                messagebox.showerror("错误", "帧率/帧数得填数字")
                return
            self.status.configure(text=f"导出中 → {outdir}")
            self.update()

            def work():
                try:
                    n = extract_frames(self.video, tf, zoom, panx, pany,
                                       outdir, mf,
                                       progress=lambda m: self.after(0, lambda: self.status.configure(text=m)))
                    self.after(0, lambda: messagebox.showinfo(
                        "完成", f"导出 {n} 帧 →\n{outdir}\n\n去官方驱动「选择照片」按顺序导入吧！"))
                except Exception as e:  # noqa: BLE001
                    self.after(0, lambda e=e: messagebox.showerror("失败", str(e)))
            threading.Thread(target=work, daemon=True).start()

    App().mainloop()


# ---------- 自检 ----------

def selftest():
    import cv2, numpy as np, tempfile
    from PIL import Image
    d = tempfile.mkdtemp(prefix="vk99selftest_")
    vpath = os.path.join(d, "synth.mp4")
    vw = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), 24, (480, 270))
    for i in range(48):  # 2 秒
        f = np.zeros((270, 480, 3), np.uint8)
        f[:, :, 2] = i * 5
        cv2.putText(f, str(i), (200, 135), cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
        vw.write(f)
    vw.release()
    n = extract_frames(vpath, 12, 1.0, 0.5, 0.5, d, max_frames=999)
    assert n > 0, "没导出任何帧"
    for fn in os.listdir(d):
        if fn.startswith("vkframe"):
            im = Image.open(os.path.join(d, fn))
            assert im.size == (TARGET_W, TARGET_H), im.size
    print(f"SELFTEST OK: 导出 {n} 帧, 全部 {TARGET_W}x{TARGET_H}, 目录 {d}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        main_gui()
