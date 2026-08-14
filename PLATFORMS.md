# Windows 与 macOS 支持说明

XMaoMusic OffsetEditor 在 `Releases` 中提供 Windows 和 macOS 两套独立发布目录。两套版本使用相同的本地 HTML 界面、音频处理逻辑、格式转换能力、BPM 检测和 NCM 流式解密实现。

## Windows

- 支持 64 位 Windows 10 和 Windows 11。
- 双击 `Start.bat` 即可启动。
- 启动器会检查 Python、项目依赖和 FFmpeg；缺失时显示下载进度并优先使用国内镜像。
- `Core0/ncm-core.exe` 已包含在 Windows 发布版中，NCM 转换不会弹出第三方窗口。
- 输出文件保存在软件目录的 `Output` 文件夹。

## macOS

- 支持 Apple Silicon（arm64）与 Intel（x86_64）。
- 首次运行前在终端执行 `chmod +x Start.command bootstrap_macos.sh build_dmg.sh`，之后可运行 `./Start.command`。
- 启动器会检查 Python 与 FFmpeg；缺失时显示下载进度并优先使用清华、北外和南京大学镜像。
- 源码运行时可直接使用内置 NCM 实现；`build_dmg.sh` 会为当前 Mac 架构构建独立的 `Core0/ncm-core`。
- DMG 必须在对应架构的 Mac 上构建，Windows 无法生成有效的 macOS 应用包。
- 打包版输出文件保存在 `~/Music/XMaoMusic Output`。

## 发布版内容

运行根目录的 `build_clean_distribution.ps1` 会重新生成：

- `Releases/Windows`
- `Releases/Mac`

发布版不包含虚拟环境、依赖下载缓存、用户输出音频、运行日志、Python 缓存、浏览器测试数据或 PyInstaller 中间目录。首次启动时，各平台会在自己的软件目录中创建本地运行环境。
