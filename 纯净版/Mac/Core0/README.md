# Core0

`ncm-core` is XMaoMusic's own headless NCM decoder. It does not open another
window and reports machine-readable progress to the desktop application.

Windows build:

```powershell
powershell -ExecutionPolicy Bypass -File .\Core0\build_windows.ps1
```

Direct CLI usage:

```text
ncm-core --input song.ncm --output song.decoded --json-progress
```

The macOS executable is built automatically by `Mac/build_dmg.sh`. The desktop
application falls back to the same bundled Python implementation when a Core0
executable is not present.
