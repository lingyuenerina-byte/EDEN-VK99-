# -*- coding: utf-8 -*-
"""把第四段真计划写入 demo_plan.json (保留其他键)"""
import json

P = "demo_plan.json"
plan = json.load(open(P, encoding="utf-8"))

plan["assets"]["photo1"] = "H:/EDENVK/assets/photo1.png"
plan["assets"]["photo2"] = "H:/EDENVK/assets/photo2.png"

plan["第四段"] = [
    {  # n1 3.4s: "说实话，有点麻烦。"
        "n": 1, "app": "driver",
        "steps": [
            {"at": 0.05, "act": "hl", "sel": "text:屏幕设置", "dur": 1.4, "label": "屏幕设置"},
            {"at": 0.30, "act": "move", "sel": "text:选择照片", "ms": 1300}
        ]
    },
    {  # n2 12.5s: 一次只能选一张……点一次确定……手腕都会酸
        "n": 2, "app": "driver",
        "steps": [
            {"at": 0.02, "act": "hl", "sel": "text:选择照片", "dur": 1.1, "label": "一次……只能一张"},
            {"at": 0.10, "act": "cdpclick", "sel": "text:选择照片"},
            {"at": 0.20, "act": "dialog_input", "asset": "photo1"},
            {"at": 0.34, "act": "wait_frames", "n": 1, "timeout": 8},
            {"at": 0.42, "act": "hl", "sel": "text:图片预览", "dur": 1.2, "label": "1 张……才 1 张"},
            {"at": 0.56, "act": "cdpclick", "sel": "text:选择照片"},
            {"at": 0.66, "act": "dialog_input", "asset": "photo2"},
            {"at": 0.80, "act": "hl", "sel": "text:删除所有帧", "dur": 1.2, "label": "不满意……全部重来"},
            {"at": 0.92, "act": "move_win", "frac": [0.78, 0.38], "ms": 1100}
        ]
    },
    {  # n3 10.6s: 社区共享 160x50 窄屏
        "n": 3, "app": "driver",
        "steps": [
            {"at": 0.03, "act": "cdpclick", "sel": "text:社区分享"},
            {"at": 0.18, "act": "hl", "sel": "text:社区分享", "dur": 0.7},
            {"at": 0.34, "act": "cdpclick", "sel": "text:动画分享"},
            {"at": 0.50, "act": "wait_dom", "sel": "body", "state": "true", "timeout": 4},
            {"at": 0.58, "act": "hl", "sel": "text:160x50", "dur": 1.6, "label": "160×50 窄屏……"},
            {"at": 0.74, "act": "hl", "sel": "text:160x50", "dur": 0.9},
            {"at": 0.82, "act": "cdpclick", "sel": "text:屏幕设置"},
            {"at": 0.92, "act": "move", "sel": "text:选择照片", "ms": 800}
        ]
    },
    {  # n4 3.4s: "……这样下去，是不行的呢。"
        "n": 4, "app": "driver",
        "steps": [
            {"at": 0.05, "act": "hl", "sel": "text:选择照片", "dur": 1.5, "label": "……是不行的呢"},
            {"at": 0.40, "act": "move_win", "frac": [0.62, 0.5], "ms": 1600}
        ]
    }
]

json.dump(plan, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("plan 第四段 updated,", len(plan["第四段"]), "clips")
