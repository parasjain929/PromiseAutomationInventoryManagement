from pathlib import Path
import os
APP_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()/".local"/"share")/"PromiseAutomation"/"InventoryManager"
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR/"promise_inventory.db"
BACKUP_DIR = APP_DIR/"backups"
BACKUP_DIR.mkdir(exist_ok=True)
CREDENTIALS_PATH = APP_DIR/"credentials.json"
TOKEN_PATH = APP_DIR/"token.json"
