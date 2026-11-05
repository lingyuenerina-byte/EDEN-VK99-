@echo off
call "D:\Visual\NET\VC\Auxiliary\Build\vcvarsall.bat" amd64
set CARGO_HTTP_PROXY=
set HTTPS_PROXY=
set HTTP_PROXY=
set npm_config_registry=https://registry.npmmirror.com
set npm_config_proxy=
set npm_config_https_proxy=
cd /d C:\Users\Lingy\vk99screen\eden-tauri
call npx --yes @tauri-apps/cli@^2 build --bundles nsis
