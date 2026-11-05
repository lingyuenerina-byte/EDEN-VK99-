# -*- coding: utf-8 -*-
import requests, wave, audioop, io, sys
API = "http://127.0.0.1:9880/tts"
REF = r"I:\dania-tts\gsv\output\slicer_opt\ref.wav"
REF_TEXT = "怎么啊？如果有你在也不放心，那就干脆给我也装个限制器或者炸弹喽。"
L4 = "说实话，有点麻烦。屏幕设置里，一次只能选一张图……选一张，点一次确定……我数过，导入六十张，要二十多分钟，手腕都会酸。社区里倒是有共享的素材……不过都是160乘50的窄屏，在我们这块屏上，显示不会完整的。……这样下去，是不行的呢。"
L5 = "所以后来，我让 Hermes Agent 帮我做了个小工具。素材这样选进来就好……想更顺滑，就试试流畅度的快捷档。预览框里可以拖着选范围……空格，还能暂停。参数这些，不用动的……拆成帧之后先预览一遍，觉得满意，再点写入键盘副屏。写入的时候，主预览窗和副屏预览，显示的就是导进去以后真正的样子。不满意的话，点进度条左边的原片，重新选一个就好……满意的话，就继续写入。走的路还是原来那条……只是点鼠标的，换成它了。"
ok = True
for tag, text in [("vo_4", L4), ("vo_5", L5)]:
    r = requests.get(API, params={
        "text": text, "text_lang": "zh",
        "ref_audio_path": REF, "prompt_text": REF_TEXT, "prompt_lang": "zh",
        "text_split_method": "cut5", "speed_factor": 0.95,
        "media_type": "wav", "streaming_mode": "false",
    }, timeout=600)
    if r.status_code != 200 or len(r.content) < 4000:
        print(tag, "FAIL", r.status_code, r.text[:200]); ok = False; continue
    open(rf"I:\dania-tts\{tag}.wav", "wb").write(r.content)
    w = wave.open(io.BytesIO(r.content), "rb")
    d = w.getnframes() / w.getframerate()
    rms = audioop.rms(w.readframes(w.getnframes()), 2)
    print(tag, "OK", f"{d:.1f}s", "rms", rms)
sys.exit(0 if ok else 1)
