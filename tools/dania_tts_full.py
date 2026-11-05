# -*- coding: utf-8 -*-
import requests, wave, audioop, io, sys

API = "http://127.0.0.1:9880/tts"
REF = r"I:\dania-tts\gsv\output\slicer_opt\ref.wav"
REF_TEXT = "怎么啊？如果有你在也不放心，那就干脆给我也装个限制器或者炸弹喽。"
LINES = [
    (1, "……灯，还是关掉比较好。"),
    (2, "这样……比较好看。"),
    (3, "不过，你们有没有觉得……这块屏幕，安静了一点。"),
    (4, "说实话，有点麻烦。屏幕设置里，一次只能选一张图……选一张，点一次确定……我数过，导入六十张，要二十多分钟，手腕都会酸。……这样下去，是不行的呢。"),
    (5, "所以后来，我让 Hermes Agent 帮我做了个小工具。整个视频丢进去，它自己拆成一帧一帧……再一帧一帧，交给官方驱动去导入。走的路还是原来那条……只是点鼠标的，换成它了。"),
    (6, "一张图是一个泡泡……现在，是一整段电影了。……呐，这样就很好。"),
]
fails = []
for i, text in LINES:
    out = rf"I:\dania-tts\vo_{i}.wav"
    r = requests.get(API, params={
        "text": text, "text_lang": "zh",
        "ref_audio_path": REF, "prompt_text": REF_TEXT, "prompt_lang": "zh",
        "text_split_method": "cut5", "speed_factor": 0.95,
        "media_type": "wav", "streaming_mode": "false",
    }, timeout=600)
    if r.status_code != 200 or len(r.content) < 4000:
        print(i, "FAIL", r.status_code, r.text[:200]); fails.append(i); continue
    open(out, "wb").write(r.content)
    w = wave.open(io.BytesIO(r.content), "rb")
    d = w.getnframes() / w.getframerate()
    rms = audioop.rms(w.readframes(w.getnframes()), 2)
    print(i, "OK", f"{d:.1f}s", "rms", rms)
print("ALL-OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
