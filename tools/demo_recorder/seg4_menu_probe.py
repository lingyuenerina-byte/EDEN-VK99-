# -*- coding: utf-8 -*-
"""社区分享 三种触发对比"""
import sys, time
sys.path.insert(0, ".")
import demo_lib as D
import recorder as R

D.dpi_aware()
w = R.Runner(print, lambda m: None)
w.recover_driver()
w.win = R.bring_front(("Valkyrie Driver",))
w.cur_app = "driver"
c = D.CDP(9223)

def page_tag():
    t = c.js("document.body.innerText") or ""
    if "退出登录" in t:
        return "个人中心"
    if "选择照片" in t:
        return "屏幕设置"
    return "其他:" + t[80:120].replace("\n", "|")

# 1) 祖先 li click via JS
r1 = c.js("""(() => {
  const leaf = [...document.querySelectorAll('*')].find(e => e.childElementCount===0 && e.textContent.trim()==='社区分享');
  let li = leaf; while (li && li.tagName !== 'LI' && !/menu-item/.test(String(li.className))) li = li.parentElement;
  const t = li || leaf;
  t.click();
  return t.tagName + '.' + String(t.className).slice(0, 30);
})()""")
time.sleep(2.5)
print("1) JS li.click ->", r1, page_tag())

# 2) dispatch 完整 pointer 序列
if "个人中心" in page_tag():
    c.call("Input.dispatchMouseEvent", type="mouseMoved", x=98.5, y=528)
    time.sleep(0.15)
    c.call("Input.dispatchMouseEvent", type="mousePressed", x=98.5, y=528, button="left", clickCount=1, buttons=1)
    time.sleep(0.12)
    c.call("Input.dispatchMouseEvent", type="mouseReleased", x=98.5, y=528, button="left", clickCount=1, buttons=0)
    time.sleep(2.5)
    print("2) full pointer seq ->", page_tag())

# 3) 真鼠标 (物理坐标 = client + css*dpr)
if "个人中心" in page_tag():
    vx, vy = w.win["client"]
    px, py = vx + 98.5 * 0.916, vy + 528 * 0.916
    print("3) real mouse to", (px, py))
    D.human_move(int(px), int(py), 500)
    D.click()
    time.sleep(2.5)
    print("3) ->", page_tag())
