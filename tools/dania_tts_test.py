# -*- coding: utf-8 -*-
import requests, sys

API = "http://127.0.0.1:9880/tts"
REF_WAV = r"I:\dania-tts\gsv\output\slicer_opt\ref.wav"
REF_TEXT = "怎么啊？如果有你在也不放心，那就干脆给我也装个限制器或者炸弹喽。"

def tts(text, out):
    r = requests.get(API, params={
        "text": text,
        "text_lang": "zh",
        "ref_audio_path": REF_WAV,
        "prompt_text": REF_TEXT,
        "prompt_lang": "zh",
        "text_split_method": "cut5",
        "speed_factor": 0.95,
        "media_type": "wav",
        "streaming_mode": "false",
    }, timeout=300)
    if r.status_code == 200 and len(r.content) > 4000:
        open(out, "wb").write(r.content)
        print("OK", out, len(r.content), "bytes")
        return True
    print("FAIL", r.status_code, r.text[:300])
    return False

lines = [
    ("第六段", "一张图是一个泡泡……现在，是一整段电影了。……呐，这样就很好。",
     r"I:\dania-tts\demo_第六段.wav"),
    ("第四段", "说实话，有点麻烦。屏幕设置里，一次只能选一张图……选一张，点一次确定……我数过，导入六十张，要二十多分钟，手腕都会酸。……这样下去，是不行的呢。",
     r"I:\dania-tts\demo_第四段.wav"),
]
ok = all(tts(t, o) for _, t, o in lines)
sys.exit(0 if ok else 1)
