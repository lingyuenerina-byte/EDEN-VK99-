#!/usr/bin/env python3
"""vk99_writer.py — 官方驱动 UI 自动化写入器 (供 GUI 调用).

链路: fetch 帧 -> 官方 opener(onImageFileSelected) -> 官方裁切确认(onConfirm)
     -> 添加帧循环 -> 保存(图片/动画) -> 写入(图片/动画).
全程走官方组件自己的回调, 零自制 HID.
"""
import functools
import http.server
import json
import os
import re
import socket
import threading
import time

from vk99_drive import ensure_driver, main_target

# 官方新版把 __reactFiber$ 挂到了祖先链断裂的孤立节点上: 旧版
# querySelectorAll('*') 取到的第一个 fiber 元素上溯不到真根, BFS 全空.
# 改成遍历多个候选元素各自上溯, 选「祖先链最深且真有子树」的当根; 每次扫描
# 都重新定位 (不缓存根, 防 React 重渲染后根失效).
_ROOT_JS = r"""
  let best = null, bd = -1;
  const els = document.querySelectorAll('input,button,textarea,canvas');
  for (let i = 0; i < els.length && i < 80; i++) {
    const k = Object.keys(els[i]).find(x => x.startsWith('__reactFiber$'));
    if (!k) continue;
    let f = els[i][k], d = 0;
    while (f.return && d++ < 200) f = f.return;
    if (d > bd && f.child) { bd = d; best = f; }
  }
  if (!best) return MISSING;
"""


def _js(missing, body):
    return "(() => {\n" + _ROOT_JS.replace("MISSING", missing) + body + "\n})()"


FIND_OPENS = _js("0", r"""
  const seen = new Set(); const q = [best]; const list = [];
  let n = 0;
  while (q.length && list.length < 8 && n++ < 20000) {
    const x = q.shift(); if (!x || seen.has(x)) continue; seen.add(x);
    const p = x.memoizedProps;
    if (p && typeof p === 'object' &&
        typeof p.onImageFileSelected === 'function' &&
        !list.includes(p.onImageFileSelected))
      list.push(p.onImageFileSelected);
    if (x.child) q.push(x.child);
    if (x.sibling) q.push(x.sibling);
  }
  window.__vkOpens = list;
  return list.length;
""")

FIND_OPENS_BTN = r"""(() => {
  const btn = [...document.querySelectorAll('button,div,span')].find(e =>
    e.childElementCount === 0 && e.textContent.trim() === '选择照片');
  if (!btn) return 0;
  const k = Object.keys(btn).find(x => x.startsWith('__reactFiber$'));
  if (!k) return 0;
  let f = btn[k], d = 0; const list = [];
  while (f && d++ < 300) {
    const p = f.memoizedProps;
    if (p && typeof p === 'object' && typeof p.onImageFileSelected === 'function'
        && !list.includes(p.onImageFileSelected))
      list.push(p.onImageFileSelected);
    f = f.return;
  }
  if (list.length) { window.__vkOpens = list; return list.length; }
  return 0;
})()"""

FIND_ALL = _js("{err: 'no-root'}", r"""
  const seen = new Set(); const q = [best];
  let confirmFn = null;
  let n = 0;
  while (q.length && !confirmFn && n++ < 20000) {
    const x = q.shift(); if (!x || seen.has(x)) continue; seen.add(x);
    const p = x.memoizedProps;
    if (p && typeof p === 'object' && typeof p.onConfirm === 'function'
        && p.visible)
      confirmFn = p.onConfirm;
    if (x.child) q.push(x.child);
    if (x.sibling) q.push(x.sibling);
  }
  if (confirmFn) window.__vkConfirm = confirmFn;
  return {confirm: !!confirmFn};
""")


# 宽松版: 不要求 visible=true (弹窗已开但 visible 慢半拍的情况)
FIND_ALL_LOOSE = _js("{err: 'no-root'}", r"""
  const seen = new Set(); const q = [best];
  let confirmFn = null;
  let n = 0;
  while (q.length && !confirmFn && n++ < 20000) {
    const x = q.shift(); if (!x || seen.has(x)) continue; seen.add(x);
    const p = x.memoizedProps;
    if (p && typeof p === 'object' && typeof p.onConfirm === 'function')
      confirmFn = p.onConfirm;
    if (x.child) q.push(x.child);
    if (x.sibling) q.push(x.sibling);
  }
  if (confirmFn) window.__vkConfirm = confirmFn;
  return {confirm: !!confirmFn};
""")


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # 静音
        pass


