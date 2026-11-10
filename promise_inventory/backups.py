import sqlite3
from datetime import datetime
from pathlib import Path
from .config import DB_PATH, BACKUP_DIR, CREDENTIALS_PATH, TOKEN_PATH
from .db import connect, transaction

def local_backup():
    path=BACKUP_DIR/f"PromiseAutomation_Inventory_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.db"
    src=connect(); dst=sqlite3.connect(path)
    try:
        src.backup(dst)
        if dst.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise RuntimeError("Backup integrity check failed")
    finally: dst.close(); src.close()
    with transaction() as c:c.execute("INSERT INTO backup_history(destination,status,details) VALUES(?,?,?)",(str(path),"Success","Verified local snapshot"))
    return path

def backups():
    return sorted(BACKUP_DIR.glob("*.db"),key=lambda p:p.stat().st_mtime,reverse=True)

def restore(path):
    path=Path(path)
    c=sqlite3.connect(path)
    try:
        if c.execute("PRAGMA integrity_check").fetchone()[0]!="ok": raise ValueError("Backup is corrupt")
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='items'").fetchone(): raise ValueError("Not an inventory database")
    finally:c.close()
    safety=local_backup()
    src=sqlite3.connect(path); dstpath=DB_PATH.with_suffix(".restore.db"); dst=sqlite3.connect(dstpath)
    try:src.backup(dst)
    finally:src.close();dst.close()
    import os; os.replace(dstpath,DB_PATH)
    return safety

def google_drive_backup():
    if not CREDENTIALS_PATH.exists(): raise FileNotFoundError(f"Place your Google OAuth Desktop credentials at {CREDENTIALS_PATH}")
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    scopes=["https://www.googleapis.com/auth/drive.file"]; creds=None
    if TOKEN_PATH.exists(): creds=Credentials.from_authorized_user_file(str(TOKEN_PATH),scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
        else: creds=InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH),scopes).run_local_server(port=0)
        TOKEN_PATH.write_text(creds.to_json(),encoding="utf-8")
    snap=local_backup(); service=build("drive","v3",credentials=creds)
    media=MediaFileUpload(str(snap),mimetype="application/vnd.sqlite3",resumable=True)
    result=service.files().create(body={"name":snap.name},media_body=media,fields="id,name,size").execute()
    with transaction() as c:c.execute("INSERT INTO backup_history(destination,status,details) VALUES(?,?,?)",(result["name"],"Success",f"Drive file ID {result['id']}"))
    return result
