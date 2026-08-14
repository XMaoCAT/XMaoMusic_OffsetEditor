# macOS build

The macOS edition uses the native macOS title bar and traffic-light window
controls. The application itself supports both dark and light appearance. The
waveform includes a draggable red playback head and a preview command that
starts playback at the current trim point.

## Run from source repository

In Terminal:

```bash
chmod +x Mac/Start.command Mac/bootstrap_macos.sh Mac/build_dmg.sh
./Mac/Start.command
```

From the standalone `Releases/Mac` directory:

```bash
chmod +x Start.command bootstrap_macos.sh build_dmg.sh
./Start.command
```

The bootstrap checks Python and FFmpeg first. Missing components are downloaded
with visible progress, preferring Tsinghua, BFSU, and NJU mirrors before official
sources.

## Build a DMG

Run this command on a Mac:

```bash
# Source repository
./Mac/build_dmg.sh

# Standalone clean Mac directory
./build_dmg.sh
```

Output:

- Apple Silicon: `XMaoMusic-OffsetEditor-macOS-arm64.dmg`
- Intel: `XMaoMusic-OffsetEditor-macOS-x86_64.dmg`

The DMG is written beside `build_dmg.sh`.

Build once on each native architecture to produce both packages. PyInstaller
cannot create a valid macOS application or DMG from Windows. The generated app
is unsigned; public distribution requires an Apple Developer ID and notarization.

## Diagnostics

Python, Qt, audio-worker, and embedded web errors are written to:

```text
~/Library/Logs/XMaoMusic OffsetEditor/application.log
```

When reporting a macOS crash, include this file together with the `.ips` report.
