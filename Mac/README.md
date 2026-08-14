# macOS build

The macOS edition uses the native macOS title bar and traffic-light window
controls. The application itself supports both dark and light appearance.

## Run from source

In Terminal:

```bash
chmod +x Mac/Start.command Mac/bootstrap_macos.sh Mac/build_dmg.sh
./Mac/Start.command
```

The bootstrap checks Python and FFmpeg first. Missing components are downloaded
with visible progress, preferring Tsinghua, BFSU, and NJU mirrors before official
sources.

## Build a DMG

Run this command on a Mac:

```bash
./Mac/build_dmg.sh
```

Output:

- Apple Silicon: `Mac/XMaoMusic-OffsetEditor-macOS-arm64.dmg`
- Intel: `Mac/XMaoMusic-OffsetEditor-macOS-x86_64.dmg`

Build once on each native architecture to produce both packages. PyInstaller
cannot create a valid macOS application or DMG from Windows. The generated app
is unsigned; public distribution requires an Apple Developer ID and notarization.
