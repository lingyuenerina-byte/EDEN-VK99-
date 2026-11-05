# engine 资源目录

打包前需在此放置两个不进仓库的可执行文件（已被 .gitignore 忽略）：

1. `ffmpeg.exe` — 随包解码器（拆帧 + 预览转码用）。
   获取：https://github.com/BtbN/FFmpeg-Builds 或 https://www.gyan.dev/ffmpeg/builds/
   （GPL 构建，随包分发请在发布页注明 ffmpeg 版本与来源）
2. `redist/Valkyrie_setup_*.exe` — 官方键盘驱动安装程序，见 redist/README.md。

`find_ffmpeg()` 优先使用本目录的 `ffmpeg.exe`，找不到才回退系统 PATH/scoop/WinGet；
两者都没有时拆帧走逐帧扫描、预览只显示首帧海报，写入功能不受影响。
