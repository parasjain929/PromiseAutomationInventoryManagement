@echo off
setlocal

py -3.12 -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

pyinstaller --noconfirm --clean --windowed --onefile --name "PromiseAutomationInventoryManager" --collect-all PySide6 main.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo Windows executable created at dist\PromiseAutomationInventoryManager.exe
echo Note: Test the executable on a clean Windows machine before rollout.
pause
