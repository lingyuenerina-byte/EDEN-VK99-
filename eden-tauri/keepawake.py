"""EDEN 通宵保活: 阻止系统睡眠, 到 04:00 自动放手 (关机任务接手)."""
import ctypes
import datetime
import sys
import time

LOG = r"C:\Users\Lingy\vk99screen\eden-tauri\keepawake.log"

def log(m):
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(datetime.datetime.now().isoformat(timespec="seconds")
                + " " + m + "\n")

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002  # 只保系统不眠, 屏幕随系统方案熄灭

deadline = datetime.datetime(2026, 10, 30, 3, 58)
log("keepawake start pid=%d" % ctypes.windll.kernel32.GetCurrentProcessId())
while datetime.datetime.now() < deadline:
    r = ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    if not r:
        log("SetThreadExecutionState FAILED (被别的程序抢占?)")
    time.sleep(50)
# 放手: 恢复电源策略由系统自管
ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)
log("keepawake exit (deadline reached)")
