# Promise Automation Inventory Manager

Local-first desktop inventory application for Promise Automation, built with Python, PySide6, and SQLite. The refreshed interface uses a navy navigation sidebar, consistent page headings, readable data-entry forms, clearer business terminology, and improved table layouts.

## Main screens
- Dashboard with active item types, active projects, low-stock alerts, outstanding allocated quantities, and recent inventory activity.
- Inventory with item search, stock receipt, physical count adjustment, and item editing.
- Projects and project stock reconciliation.
- Multi-item project allocation with a selectable allocation date, searchable item selection, and whole-number quantities.
- Project Details shows allocation dates and all allocated components for the selected project.
- Returns for unused components.
- Stock movement history.
- Excel and CSV exports.
- Local backup/restore and Google Drive backup setup.
- Settings, password changes, data-folder access, and database integrity check.
- First-run administrator setup, sign-in, and logout. Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes.
- Project-level component consumption only; machine registry and machine-specific tracking are removed.

Items are entered by name and internal ID. Barcode scanning, serial-number tracking, and machine-level component tracking are not included. Existing databases are migrated to remove machine-specific links while preserving project, allocation, movement, and installation records.

## Run on macOS
1. Install Python 3.12 from https://www.python.org/downloads/macos/ if a compatible Python version is not already installed.
2. Extract the ZIP archive.
3. Open Terminal and change to the extracted project folder, for example:
   ```bash
   cd ~/Downloads/PromiseAutomationInventoryManager
   ```
4. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
5. Install the dependencies and launch:
   ```bash
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   python main.py
   ```
6. To run the workflow tests:
   ```bash
   python -m pytest -q
   ```

If `python3` points to an unsupported version, install Python 3.12 and use the corresponding executable to create the environment. The virtual environment avoids modifying Homebrew-managed Python packages.

## Run on Windows
1. Install Python 3.12 from https://www.python.org/downloads/windows/ and enable the Python launcher during setup.
2. Extract the ZIP archive and open PowerShell in the project folder.
3. Run:
   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   python main.py
   ```
4. Run tests with `python -m pytest -q`.

## Build desktop applications (Windows and macOS)

See [`packaging/BUILDING.md`](packaging/BUILDING.md). Run `build_windows.bat` on Windows to create the `.exe`, or `./build_mac.sh` on macOS to create the `.app`. Native builds must run on their target operating system. A GitHub Actions workflow is included to build both platforms and publish downloadable workflow artifacts.


## Data location
The application stores its database and local application data separately from the source folder. On Windows, the data directory is under `%LOCALAPPDATA%\\PromiseAutomation\\InventoryManager\\`. On macOS, the application data directory is selected by `promise_inventory/config.py` and can be opened from Settings.

## Google Drive backup
Google Drive backup requires a Google Cloud project, the Drive API enabled, and an OAuth Desktop App client. Save the downloaded client JSON as `credentials.json` in the application data folder, then use **Backup & Restore → Back up to Google Drive**. Keep credentials and OAuth tokens private. Cloud backup is not active until this configuration and an actual upload have been tested.

## Validation status
Python syntax compilation and ten automated workflow, authentication, allocation-date, integer-quantity, and migration tests passed in the editing environment. PySide6 was not installed in that environment, so the desktop window could not be launched there for visual verification. The allocation dialog was structurally redesigned, but visual acceptance on macOS and Windows is still required. The login gate protects the app’s database API during normal application use, and passwords are hashed; however, the SQLite database file itself is not encrypted. Anyone with direct access to the computer and data folder may be able to access the file outside the app. Complete Mac/Windows UI acceptance and operational stock-ledger validation are still recommended before using this as the only live inventory record.
