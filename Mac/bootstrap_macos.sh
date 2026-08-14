#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/app.py" ]]; then
  PROJECT_ROOT="$SCRIPT_DIR"
else
  PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi
RUNTIME_ROOT="$PROJECT_ROOT/.runtime/macos"
MINIFORGE_ROOT="$RUNTIME_ROOT/miniforge"
VENV_ROOT="$SCRIPT_DIR/.venv"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This bootstrap must run on macOS."
  exit 1
fi

ARCH="$(uname -m)"
case "$ARCH" in
  arm64)
    INSTALLER_NAME="Miniforge3-MacOSX-arm64.sh"
    INSTALLER_SHA256="59168f1e24d0a4ad9932021170809fca836cd240e183eeeb331d5bcfc0098168"
    ;;
  x86_64)
    INSTALLER_NAME="Miniforge3-MacOSX-x86_64.sh"
    INSTALLER_SHA256="39273e4c89a0a1af4538010615d44ae8f44e1af41007e02def593d20f316b003"
    ;;
  *)
    echo "Unsupported Mac architecture: $ARCH"
    exit 1
    ;;
esac

mkdir -p "$RUNTIME_ROOT"

PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(not ((3, 10) <= sys.version_info[:2] < (3, 14)))'; then
  PYTHON_BIN="$(command -v python3)"
elif [[ -x "$MINIFORGE_ROOT/bin/python" ]]; then
  PYTHON_BIN="$MINIFORGE_ROOT/bin/python"
else
  INSTALLER_PATH="$RUNTIME_ROOT/$INSTALLER_NAME"
  URLS=(
    "https://mirrors.bfsu.edu.cn/github-release/conda-forge/miniforge/LatestRelease/$INSTALLER_NAME"
    "https://mirror.nju.edu.cn/github-release/conda-forge/miniforge/LatestRelease/$INSTALLER_NAME"
    "https://github.com/conda-forge/miniforge/releases/download/26.3.2-3/$INSTALLER_NAME"
  )
  echo "Compatible Python was not found. Downloading Miniforge ($ARCH)..."
  DOWNLOAD_OK=0
  for URL in "${URLS[@]}"; do
    echo "Source: $URL"
    if curl --fail --location --progress-bar "$URL" --output "$INSTALLER_PATH"; then
      ACTUAL_SHA256="$(shasum -a 256 "$INSTALLER_PATH" | awk '{print $1}')"
      if [[ "$ACTUAL_SHA256" == "$INSTALLER_SHA256" ]]; then
        DOWNLOAD_OK=1
        break
      fi
      echo "Checksum mismatch; trying the next source."
    else
      echo "Download failed; trying the next source."
    fi
  done
  if [[ "$DOWNLOAD_OK" != "1" ]]; then
    echo "Unable to download a verified Miniforge installer."
    exit 1
  fi
  echo "Installing project-local Miniforge..."
  bash "$INSTALLER_PATH" -b -p "$MINIFORGE_ROOT"
  PYTHON_BIN="$MINIFORGE_ROOT/bin/python"
fi

if [[ ! -x "$VENV_ROOT/bin/python" ]]; then
  echo "Creating the project-local Python environment..."
  "$PYTHON_BIN" -m venv "$VENV_ROOT"
fi

echo "Checking Python dependencies (download progress will be shown when needed)..."
if ! "$VENV_ROOT/bin/python" -m pip install --progress-bar on \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
  -r "$PROJECT_ROOT/requirements.txt"; then
  echo "Tsinghua mirror unavailable; trying official PyPI..."
  "$VENV_ROOT/bin/python" -m pip install --progress-bar on -r "$PROJECT_ROOT/requirements.txt"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  echo "FFmpeg found: $(command -v ffmpeg)"
else
  echo "System FFmpeg was not found. Verifying the project-local FFmpeg..."
  FFMPEG_BIN="$("$VENV_ROOT/bin/python" -c 'from imageio_ffmpeg import get_ffmpeg_exe; print(get_ffmpeg_exe())')"
  if [[ ! -x "$FFMPEG_BIN" ]]; then
    echo "Project-local FFmpeg setup failed."
    exit 1
  fi
  echo "Project-local FFmpeg ready: $FFMPEG_BIN"
fi

echo "macOS environment is ready ($ARCH)."
