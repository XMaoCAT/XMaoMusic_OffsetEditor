# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path.cwd()
core_binary = project_root / "Core0" / "ncm-core"

datas = [(str(project_root / "ui"), "ui")]
binaries = [(str(core_binary), "Core0")]
hiddenimports = []
hiddenimports += ["PySide6.QtMultimedia"]

for package in ("librosa", "sklearn", "numba", "llvmlite", "soundfile", "scipy", "imageio_ffmpeg", "Crypto"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

a = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="XMaoMusic OffsetEditor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="XMaoMusic OffsetEditor",
)
app = BUNDLE(
    coll,
    name="XMaoMusic OffsetEditor.app",
    icon=None,
    bundle_identifier="com.xmaocat.xmaomusic-offseteditor",
    info_plist={
        "CFBundleDisplayName": "XMaoMusic OffsetEditor",
        "CFBundleShortVersionString": "1.1.0",
        "CFBundleVersion": "1.1.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
