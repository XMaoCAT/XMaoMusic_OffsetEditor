#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/app.py" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "DMG packages can only be built on macOS."
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  arm64|x86_64) ;;
  *) echo "Unsupported Mac architecture: $ARCH"; exit 1 ;;
esac

"$SCRIPT_DIR/bootstrap_macos.sh"
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

echo "Checking build dependencies..."
if ! "$PYTHON_BIN" -m pip install --progress-bar on \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller==6.16.0; then
  echo "Tsinghua mirror unavailable; trying official PyPI..."
  "$PYTHON_BIN" -m pip install --progress-bar on pyinstaller==6.16.0
fi

BUILD_ROOT="$SCRIPT_DIR/build/$ARCH"
CORE_DIST="$BUILD_ROOT/core-dist"
APP_DIST="$SCRIPT_DIR/dist-$ARCH"
STAGING_ROOT="$BUILD_ROOT/dmg-root"
DMG_PATH="$SCRIPT_DIR/XMaoMusic-OffsetEditor-macOS-$ARCH.dmg"

mkdir -p "$BUILD_ROOT" "$CORE_DIST" "$APP_DIST"

echo "Building Core0 for $ARCH..."
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --onefile --console \
  --name ncm-core \
  --paths "$PROJECT_ROOT" \
  --distpath "$CORE_DIST" \
  --workpath "$BUILD_ROOT/core-work" \
  --specpath "$BUILD_ROOT" \
  "$PROJECT_ROOT/Core0/ncm_cli.py"
cp -f "$CORE_DIST/ncm-core" "$PROJECT_ROOT/Core0/ncm-core"
chmod +x "$PROJECT_ROOT/Core0/ncm-core"

echo "Building XMaoMusic OffsetEditor.app..."
cd "$PROJECT_ROOT"
"$PYTHON_BIN" -m PyInstaller --noconfirm --clean \
  --distpath "$APP_DIST" \
  --workpath "$BUILD_ROOT/app-work" \
  "$SCRIPT_DIR/XMaoMusic-macos.spec"

APP_PATH="$APP_DIST/XMaoMusic OffsetEditor.app"
if [[ ! -d "$APP_PATH" ]]; then
  echo "Application bundle was not created."
  exit 1
fi

rm -rf "$STAGING_ROOT"
mkdir -p "$STAGING_ROOT"
cp -R "$APP_PATH" "$STAGING_ROOT/"
ln -s /Applications "$STAGING_ROOT/Applications"
rm -f "$DMG_PATH"

echo "Creating DMG..."
hdiutil create \
  -volname "XMaoMusic OffsetEditor" \
  -srcfolder "$STAGING_ROOT" \
  -ov -format UDZO \
  "$DMG_PATH"

echo "DMG ready: $DMG_PATH"
echo "This build is unsigned. Distribution outside your own Macs requires Apple signing and notarization."
