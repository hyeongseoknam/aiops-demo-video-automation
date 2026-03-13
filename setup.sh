#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

OS="$(uname -s)"

echo "=== AIOps Demo Video Agent Setup ==="
echo "Detected OS: $OS"

# Check prerequisites
echo ""
echo "[0/4] Checking prerequisites..."

# Python
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    echo "  OK  $PY_VER"
else
    echo "  FAIL  python3 not found"
    if [ "$OS" = "Darwin" ]; then
        echo "  Install: brew install python@3.12"
    else
        echo "  Install: sudo apt install python3 python3-venv"
    fi
    exit 1
fi

# ffmpeg
if command -v ffmpeg &>/dev/null; then
    echo "  OK  ffmpeg available"
else
    echo "  FAIL  ffmpeg not found"
    if [ "$OS" = "Darwin" ]; then
        echo "  Install: brew install ffmpeg"
    else
        echo "  Install: sudo apt install ffmpeg"
    fi
    exit 1
fi

# Fonts (warning only)
if [ "$OS" = "Darwin" ]; then
    if [ -f "/System/Library/Fonts/AppleSDGothicNeo.ttc" ]; then
        echo "  OK  CJK fonts (AppleSDGothicNeo)"
    else
        echo "  WARN  No CJK font found. For best results:"
        echo "        brew install --cask font-noto-sans-cjk"
    fi
else
    if [ -f "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" ]; then
        echo "  OK  CJK fonts (NotoSansCJK)"
    else
        echo "  WARN  NotoSansCJK not found."
        echo "        sudo apt install fonts-noto-cjk"
    fi
fi

# Create venv
echo ""
if [ ! -d ".venv" ]; then
    echo "[1/3] Creating Python virtual environment..."
    python3 -m venv .venv
else
    echo "[1/3] Virtual environment already exists."
fi

# Install deps
echo "[2/3] Installing Python dependencies..."
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Install Playwright Chromium
echo "[3/3] Installing Playwright Chromium browser..."
playwright install chromium

echo ""
echo "=== Setup complete ==="
echo "Activate with: source .venv/bin/activate"
echo "Run with:      python run.py"
if [ "$OS" = "Darwin" ]; then
    echo ""
    echo "macOS note: Copy config/scenario_osx.yaml to config/scenario.yaml"
    echo "            and update paths for your environment."
fi
