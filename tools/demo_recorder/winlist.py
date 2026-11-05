# -*- coding: utf-8 -*-
import sys, os, ctypes, ctypes.wintypes as wt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_lib as D

D.dpi_aware()
print('virtual:', D.user32.GetSystemMetrics(76), D.user32.GetSystemMetrics(77),
      D.user32.GetSystemMetrics(78), D.user32.GetSystemMetrics(79))
print('eden pids', D.get_pid_by_name('eden.exe'))
b = ctypes.create_unicode_buffer(256)
found = []

@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, l):
    if D.user32.IsWindowVisible(h):
        if D.user32.GetWindowTextLengthW(h):
            D.user32.GetWindowTextW(h, b, 256)
            r = wt.RECT(); D.user32.GetWindowRect(h, ctypes.byref(r))
            if r.right - r.left > 250 and r.bottom - r.top > 250:
                if any(k in b.value for k in ('EDEN', 'Valkyrie', '幻映')):
                    found.append((h, b.value, r.left, r.top, r.right, r.bottom))
    return True

D.user32.EnumWindows(cb, 0)
for f in found:
    print(f)
