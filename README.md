# XMaoMusic OffsetEditor

用于修正音频开头偏移、转换音频格式和分析 BPM 的 Windows / macOS 桌面工具，适合 maimai 谱面制作等需要精确校时的场景。源文件始终保持不变；源码版结果保存在项目内 `Output`，打包后的 macOS 版保存在用户的 `Music/XMaoMusic Output`。

## 主要能力

- 删除音频开头，或在开头添加静音
- 偏移时间可直接键入，回车或失焦后确认；支持 `1 ms` 精度和 `10 ms` 按钮步进
- 显示真实双声道波形、源时长和预计输出时长
- 调整采样率、声道、位深、格式与有损编码比特率
- 根据目标格式自动限制无效参数
- 编辑接点短淡入，减少切点爆音
- 可选峰值标准化到 `-1 dBFS`
- 显示输出大小估算和真实编码进度
- 支持拖放导入、文件名清理和同名自动编号，不覆盖已有文件
- 在独立“格式转换”工作区中转换 MP3、WAV、FLAC、OGG、M4A、AAC、WMA、AIFF 与 Opus
- 导入后在后台自动分析 BPM，并显示检测节拍数与实际分析范围
- 拖入或选择 NCM 后在应用内确认，静默转换为 WAV、自动载入并继续分析 BPM
- 毛玻璃软件界面与动态流体背景，支持持久化明暗主题、手动关闭动效并遵循系统“减少动态效果”设置
- Windows 使用可拖动的自绘标题栏；macOS 使用原生标题栏与交通灯窗口控件

## 支持格式

导入和导出支持：

- MP3
- WAV
- FLAC
- OGG Vorbis
- M4A / AAC
- WMA
- AIFF
- Opus

此外支持导入网易云 NCM 容器。程序优先调用 `Core0/ncm-core.exe`（macOS 为 `Core0/ncm-core`）完成无界面流式解密，再由 FFmpeg 转为标准 WAV；核心缺失时自动使用同源内置实现。整个过程不会打开独立转换程序，也不会修改原始 NCM 文件。

## 打开即用

直接双击根目录中的 `Start.bat`。

启动器会依次完成：

1. 检查兼容的 64 位 Python 3.9 至 3.13。
2. 缺少 Python 时，优先从阿里云、华为云等国内镜像下载项目专用 Python，并显示百分比、大小和实时速度。
3. 在项目内创建 `.venv`，优先使用清华和阿里云 PyPI 镜像安装依赖，失败后才回退官方源；pip 会显示下载进度。
4. 对系统 `ffmpeg.exe` 执行健康检查。系统 FFmpeg 不存在或不可用时，自动使用随 `imageio-ffmpeg` 依赖下载的项目内 FFmpeg。
5. 打印最终使用的 FFmpeg 路径并启动应用。后续启动会直接复用已准备好的环境。

首次准备环境需要联网。`.venv` 和 `.runtime` 都是项目本地目录，删除后再次运行 `Start.bat` 即可自动重建。

## Windows 与 Mac 纯净版

仓库中的 `纯净版` 目录提供两个互不混用的平台版本：

- `纯净版/Windows`：包含 `Start.bat`、Windows 环境检测脚本和已构建的 `Core0/ncm-core.exe`。
- `纯净版/Mac`：包含 `Start.command`、macOS 环境检测脚本，以及 Apple Silicon / Intel 的 DMG 构建脚本。

两份目录均不包含运行记录、虚拟环境、下载缓存、用户输出、日志、测试截图或构建中间文件。需要重新生成时，在 Windows PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\build_clean_distribution.ps1
```

完整平台要求和启动方式见 [PLATFORMS.md](PLATFORMS.md)。

## 界面架构

应用仍是本地桌面软件，不依赖在线网页：

- `app.py`：应用入口
- `desktop_app.py`：PySide6 桌面窗口、文件对话框、拖放和 WebChannel 桥接
- `audio_core.py`：音频分析、BPM 检测、偏移处理和 FFmpeg 编码
- `ncm_core.py`：NCM 容器解析与流式解密
- `Core0/`：可独立封装的无界面 NCM 核心、Windows 构建脚本与已构建 EXE
- `ui/index.html`、`ui/styles.css`、`ui/app.js`、`ui/fluid.js`：嵌入式本地界面
- `bootstrap.ps1`：环境、依赖与 FFmpeg 自检
- `Mac/`：macOS 首次启动、依赖自检、`.app` 与 DMG 构建脚本

## macOS

源码仓库中的 macOS 入口为 `Mac/Start.command`；`纯净版/Mac` 独立目录中的入口为根部 `Start.command`。首次运行会检查 Python 与 FFmpeg；缺失时显示下载进度，并优先使用清华、北外和南京大学镜像。详细说明见 `Mac/README.md`，纯净版内对应 `README-macOS.md`。

DMG 必须在 macOS 上构建：

```bash
# 源码仓库布局
chmod +x Mac/Start.command Mac/bootstrap_macos.sh Mac/build_dmg.sh
./Mac/build_dmg.sh

# 纯净版/Mac 独立目录布局
chmod +x Start.command bootstrap_macos.sh build_dmg.sh
./build_dmg.sh
```

Apple Silicon 输出 `XMaoMusic-OffsetEditor-macOS-arm64.dmg`，Intel 输出 `XMaoMusic-OffsetEditor-macOS-x86_64.dmg`，文件位于构建脚本所在目录。两种架构需分别在对应架构的 Mac 上构建。Windows 无法生成有效的 macOS `.app` 或 DMG；未签名构建仅适合本机测试，公开分发还需要 Apple Developer ID 签名和公证。

## 手动启动

环境已安装时可以运行：

```powershell
.\.venv\Scripts\python.exe app.py
```

也可以运行 `install_deps.ps1` 把依赖安装到兼容的 `_deps` 目录，再使用系统 Python 启动。

## 第三方说明

NCM 容器格式实现参考了 Apache-2.0 许可的 [yoki123/ncmdump](https://github.com/yoki123/ncmdump)，本项目未捆绑或调用用户提供的第三方 NCM 转换 EXE。详细归属见 `THIRD_PARTY_NOTICES.md`。
