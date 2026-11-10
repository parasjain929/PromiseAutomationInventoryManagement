# Native desktop builds

The application is Python/PySide6. PyInstaller must run on the target operating system; it does not cross-compile a Windows `.exe` from Linux/macOS or a macOS `.app` from Windows.

## Windows

On a Windows 10/11 x64 machine with Python 3.12 installed:

1. Extract the project folder.
2. Double-click `build_windows.bat`.
3. The executable is written to `dist/PromiseAutomationInventoryManager.exe`.

## macOS

On the Mac that will run the application:

```bash
chmod +x build_mac.sh
./build_mac.sh
```

The app bundle is written to `dist/Promise Automation Inventory Manager.app`.

On first launch, macOS may require right-click > Open because the app is not signed/notarized. For distribution to other Macs, sign with an Apple Developer ID and notarize the app.

## Build both through GitHub Actions

Push this folder to a GitHub repository, then open **Actions → Build desktop applications → Run workflow**. The workflow builds the Windows executable on a Windows runner and the macOS app on a macOS runner. Download the two artifacts from the completed workflow run.

## Data safety

The SQLite database and backup files are stored outside the packaged application under the user's application data directory. Replacing the executable or `.app` should not replace the database. Back up the database before upgrading. The current app is not code-signed and the SQLite database is not encrypted at rest.
