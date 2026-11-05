@echo off
call "D:\Visual\NET\VC\Auxiliary\Build\vcvarsall.bat" amd64
set CARGO_HTTP_PROXY=
cd /d C:\Users\Lingy\vk99screen\eden-tauri\src-tauri
cargo build --release
