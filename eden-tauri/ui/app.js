// EDEN-VK99Ⅱ「幻映」前端 — 全部业务走 sidecar HTTP.
// v1.1: 舞台原片可直接播放(Range 流), 底部时间轴拖动选段(旧 studio 功能), 原片/成片切换.
(() => {
  const $ = (id) => document.getElementById(id);
  const ASPECT = 172 / 320;
  const invoke = (window.__TAURI__ && window.__TAURI__.core.invoke)
    ? (c, a) => window.__TAURI__.core.invoke(c, a) : null;

  let BASE = null;          // http://127.0.0.1:PORT
  let st = null;            // 最近一次 /api/state
  let logCur = 0;
  let paramTimer = null;    // 参数防抖
  let userScrolledLog = false;
  let stageMode = "src";    // src=原片 fx=拆帧成片
  let lastBatch = null;

  const api = async (path, method = "GET", body = null) => {
    const opt = { method, headers: { "Content-Type": "application/json" } };
    if (body) opt.body = JSON.stringify(body);
    const r = await fetch(BASE + path, opt);
    return r.json();
  };
  const isImageFile = (f) => /\.(jpe?g|png|gif|webp|bmp)$/i.test(f || "");

  // ---------- 启动: 等 sidecar 端口 ----------
  async function boot() {
    let tries = 0;
    while (!BASE && tries++ < 600) {
      if (invoke) {
        const p = await invoke("sidecar_port").catch(() => 0);
        if (p > 0 && await ping(p)) BASE = `http://127.0.0.1:${p}`;
      } else if (await ping(8793)) { BASE = "http://127.0.0.1:8793"; }
      if (!BASE && tries % 10 === 0)
        $("bootmsg").textContent =
          `还在等引擎起来哦… (${Math.round(tries / 2)}s) 首次启动要下依赖, 稍安勿躁~`;
      await new Promise((r) => setTimeout(r, 500));
    }
    if (!BASE) { $("bootmsg").textContent = "!! 引擎起不来… 请看日志排查"; return; }
    $("boot").remove();
    $("app").hidden = false;
    setInterval(pollState, 700);
    setInterval(pollLog, 600);
    pollState(); pollLog();
  }
  const ping = async (p) => {
    try {
      const r = await fetch(`http://127.0.0.1:${p}/api/ping`,
                            { signal: AbortSignal.timeout(900) });
      return r.ok;
    } catch { return false; }
  };

  // ---------- 状态轮询 ----------
  async function pollState() {
    try { st = await api("/api/state"); } catch { return; }
    // 新拆帧完成 → 自动切到成片预览
    if (st.batch && st.batch !== lastBatch &&
        ["ready", "writing", "awaiting", "done"].includes(st.phase)) {
      lastBatch = st.batch;
      stageMode = "fx";
    }
    render();
  }
  async function pollLog() {
    try {
      const d = await api(`/api/log?since=${logCur}`);
      for (const ln of d.lines) appendLog(ln.m);
      logCur = d.cursor;
    } catch { /* sidecar 重启中 */ }
  }
  function appendLog(m) {
    const el = document.createElement("div");
    el.textContent = m;
    if (/^[✗!]/.test(m)) el.className = "t-err";
    else if (/^[✓✅]/.test(m)) el.className = "t-ok";
    else if (/^[⚡🍃⏸]/.test(m)) el.className = "t-warn";
    $("log").appendChild(el);
    while ($("log").children.length > 700) $("log").firstChild.remove();
    if (!userScrolledLog) $("log").scrollTop = $("log").scrollHeight;
  }
  $("log").addEventListener("scroll", () => {
    const el = $("log");
    userScrolledLog = el.scrollHeight - el.scrollTop - el.clientHeight > 40;
  });

  // ---------- 渲染 ----------
  const setVal = (id, v) => {
    const el = $(id);
    if (document.activeElement !== el) el.value = v;
  };
  function render() {
    if (!st) return;
    const P = st.params;
    setVal("iv", P.iv); setVal("maxn", P.maxn); setVal("minn", P.minn);
    setVal("t0", P.t0); setVal("seg", P.seg);
    setVal("zoom", P.zoom); $("zoomval").textContent = P.zoom.toFixed(2) + "×";
    if (document.activeElement !== $("animname")) setVal("animname", st.name);

    // 素材/舞台
    const has = !!st.file;
    $("fname").textContent = has ? st.file : "未选择";
    $("noimg").style.display = has ? "none" : "flex";
    if (has && $("poster").dataset.for !== st.file) {
      $("poster").dataset.for = st.file;
      $("poster").src = `${BASE}/api/poster.jpg?t=${Date.now()}`;
      $("poster").onload = layoutCrop;
    }
    applyStage();
    layoutTimeline();

    // 预估行 (安全说明: 拼接的全是服务端数值字段, 无用户自由文本入 innerHTML)
    const speed = st.dur > 0 ? (st.est_frames * st.eff_iv) / (st.dur * 1000) : 1;
    $("estline").innerHTML = st.info
      ? `预估 <b>${st.est_frames}</b> 帧 · 间隔 <b>${st.eff_iv}ms</b> ` +
        `(速度×${speed.toFixed(2)}${Math.abs(speed - 1) < 0.02 ? " · 原速" : ""})` +
        `<br>素材 ${st.info.dur}s · 原速最长需 ${st.need_frames} 帧 ` +
        `· 容量上限 61 帧≈${(61 * 255 / 1000).toFixed(1)}s`
      : "— 载入素材后显示预估 —";
    $("stageinfo").innerHTML = st.info
      ? `尺寸 ${st.info.w}×${st.info.h} · fps ${st.info.fps}<br>` +
        `时长 ${st.info.dur}s · 片段 ${st.dur}s<br>` +
        (st.mode === "动画"
          ? (st.info.prev === "run"
              ? `⏳ 预览编码中 ${st.info.prev_pct || 0}% …完成后自动可播`
              : st.info.prev === "fail"
                ? "⚠ 预览转码失败: 仅显示首帧海报 (写入不受影响)"
                : "下方时间轴拖动=选段 · 双击=全片<br>粉框=取景 · 滚轮/滑块=放大<br>空格或进度条=播放暂停原片")
          : "单张图片: 取景后直接写入 1 帧")
      : "";

    // 徽章
    const d = st.driver_ok;
    const db = $("drvbadge");
    db.textContent = d === null ? "驱动检测中…" : d ? "✓ 官方驱动在线" : "✗ 无官方驱动";
    db.className = "badge " + (d ? "ok" : d === null ? "gray" : "bad");
    const PH = { idle: ["待命", "gray"], opened: ["素材已载", ""],
      preparing: ["拆帧中…", "warn"], ready: ["已拆帧 ✓", "ok"],
      writing: ["写入中…", "warn"], awaiting: ["等你确认 ✋", "bad"],
      done: ["完成 🎉", "ok"], error: ["出错", "bad"] };
    const [txt, cls] = PH[st.phase] || ["?", "gray"];
    $("phasebadge").textContent = txt;
    $("phasebadge").className = "badge " + cls;

    // 按钮
    const busy = st.busy;
    $("btnPick").disabled = busy;
    $("btnPrep").disabled = !st.file || busy;
    $("btnWrite").disabled = !(st.nframes > 0) || busy;
    document.querySelectorAll(".preset").forEach((b) => b.disabled = busy);
    $("btnResume").hidden = st.phase !== "awaiting";
    $("btnCancel").hidden = !(busy &&
      ["writing", "awaiting", "preparing"].includes(st.phase));
    // 原片/成片切换 chip
    $("chipFx").disabled = !(st.nframes > 0);
    if (stageMode === "fx" && !(st.nframes > 0)) stageMode = "src";
    $("chipSrc").classList.toggle("on", stageMode === "src");
    $("chipFx").classList.toggle("on", stageMode === "fx");

    // 进度
    const show = busy && st.prog[1] > 0;
    $("progrow").hidden = !show;
    if (show) {
      const [c, t] = st.prog;
      $("progbar").style.width = (100 * c / Math.max(t, 1)) + "%";
      $("progtxt").textContent = `${c} / ${t}`;
    }
  }

  // ---------- 舞台播放器: 原片即载即播 / 成片 ----------
  function applyStage() {
    const v = $("anim"), p = $("poster");
    const has = st && st.file;
    const imgSrc = has && isImageFile(st.file);
    const fx = stageMode === "fx" && st.batch && !imgSrc;
    const useVideo = has && !imgSrc;
    v.hidden = !useVideo;
    p.style.visibility = (useVideo && !v.dataset.key) ? "visible"
      : (useVideo ? "hidden" : "visible");
    if (!useVideo) { v.removeAttribute("src"); v.dataset.key = ""; return; }
    // 源视频预览需等 sidecar 转码完成 (H.264 faststart), 否则 WebView2 可能播不了
    // 源视频预览: 只播转码好的 H.264 faststart; 失败时保持首帧海报,
    // 绝不直挂原片 (HEVC/10bit 等 WebView2 解不了 = 黑屏+解码卡顿)
    const prevReady = fx || !st.info || st.info.prev === "ready";
    const key = fx ? "fx:" + st.batch
                   : "src:" + st.file + ":" + (st.info ? st.info.prev : "");
    if (v.dataset.key !== key && prevReady) {
      v.dataset.key = key;
      v.loop = !!fx;
      v.src = fx ? `${BASE}/api/video.mp4?t=${Date.now()}`
                 : `${BASE}/api/source?t=${Date.now()}`;
      v.onloadedmetadata = layoutCrop;
      if (fx) v.play().catch(() => {});
    }
    if (!prevReady) { v.dataset.key = ""; }   // 编码中: 保持海报
    layoutCrop();
  }

  // ---------- 播放控制: 选段循环 + 播放头 ----------
  function segWindow() {
    if (!st || !st.info || !st.info.dur) return null;
    const dur = st.info.dur, P = st.params;
    const t0 = Math.min(P.t0 || 0, dur);
    const span = Math.max(0.01, Math.min(P.seg > 0 ? P.seg : dur - t0, dur - t0));
    return [t0, t0 + span];
  }
  function togglePlay() {
    const v = $("anim");
    if (v.hidden || !v.getAttribute("src")) return;
    if (v.paused) {
      if (stageMode === "src") {
        const w = segWindow();
        if (w && (v.currentTime >= w[1] - 0.05 || v.currentTime < w[0] - 0.05))
          v.currentTime = w[0];          // 从选段起点播
      }
      v.play().catch(() => {});
    } else v.pause();
  }
  function syncPlayBtn() {
    const v = $("anim");
    const playing = !v.paused && !v.hidden && !!v.getAttribute("src");
    const b = $("btnPlay");
    b.classList.toggle("on", playing);
    b.innerHTML = playing
      ? '<svg viewBox="0 0 24 24"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>暂停'
      : '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>播放';
  }
  ["play", "pause", "ended"].forEach((ev) =>
    $("anim").addEventListener(ev, syncPlayBtn));
  $("anim").addEventListener("click", togglePlay);   // 点画面也能播/停
  $("btnPlay").addEventListener("click", togglePlay);
  $("anim").addEventListener("timeupdate", () => {
    const v = $("anim"), head = $("tlHead");
    if (stageMode !== "src") { head.hidden = true; return; }
    const w = segWindow(); if (!w) { head.hidden = true; return; }
    if (!v.paused &&
        (v.currentTime >= w[1] - 0.03 || v.currentTime < w[0] - 0.15))
      v.currentTime = w[0];              // 片段循环 (和键盘副屏播放一致)
    head.hidden = false;
    head.style.left = (100 * Math.max(0, Math.min(1,
      (v.currentTime - w[0]) / Math.max(0.01, w[1] - w[0])))) + "%";
  });

  // ---------- 取景框几何 (compute_crop 同款公式) ----------
  function cropBoxXYWH() {
    if (!st || !st.info) return null;
    const { w, h } = st.info, P = st.params;
    const crop_w0 = Math.min(w, Math.round(h * ASPECT));
    let cw = Math.max(2, Math.round(crop_w0 / P.zoom));
    let ch = Math.max(2, Math.round(cw / ASPECT));
    if (ch > h) { ch = h; cw = Math.round(ch * ASPECT); }
    cw = Math.min(cw, w); ch = Math.min(ch, h);
    return { cw, ch,
      x: Math.round(P.panx * (w - cw)), y: Math.round(P.pany * (h - ch)) };
  }
  // 参考元素的实际画面显示矩形 (video contain 后可能留黑边)
  function refRect() {
    const v = $("anim");
    if (!v.hidden && st && st.info) {
      const s = Math.min(v.clientWidth / st.info.w, v.clientHeight / st.info.h);
      return { el: v, sx: s };
    }
    return { el: $("poster"), sx: 0 };
  }
  function layoutCrop() {
    const box = $("cropbox");
    // 单图 / 成片播放中 / 无素材 → 不隐藏取景框? 成片时框无意义, 隐藏
    if (!st || !st.info || st.mode !== "动画" || stageMode === "fx") {
      box.hidden = true; return;
    }
    const { el } = refRect();
    if (!el.clientWidth) { box.hidden = true; return; }
    box.hidden = false;
    const g = cropBoxXYWH();
    if (!g) return;
    const { w, h } = st.info;
    let dispW, dispH, offX, offY;
    if (el.tagName === "VIDEO") {
      const s = Math.min(el.clientWidth / w, el.clientHeight / h);
      dispW = w * s; dispH = h * s;
      offX = el.offsetLeft + (el.clientWidth - dispW) / 2;
      offY = el.offsetTop + (el.clientHeight - dispH) / 2;
    } else {
      dispW = el.clientWidth; dispH = el.clientHeight;
      offX = el.offsetLeft; offY = el.offsetTop;
    }
    box.style.width = (g.cw / w * dispW) + "px";
    box.style.height = (g.ch / h * dispH) + "px";
    box.style.left = (offX + g.x / w * dispW) + "px";
    box.style.top = (offY + g.y / h * dispH) + "px";
    box._dispW = dispW; box._vw = w;   // 供拖动换算
    refreshShot();
  }
  let shotT = 0, shotTimer = null;
  function refreshShot() {
    const now = Date.now();
    clearTimeout(shotTimer);
    shotTimer = setTimeout(() => {
      $("shot").src = `${BASE}/api/shot.jpg?t=${now}`;
    }, 120);
  }

  // ---------- 参数提交 (防抖) ----------
  function postParams(d) {
    clearTimeout(paramTimer);
    paramTimer = setTimeout(async () => {
      try { st = (await api("/api/params", "POST", d)).state; render(); }
      catch { /* 忽略瞬断 */ }
    }, 90);
  }
  const num = (id) => parseFloat($(id).value || "0");
  ["iv", "maxn", "minn", "t0", "seg"].forEach((id) => {
    $(id).addEventListener("change", () => postParams({ [id]: num(id) }));
  });
  $("zoom").addEventListener("input", () =>
    postParams({ zoom: parseFloat($("zoom").value) }));

  // ---------- 时间轴: 拖动选段 ----------
  function layoutTimeline() {
    const ok = st && st.info && st.mode === "动画" && !isImageFile(st.file);
    $("trow").hidden = !ok;
    if (!ok) return;
    const dur = st.info.dur || 0.001;
    const t0 = Math.min(st.params.t0, dur);
    const span = Math.max(0.01, Math.min(st.dur || dur - t0, dur - t0));
    const seg = $("tlSeg");
    seg.style.left = (100 * t0 / dur) + "%";
    seg.style.width = (100 * span / dur) + "%";
    $("tlRead").textContent =
      span >= dur - 0.05 ? `全片 ${dur.toFixed(1)}s`
        : `${t0.toFixed(1)}–${(t0 + span).toFixed(1)}s / ${dur.toFixed(1)}s`;
  }
  let tl = null;    // {mode: move|l|r|new, x0, t0, span}
  const trackSec = (clientX) => {
    const r = $("tlTrack").getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    return f * (st.info ? st.info.dur : 0);
  };
  $("tlTrack").addEventListener("pointerdown", (e) => {
    if (!st || !st.info) return;
    e.preventDefault();
    const dur = st.info.dur;
    const t0 = st.params.t0, span = st.dur || dur - t0;
    const s = trackSec(e.clientX);
    let mode = "new";
    if (e.target.classList.contains("tl-l")) mode = "l";
    else if (e.target.classList.contains("tl-r")) mode = "r";
    else if (s >= t0 && s <= t0 + span) mode = "move";
    tl = { mode, x0: s, t0, span, dur };
    $("tlTrack").setPointerCapture(e.pointerId);
    if (mode === "new") tl.t0 = s; tl.span = 0.01;
    if (mode === "move" || mode === "l" || mode === "r") {
      tl.t0 = t0; tl.span = span;
    }
  });
  window.addEventListener("pointermove", (e) => {
    if (!tl || !st || !st.info) return;
    const { mode, x0, dur } = tl;
    let t0 = tl.t0, span = tl.span;
    const s = trackSec(e.clientX);
    if (mode === "move") {
      t0 = Math.max(0, Math.min(dur - span, x0 + (s - x0)));
    } else if (mode === "l") {
      const ns = Math.max(0.1, tl.t0 + tl.span - s);   // 左缘右移→时长缩
      t0 = Math.max(0, Math.min(s, tl.t0 + tl.span - 0.1));
      span = tl.t0 + tl.span - t0;
    } else if (mode === "r") {
      span = Math.max(0.1, Math.min(dur - tl.t0, s - tl.t0));
      t0 = tl.t0;
    } else { // new: 从按下点拖出
      t0 = Math.max(0, Math.min(x0, s));
      span = Math.max(0.1, Math.min(s, dur) - t0);
    }
    tl.t0 = t0; tl.span = span;
    // 本地先行更新, 避免等待感
    st.params.t0 = +t0.toFixed(2);
    const full = span >= dur - 0.05;
    st.params.seg = full ? 0 : +span.toFixed(2);
    st.dur = span;
    layoutTimeline(); layoutCrop();
    postParams({ t0: +t0.toFixed(2), seg: full ? 0 : +span.toFixed(2) });
  });
  window.addEventListener("pointerup", () => { tl = null; });
  $("tlTrack").addEventListener("dblclick", () => {
    if (!st || !st.info) return;
    st.params.t0 = 0; st.params.seg = 0; st.dur = st.info.dur;
    layoutTimeline(); layoutCrop();
    postParams({ t0: 0, seg: 0 });
  });

  // ---------- 框拖动 / 滚轮缩放 ----------
  let drag = null;
  $("cropbox").addEventListener("pointerdown", (e) => {
    e.preventDefault();
    const g = cropBoxXYWH();
    drag = { sx: e.clientX, sy: e.clientY, ox: g.x, oy: g.y, g };
    $("cropbox").setPointerCapture(e.pointerId);
  });
  window.addEventListener("pointermove", (e) => {
    if (!drag || !st) return;
    const dispW = $("cropbox")._dispW || $("poster").clientWidth;
    const scale = st.info.w / Math.max(dispW, 1);   // 显示px→视频px
    const nx = drag.ox + (e.clientX - drag.sx) * scale;
    const ny = drag.oy + (e.clientY - drag.sy) * scale;
    const mx = Math.max(0, Math.min(st.info.w - drag.g.cw, nx));
    const my = Math.max(0, Math.min(st.info.h - drag.g.ch, ny));
    st.params.panx = mx / Math.max(st.info.w - drag.g.cw, 1);
    st.params.pany = my / Math.max(st.info.h - drag.g.ch, 1);
    layoutCrop();
    postParams({ panx: +st.params.panx.toFixed(4),
                 pany: +st.params.pany.toFixed(4) });
  });
  window.addEventListener("pointerup", () => { drag = null; });
  $("stage").addEventListener("wheel", (e) => {
    if (!st || !st.info || stageMode === "fx") return;
    e.preventDefault();
    const z = Math.max(1, Math.min(4,
      st.params.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08)));
    st.params.zoom = z;
    $("zoom").value = z;
    postParams({ zoom: +z.toFixed(3) });
  }, { passive: false });

  // ---------- chip: 原片 / 成片 ----------
  $("chipSrc").addEventListener("click", () => { stageMode = "src"; applyStage(); render(); });
  $("chipFx").addEventListener("click", () => {
    if (!st || !(st.nframes > 0)) return;
    stageMode = "fx"; applyStage(); render();
  });

  // ---------- 按钮 ----------
  $("btnPick").addEventListener("click", async () => {
    if (!invoke) { appendLog("!! 浏览器直开模式没有原生文件框, 请用 EXE 启动"); return; }
    const p = await invoke("pick_file");
    if (!p) return;
    appendLog(`… 正在读取素材: ${p}`);
    const d = await api("/api/open", "POST", { path: p });
    stageMode = "src"; lastBatch = null;
    st = d.state; render();
  });
  // 模式固定为动画 (单图入口已移除)
  document.querySelectorAll(".preset").forEach((b) =>
    b.addEventListener("click", async () => {
      st = (await api("/api/preset", "POST", { fps: +b.dataset.fps })).state;
      render();
    }));
  $("btnSpec").addEventListener("click", async () => {
    st = (await api("/api/setframes", "POST", { n: num("specn") })).state;
    render();
  });
  $("btnPrep").addEventListener("click", async () => {
    await api("/api/prepare", "POST"); pollState();
  });
  $("btnWrite").addEventListener("click", async () => {
    await api("/api/write", "POST", { name: $("animname").value });
    pollState();
  });
  $("btnResume").addEventListener("click", async () => {
    st = (await api("/api/resume", "POST")).state; render();
  });
  $("btnCancel").addEventListener("click", async () => {
    st = (await api("/api/cancel", "POST")).state; render();
  });
  // 空格 = 播放/暂停 (原片与成片都可, 沿用旧 studio 习惯)
  window.addEventListener("keydown", (e) => {
    if (e.code === "Space" && document.activeElement.tagName !== "INPUT") {
      e.preventDefault();
      togglePlay();
    }
  });

  boot();
})();
