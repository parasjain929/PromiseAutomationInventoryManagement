#!/usr/bin/env bash
set -euo pipefail

APP_NAME="Promise Automation Inventory Manager"
DIST_DIR="dist"
BUILD_DIR="build"

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

rm -rf "$DIST_DIR" "$BUILD_DIR"
pyinstaller \
  --noconfirm --clean --windowed --onedir \
  --name "$APP_NAME" \
  --osx-bundle-identifier "com.promiseautomation.inventorymanager" \
  --collect-all PySide6 \
  main.py

echo "macOS app created at: $DIST_DIR/$APP_NAME.app"
echo "For distribution outside your own Mac, code signing and notarization are recommended."