def free_port(prefer=8901):
    for p in (prefer, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p))
            return s.getsockname()[1]
        except OSError:
            pass
        finally:
            s.close()
    return 0


class WriterError(Exception):
    pass


class OfficialWriter:
    """serve_dir 内必须能按相对路径访问帧文件. log/progress 回调线程内直接调用."""

    def __init__(self, serve_dir, log=None, progress=None):
        self.serve_dir = os.path.abspath(serve_dir)
        self.log = log or (lambda m: None)
        self.progress = progress or (lambda cur, total: None)
        self.cancel = False
        self.tg = None
        self._srv = None

    # ---------- 内部 ----------
    def _js_wait(self, expr, max_s=8, interval=0.4):
        t0 = time.time()
        while time.time() - t0 < max_s:
            if self.cancel:
                return None
            try:
                r = self.tg.js(expr)
                if r:
                    return r
            except Exception:
                pass
            time.sleep(interval)
        return None

    def _click_text(self, txt):
        return self.tg.js(f"""(() => {{
          const cands = [...document.querySelectorAll('*')].filter(e =>
            e.textContent.trim() === {json.dumps(txt)} && e.offsetParent);
          const el = cands[cands.length - 1];
          if (!el) return null;
          el.click(); return 'ok';
        }})()""")

    def _body(self):
        try:
            return self.tg.js("document.body.innerText") or ""
        except Exception:
            return ""

    def _frames(self):
        m = re.search(r"帧数[：:]\s*(\d+)/(\d+)", self._body())
        return (int(m.group(1)), int(m.group(2))) if m else None

    def _to_screen_setting(self):
        # 驱动冷启动时 React 菜单要过几秒才绑定事件, 单次 click 常打空枪.
        # 因此反复「点菜单项 + 查目标页」直到进入, 最长 40s.
        t_end = time.time() + 40
        while time.time() < t_end:
            if self.cancel:
                return False
            hit = self._js_wait("""[...document.querySelectorAll('*')].some(e =>
              e.childElementCount === 0 && e.textContent.trim() === '选择照片')""",
                                0.6, 0.3)
            if hit:
                return True
            self.tg.js("""(() => {
              const t = [...document.querySelectorAll('*')].find(e =>
                e.childElementCount === 0 && e.textContent.trim() === '屏幕设置');
              if (t) t.click();
            })()""")
            time.sleep(1.2)
        return bool(self._js_wait("""[...document.querySelectorAll('*')].some(e =>
          e.childElementCount === 0 && e.textContent.trim() === '选择照片')""",
                                  5))

    def _canvas_mean(self):
        return self.tg.js("""(() => {
          const c=document.querySelector('canvas');
          try{const g=c.getContext('2d',{willReadFrequently:true});
          const d=g.getImageData(0,0,c.width,c.height).data;let s=0;
          for(let i=0;i<d.length;i+=4)s+=d[i]+d[i+1]+d[i+2];
          return Math.round(s/(d.length/4)/3);}catch(e){return -1;}})()""")

    def _wait_done(self, max_s):
        # 注意: 键盘蓝牙初始化时页面会常驻「初始化设备中, 请稍候...」静态文案,
        # 会被旧的「请稍候 出现→消失」判定永久卡死(明明保存成功却报 timeout).
        # 因此剔除该静态文案, 并优先捕捉「保存成功/写入成功」toast.
        STATIC = "初始化设备中, 请稍候"
        t0 = time.time()
        seen_load = False
        while time.time() - t0 < max_s:
            if self.cancel:
                return "cancelled"
            b = self._body().replace(STATIC, "")
            if "保存成功" in b or "写入成功" in b:
                return True
            if "请稍候" in b:
                seen_load = True
            elif seen_load:
                time.sleep(1.0)
                if "请稍候" not in self._body().replace(STATIC, ""):
                    return True
            else:
                time.sleep(0.8)
        return "timeout"

    def _fetch_file(self, rel, port):
        ext = "image/png" if rel.lower().endswith(".png") else "image/jpeg"
        return self.tg.js(f"""
        (async () => {{
          const u = 'http://127.0.0.1:{port}/{rel}';
          const resp = await fetch(u);
          if (!resp.ok) return 'fetch-fail ' + resp.status + ' ' + u;
          const buf = await resp.arrayBuffer();
          window.__vkFile = new File([buf], '{os.path.basename(rel)}', {{type: '{ext}'}});
          return buf.byteLength;
        }})()
        """)

    def _load_frame(self, rel, port):
        """整帧级重试: 单帧失败(含 modal-open-but-no-confirm)重试一次."""
        last = ""
        for attempt in range(2):
            if self.cancel:
                return "cancelled"
            r = self._load_frame_once(rel, port)
            if r == "confirmed":
                return r
            last = str(r)
            self._click_text("取消")
            if attempt == 0:
                time.sleep(1.2)
        return last

    def _load_frame_once(self, rel, port):
        last = ""
        n = self._fetch_file(rel, port)
        if not isinstance(n, int):
            return "fetch:" + str(n)
        self._to_screen_setting()
        # 编辑器加载上一帧时会重挂载组件, 那一刻 fiber 里找不到选图回调
        # (旧版直接返回空串, 报错信息就变成「载入失败: 」后面啥也没有).
        # 6 帧以上时重挂载可能超过 10s: 放宽到 30s, 并加「选择照片」按钮锚点
        # 上溯找回调(比全树 BFS 更便宜), 两路各试一轮.
        cnt = 0
        t_wait = time.time() + 30
        while time.time() < t_wait:
            if self.cancel:
                return "cancelled"
            cnt = self.tg.js(FIND_OPENS_BTN) or self.tg.js(FIND_OPENS) or 0
            if cnt:
                break
            time.sleep(0.3)
        if not cnt:
            body = (self._body() or "")[-160:].replace("\n", " / ")
            return f"no-open-callback (等30s无选图回调, 页面: …{body})"
        for oi in range(cnt or 0):
            if self.cancel:
                return "cancelled"
            self.tg.js(f"""(async () => {{
              try {{ window.__vkOpens[{oi}](window.__vkFile); return 1; }}
              catch (e) {{ return 0; }} }})()""")
            ok = self._js_wait("""(() => {
              return document.body.innerText.includes('滚动滚轮调整图片大小');
            })()""", 4, 0.2)
            if ok:
                # 轮询找确认回调(弹窗刚开时 fiber 可能慢半拍), 再试宽松版
                found = False
                t0 = time.time()
                while not found and time.time() - t0 < 4:
                    rr = self.tg.js(FIND_ALL) or {}
                    found = bool(rr.get("confirm"))
                    if not found:
                        time.sleep(0.2)
                if not found:
                    rr = self.tg.js(FIND_ALL_LOOSE) or {}
                    found = bool(rr.get("confirm"))
                if found:
                    return self.tg.js("""(async () => {
                      try { await window.__vkConfirm('fallback'); return 'confirmed'; }
                      catch (e) { return 'ERR:' + e.message; }
                    })()""")
                last = "modal-open-but-no-confirm"
            else:
                last = f"modal-not-open (opens={cnt})"
            self._click_text("取消")
            time.sleep(0.6)
        return last

    # ---------- 对外 ----------
    def connect(self):
        ensure_driver()
        self.tg = main_target()
        self.tg.call("Runtime.enable")
        self.tg.call("Page.enable")
        if not self._to_screen_setting():
            b = (self._body() or "")
            if "设备搜索中" in b or "欢迎使用" in b:
                raise WriterError("驱动停在「设备搜索中」——请确认键盘已开机且蓝牙已连接, 连上后重试")
            self.log("screen-settings page unavailable, reloading driver UI...")
            self.tg.call("Page.reload")
            self._js_wait("""(() => document.body &&
              document.body.innerText.includes('屏幕设置'))()""", 30, 1.0)
            if not self._to_screen_setting():
                raise WriterError("驱动页面无法进入屏幕设置")
        # 起静态文件服务
        root = self.serve_dir
        # 必须用 partial 显式传 directory: SimpleHTTPRequestHandler.__init__
        # 会把类属性 directory 覆盖成 os.getcwd(), 只设类属性=服务的是当前目录(404 元凶)
        handler = functools.partial(_Quiet, directory=root)
        port = free_port()
        self._srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        self.log(f"frame file server: http://127.0.0.1:{port}/ <- {root}")
        return port

    def _clear_frames(self):
        """动画写入前把编辑器里残留的旧帧全部删掉, 避免新旧帧混在一起.
        点击可能打空: 循环清到空(或连续两轮无进展)为止."""
        if not self._to_screen_setting():
            return
        for _ in range(3):
            fr = self._frames()
            if not fr or fr[0] <= 1:
                return
            self.log(f"editor still holds {fr} old frames, clearing them first...")
            before = fr[0]
            if self._click_text("删除所有帧") != "ok":
                return
            time.sleep(0.6)
            if "确定" in self._body():
                self._click_text("确定")
            time.sleep(0.9)
            after = self._frames()
            self.log(f"   after clear: {after}")
            if not after or after[0] <= 1 or after[0] >= before:
                return

    def _type_name(self):
        """保存弹窗里的名称输入框自动填充用户起的名字, 再点确定."""
        nm = json.dumps(self._name or "vk99")
        r = self.tg.js("""(() => {
          const v = %s;
          const inp = [...document.querySelectorAll('input')].find(i =>
            i.offsetParent !== null && (i.type === 'text' || i.type === ''));
          if (!inp) return 'no-input';
          const st = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          st.call(inp, v);
          inp.dispatchEvent(new Event('input', {bubbles: true}));
          return 'typed';
        })()""" % nm)
        if "确定" in self._body():
            self._click_text("确定")
        return r

    def _set_interval(self, ms):
        """把官方 图片间隔 改成 ms (1~255). 用 JS 合成事件 (活体验证过):
        focus → native setter 写值 → input 事件(官方 onChange 钳1~255改state)
        → keydown Enter(官方 onKeyDown 触发 blur → onBlur 把值写进
        drawingBoard.frameDelay 和写入对象 c.frameDelay) → blur.
        注意: 之前用 CDP 真实键鼠事件, 官方窗口没获得系统焦点时点击根本
        不聚焦输入框(activeElement 停在 BODY), 间隔永远停留在默认 50ms →
        键盘 61帧×50ms=3s 快放. JS focus() 不依赖窗口焦点, 稳定可用.
        校验: 官方 useEffect 在未聚焦时把显示值同步回 store 的 frameDelay,
        所以稳定后读回 == 目标值, 即证明真写进了动画对象."""
        want = max(1, min(255, int(ms)))
        r = self.tg.js("""(() => {
  const ins = [...document.querySelectorAll('input')].filter(
    i => i.offsetParent !== null && !i.closest('.ant-select') &&
         ['text', 'number', ''].includes(i.type));
  let inp = null;
  for (const i2 of ins) {
    let el = i2;
    for (let k = 0; k < 7 && el; k++) {
      el = el.parentElement;
      if (el && (el.innerText || '').includes('图片间隔')) { inp = i2; break; }
    }
    if (inp) break;
  }
  if (!inp) return 'no-interval-input';
  if (inp.disabled) return 'disabled';
  inp.focus();
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value').set;
  setter.call(inp, '%d');
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  inp.dispatchEvent(new KeyboardEvent('keydown',
    { key: 'Enter', code: 'Enter', bubbles: true }));
  inp.blur();
  return 'sent';
})()""" % want)
        if r in ("no-interval-input", "disabled"):
            return r
        time.sleep(1.2)
        got = self.tg.js("""(() => {
  const ins = [...document.querySelectorAll('input')].filter(
    i => i.offsetParent !== null && !i.closest('.ant-select') &&
         ['text', 'number', ''].includes(i.type));
  for (const inp of ins) {
    let el = inp;
    for (let k = 0; k < 7 && el; k++) {
      el = el.parentElement;
      if (el && (el.innerText || '').includes('图片间隔')) return inp.value;
    }
  }
  return '?';
})()""")
        return str(got)

    def write(self, frame_rels, port, name=None, interval=None, pause_cb=None):
        """frame_rels: 相对 serve_dir 的路径列表. 1 帧=图片, 多帧=动画.
        pause_cb: 全部帧导入官方编辑器后、保存前调用; 返回新的图片间隔(ms)."""
        self._name = name or "vk99"
        self._interval = int(interval) if interval else None
        total = len(frame_rels)
        self.log(f"== writing {total} frames")
        if total > 1:
            self._clear_frames()
        r = self._load_frame(frame_rels[0], port)
        self.log(f"   frame 1: {r}")
        if r != "confirmed":
            raise WriterError(f"第 1 帧载入失败: {r}")
        self.progress(1, total)
        # 画布渲染是异步的: 轮询到非空就走, 不再固定等 2 秒
        mean = 0
        for _ in range(8):
            time.sleep(0.5)
            mean = self._canvas_mean()
            if mean > 0 or self.cancel:
                break
        self.log(f"   canvas mean: {mean}")
        if mean == 0:
            raise WriterError("画布是空的, 中止 (不把黑图刷进键盘)")

        if total == 1:
            if pause_cb is not None:
                nv = pause_cb()
                if nv:
                    self._interval = int(nv)
                if self.cancel:
                    raise WriterError("已取消")
            self.log("== saving image (auto name: %s)" % self._name)
            self._click_text("保存图片")
            time.sleep(1.5)
            self._type_name()
            rr = self._wait_done(120)
            if rr is not True:
                raise WriterError(f"保存失败: {rr}")
            time.sleep(1.0)
            self.log("== pushing image (bluetooth may take minutes...)")
            self._click_text("写入图片")
            time.sleep(1.2)
            if "确定" in self._body():
                self._click_text("确定")
            rr = self._wait_done(420)
        else:
            for i, rel in enumerate(frame_rels[1:], 2):
                if self.cancel:
                    raise WriterError("已取消")
                if not self._to_screen_setting():
                    raise WriterError("中途回不到屏幕设置页")
                if self._click_text("添加帧") != "ok":
                    raise WriterError("添加帧不可点")
                time.sleep(0.5)
                r = self._load_frame(rel, port)
                self.log(f"   frame {i}/{total}: {r} (editor: {self._frames()})")
                if r != "confirmed":
                    raise WriterError(f"第 {i} 帧载入失败: {r}")
                self.progress(i, total)
                time.sleep(0.5)
            fr = self._frames()
            if fr and fr[0] < total:
                self.log(f"!! official canvas kept only {fr[0]}/{total} frames (limit {fr[1]}): "
                         f"实际播放约 {fr[0] * (self._interval or 50) / 1000:.1f}s, "
                         "比工作室预算的短, 快放更多 — 缩短片段或减少帧数间隔试算")
                self._kept = fr[0]
            else:
                self._kept = total
            if pause_cb is not None:
                nv = pause_cb()
                if nv:
                    self._interval = int(nv)
                if self.cancel:
                    raise WriterError("已取消")
            self.log("== saving animation (auto name: %s)" % self._name)
            self._click_text("保存动画")
            time.sleep(1.5)
            self._type_name()
            rr = self._wait_done(180)
            if rr is not True:
                raise WriterError(f"保存失败: {rr}")
            time.sleep(1.0)
            if total > 1 and self._interval:
                want = max(1, min(255, int(self._interval)))
                got = self._set_interval(want)
                if str(got) == str(want):
                    self.log(f"   frame interval: {got} ms confirmed in official animation object")
                elif got == "no-interval-input":
                    self.log("   !! interval input not found, set %d ms manually in screen settings" % want)
                else:
                    self.log(f"   !! interval set to {want} but official reads {got} - "
                             f"键盘实际按 {got}ms/帧播放, 请手动确认")
                time.sleep(0.6)
            self.log(f"== writing animation {total} frames (may take minutes...)")
            self._click_text("写入动画")
            time.sleep(1.2)
            if "确定" in self._body():
                self._click_text("确定")
            rr = self._wait_done(300 + 300 * total)
        if rr is not True:
            raise WriterError(f"写入未正常结束: {rr}")
        self.log(f"== done, frames in editor: {self._frames()}")

    def close(self):
        if self._srv:
            try:
                self._srv.shutdown()
                self._srv.server_close()
            except Exception:
                pass
            self._srv = None


# ================= 自检 (不碰键盘) =================
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if "--selftest" in sys.argv:
        # 1) 模块可导入 + Writer 可实例化
        w = OfficialWriter(os.path.dirname(os.path.abspath(__file__)))
        # 2) 静态服务能起
        port = None
        root = os.path.dirname(os.path.abspath(__file__))
        # 必须用 partial 显式传 directory: SimpleHTTPRequestHandler.__init__
        # 会把类属性 directory 覆盖成 os.getcwd(), 只设类属性=服务的是当前目录(404 元凶)
        handler = functools.partial(_Quiet, directory=root)
        port = free_port()
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        import urllib.request
        data = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/animtest/f1.png", timeout=3).read()
        srv.shutdown()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", "服务读到的不是 PNG"
        print(f"SELFTEST OK: writer 实例化 + 静态服务 127.0.0.1:{port} 取帧 {len(data)}B")
    else:
        print("用法: python vk99_writer.py --selftest")
