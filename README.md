# EDEN-VK99II「幻映」

> 视频 → 键盘副屏，一键刷入。作者：LingyueNerina

为 Valkyrie V99 Pro（VK99）键盘的 **172×320 副屏**制作并写入动画 / 单帧图片的 Windows 桌面工具。选择任意视频或图片素材，自动完成裁切、缩放、逐帧预览，再经官方 Valkyrie Driver 的界面自动化把内容刷进键盘副屏——**零自制 HID、零魔改驱动**。

## 功能

- 视频 / GIF / 图片导入，实时预览窗（自动转码 H.264，HEVC / 10bit 也能播）
- 172×320 竖屏取景：起点、片段时长、缩放、平移、帧率全可调
- 一键贴合原速（官方 GIF 槽物理上限 61 帧 ≈ 15.5s，超限自动收敛）
- 逐帧写入键盘副屏，支持断点续写与取消
- 官方驱动未安装时自动弹出随包安装程序

## 架构

| 层 | 技术 |
|---|---|
| 桌面壳 | Tauri v2 (Rust) + WebView2 |
| 引擎 | Python sidecar，HTTP API 监听 `127.0.0.1:8793~8812`（被占自增，单实例复用） |
| 写入通道 | Chrome DevTools Protocol 驱动官方 Valkyrie Driver UI（`vk99_writer.py`） |

引擎端口与 API 见 `engine/README.md`（打包目录内的侧车说明）。

## 安装

1. 下载 Releases 里的 `EDEN-VK99II_<ver>_x64-setup.exe` 安装；
2. 确保已安装官方 **Valkyrie Driver**（`%LOCALAPPDATA%\Programs\Valkyrie Driver\`），没有的话软件会拉起随包安装程序，装不装由你决定；
3. 插上 VK99 键盘，启动 EDEN-VK99II。

首次启动会较慢（Windows Defender 需要扫描随包的 Python 运行库，约 10~40 秒；之后恢复秒级。可在「病毒和威胁防护 → 排除项」中添加 `%LOCALAPPDATA%\EDEN\venv` 提速）。

## 从源码构建

前置：Rust (MSVC)、Node 无需（前端为纯静态 JS）、[uv](https://docs.astral.sh/uv/)、Python 3.12、NSIS 由 Tauri 自动获取。

```bash
# 1) 放回未入库的二进制（体积/许可原因，仓库不含）：
#    - ffmpeg.exe               随包解码器（npmmirror ffmpeg-static b6.0 单文件版）
#    - engine/ffmpeg.exe
#    - engine/redist/Valkyrie_setup_*.exe  官方驱动安装包
# 2) 构建（Windows，需 MSVC 环境）：
cmd /c "call <VS>\VC\Auxiliary\Build\vcvarsall.bat amd64 && set CARGO_HTTP_PROXY= && cd src-tauri && cargo tauri build"
# 产物: src-tauri/target/release/bundle/nsis/EDEN-VK99II_<ver>_x64-setup.exe
```

开发直跑：`cargo tauri dev`（引擎由壳自动拉起；也可手动 `uv run --python 3.12 --with opencv-python --with pillow --with numpy --with websocket-client python -u vk99_server.py`）。

## 目录

```
vk99_server.py    引擎 sidecar（HTTP API、预览转码、状态机）
vk99_writer.py    官方 UI 自动化写入器（CDP）
vk99_prep.py      探帧 / 裁切计算
vk99_drive.py     旧版 Tk 界面（已退役，保留参考）
eden-tauri/       Tauri 壳 + 前端 (ui/) + 引擎资源 (src-tauri/engine/)
tools/            辅助脚本
```

## 注意

- 官方 GIF 槽为 61 帧 × 255ms；写入期间请勿移动、关闭 Valkyrie Driver 窗口。
- 软件内置全局急停热键 **F12**（中止当前写入，不销毁窗口）。
- 预览缓存在 `%LOCALAPPDATA%\EDEN\prev_cache\`，可随时删除。

## 许可

MIT License（见 `LICENSE`）。本软件为第三方独立工具，与相关厂商无隶属关系，仅调用公开的官方驱动界面；GIF 播放效果受官方固件槽位限制。本软件按「现状」提供，不承担任何硬件损坏或数据丢失责任。
