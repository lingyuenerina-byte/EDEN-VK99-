# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, ".")
import demo_lib as D

d = D.CDP(9224)
tail = d.js("(()=>{const x=document.querySelector('#log');return x?x.innerText.slice(-150):'?'})()")
print("eden log tail:", (tail or "").replace("\n", " / ")[:150])
e = D.CDP(9223)
print("driver 成功:", e.js("document.body.innerText.includes('成功')"))
print("driver 请稍候:", e.js("document.body.innerText.includes('请稍候')"))
