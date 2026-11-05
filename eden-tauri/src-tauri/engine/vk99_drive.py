#!/usr/bin/env python3
"""vk99_drive.py — CDP 操作官方 Valkyrie Driver UI:
注入帧文件到「选择照片」input + 点「写入图片」, 全部由官方软件自己写键盘.
用法:
  python vk99_drive.py probe               # 列出页面+屏幕设置区结构
  python vk99_drive.py inject <dir>        # 注入帧(不自动点写入, 人工确认)
"""
import glob
import json
import subprocess
import sys
import time
import urllib.request

import websocket

EXE = r"C:\Users\Lingy\AppData\Local\Programs\Valkyrie Driver\Valkyrie Driver.exe"
PORT = 9223


def ensure_driver():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
        return
    except Exception:
        pass
    # 重启带调试口的驱动
    subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                    "Get-Process | Where-Object {$_.Name -like '*Valkyrie*'} | Stop-Process -Force"],
                   capture_output=True)
    time.sleep(1.5)
    subprocess.Popen([EXE, f"--remote-debugging-port={PORT}", "--remote-allow-origins=*"],
                     creationflags=0x00000008)  # DETACHED
    for _ in range(20):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
            return
        except Exception:
            continue
    raise SystemExit("!! 驱动调试口起不来")


class Target:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=15,
                                              header=["Origin: http://127.0.0.1"])
        self.id = 0

    def call(self, method, **params):
        self.id += 1
        self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        r = self.call("Runtime.evaluate", expression=expr,
                      returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


def main_target():
    data = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
    pages = [t for t in data if t.get("type") == "page"]
    for t in pages:
        print("page:", t.get("url", "")[:80], "|", t.get("title", "")[:30])
    main = next((t for t in pages if "file://" in t.get("url", "")), pages[0])
    return Target(main["webSocketDebuggerUrl"])


FIND_INPUT = r"""
(() => {
  const ins = [...document.querySelectorAll('input[type=file]')];
  return ins.map((i, n) => {
    i.setAttribute('data-vkprobe', n);
    return {idx: n, accept: i.accept, multiple: i.multiple,
            visible: !!(i.offsetParent), cls: i.className.slice(0,40)};
  });
})()
"""

PAGE_TEXT = r"""
(() => {
  const t = document.body.innerText.replace(/\s+/g, ' ');
  return t.slice(0, 600);
})()
"""


def probe():
    tg = main_target()
    tg.call("Runtime.enable")
    # 等前端渲染
    for _ in range(10):
        txt = tg.js(PAGE_TEXT)
        if txt and len(txt) > 10:
            break
        time.sleep(1.5)
    print("页面文本:", json.dumps(tg.js(PAGE_TEXT), ensure_ascii=False)[:600])
    print("file inputs:", tg.js(FIND_INPUT))
    print("frames:", json.dumps(tg.call("Page.getFrameTree"), ensure_ascii=False)[:800])
    print("webviews:", tg.js(
        "document.querySelectorAll('webview,iframe').length + ' | ' + "
        "[...document.querySelectorAll('webview,iframe')].map(w=>w.src||w.getAttribute('src')||'?').join(',')"))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    ensure_driver()
    if cmd == "probe":
        probe()
