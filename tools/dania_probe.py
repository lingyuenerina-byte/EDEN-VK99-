# -*- coding: utf-8 -*-
import requests
API = "http://127.0.0.1:9880/tts"
REF = r"I:\dania-tts\gsv\output\slicer_opt\ref.wav"
REF_TEXT = "怎么啊？如果有你在也不放心，那就干脆给我也装个限制器或者炸弹喽。"
def try_one(tag, text, ptext):
    r = requests.get(API, params={
        "text": text, "text_lang": "zh",
        "ref_audio_path": REF, "prompt_text": ptext, "prompt_lang": "zh",
        "text_split_method": "cut5", "speed_factor": 0.95,
        "media_type": "wav", "streaming_mode": "false",
    }, timeout=300)
    print(tag, r.status_code, len(r.content))
    if r.status_code == 200 and len(r.content) > 4000:
        open(rf"I:\dania-tts\probe_{tag}.wav", "wb").write(r.content)
try_one("A-short", "你好。", REF_TEXT)
try_one("B-refsame", REF_TEXT, REF_TEXT)
try_one("C-noopenq", "今天天气不错。", "我在这里等你很久了。")
