@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "eden-tauri\src-tauri\target\release\eden.exe" (
  start "" "eden-tauri\src-tauri\target\release\eden.exe"
) else (
  echo 还没编译好哦… 请先在 eden-tauri\src-tauri 跑 cargo build --release
  pause
)
exit
