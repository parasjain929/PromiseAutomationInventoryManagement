import sqlite3
from contextlib import contextmanager
from .config import DB_PATH

# Enabled by main.py after schema initialization. Tests and migration setup can use the DB before login.
ENFORCE_SESSION = False
SESSION_AUTHENTICATED = False

def set_session_authenticated(value):
    global SESSION_AUTHENTICATED
    SESSION_AUTHENTICATED = bool(value)


SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_info(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY, item_code TEXT UNIQUE, name TEXT NOT NULL,
 category TEXT DEFAULT '', unit TEXT NOT NULL DEFAULT 'pieces', location TEXT DEFAULT '',
 min_stock REAL NOT NULL DEFAULT 0, opening_qty REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
 notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name COLLATE NOCASE);
CREATE TABLE IF NOT EXISTS projects(id INTEGER PRIMARY KEY, project_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
 customer TEXT DEFAULT '', location TEXT DEFAULT '', manager TEXT DEFAULT '', status TEXT DEFAULT 'Planned',
 start_date TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS allocations(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL REFERENCES projects(id),
 item_id INTEGER NOT NULL REFERENCES items(id), quantity REAL NOT NULL CHECK(quantity>0), notes TEXT DEFAULT '',
 operator TEXT DEFAULT '', allocated_at TEXT DEFAULT CURRENT_TIMESTAMP, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, occurred_at TEXT DEFAULT CURRENT_TIMESTAMP,
 item_id INTEGER NOT NULL REFERENCES items(id), movement_type TEXT NOT NULL, quantity REAL NOT NULL,
 project_id INTEGER REFERENCES projects(id),
 allocation_id INTEGER REFERENCES allocations(id), source TEXT DEFAULT '', destination TEXT DEFAULT '',
 reason TEXT NOT NULL DEFAULT '', operator TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS installations(id INTEGER PRIMARY KEY, allocation_id INTEGER NOT NULL REFERENCES allocations(id),
 item_id INTEGER NOT NULL REFERENCES items(id), project_id INTEGER NOT NULL REFERENCES projects(id),
 item_name_snapshot TEXT NOT NULL, quantity REAL NOT NULL,
 installed_at TEXT DEFAULT CURRENT_TIMESTAMP, notes TEXT DEFAULT '', movement_id INTEGER REFERENCES movements(id));
CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY, allocation_id INTEGER NOT NULL REFERENCES allocations(id),
 item_id INTEGER NOT NULL REFERENCES items(id), project_id INTEGER NOT NULL REFERENCES projects(id),
 quantity REAL NOT NULL, condition TEXT NOT NULL, returned_at TEXT DEFAULT CURRENT_TIMESTAMP,
 notes TEXT DEFAULT '', movement_id INTEGER REFERENCES movements(id));
CREATE TABLE IF NOT EXISTS backup_history(id INTEGER PRIMARY KEY, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
 destination TEXT NOT NULL, status TEXT NOT NULL, details TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS auth_users(id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE, salt TEXT NOT NULL, password_hash TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
"""
def connect():
    if ENFORCE_SESSION and not SESSION_AUTHENTICATED:
        raise PermissionError("Please sign in before accessing inventory data.")
    c=sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    return c
@contextmanager
def transaction():
    c=connect()
    try:
        c.execute("BEGIN IMMEDIATE")
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
def initialize_database():
    with connect() as c:
        c.executescript(SCHEMA)
        allocation_cols = {r[1] for r in c.execute("PRAGMA table_info(allocations)")}
        if "allocated_at" not in allocation_cols:
            c.execute("ALTER TABLE allocations ADD COLUMN allocated_at TEXT")
            c.execute("UPDATE allocations SET allocated_at=COALESCE(created_at, CURRENT_TIMESTAMP)")
        if not c.execute("SELECT 1 FROM schema_info LIMIT 1").fetchone():
            c.execute("INSERT INTO schema_info VALUES(2)")
        c.commit()
    # Migrate older databases without losing project, allocation, movement, or installation history.
    # Machine links are intentionally discarded because machine-level tracking is no longer supported.
    raw = sqlite3.connect(DB_PATH, timeout=15)
    try:
        raw.execute("PRAGMA foreign_keys=OFF")
        tables = {r[0] for r in raw.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "movements" in tables:
            cols = {r[1] for r in raw.execute("PRAGMA table_info(movements)")}
            if "machine_id" in cols:
                raw.execute("CREATE TABLE movements_new(id INTEGER PRIMARY KEY, occurred_at TEXT DEFAULT CURRENT_TIMESTAMP, item_id INTEGER NOT NULL REFERENCES items(id), movement_type TEXT NOT NULL, quantity REAL NOT NULL, project_id INTEGER REFERENCES projects(id), allocation_id INTEGER REFERENCES allocations(id), source TEXT DEFAULT '', destination TEXT DEFAULT '', reason TEXT NOT NULL DEFAULT '', operator TEXT DEFAULT '')")
                raw.execute("INSERT INTO movements_new(id,occurred_at,item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason,operator) SELECT id,occurred_at,item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason,operator FROM movements")
                raw.execute("DROP TABLE movements")
                raw.execute("ALTER TABLE movements_new RENAME TO movements")
        if "installations" in tables:
            cols = {r[1] for r in raw.execute("PRAGMA table_info(installations)")}
            if "machine_id" in cols:
                raw.execute("CREATE TABLE installations_new(id INTEGER PRIMARY KEY, allocation_id INTEGER NOT NULL REFERENCES allocations(id), item_id INTEGER NOT NULL REFERENCES items(id), project_id INTEGER NOT NULL REFERENCES projects(id), item_name_snapshot TEXT NOT NULL, quantity REAL NOT NULL, installed_at TEXT DEFAULT CURRENT_TIMESTAMP, notes TEXT DEFAULT '', movement_id INTEGER REFERENCES movements(id))")
                raw.execute("INSERT INTO installations_new(id,allocation_id,item_id,project_id,item_name_snapshot,quantity,installed_at,notes,movement_id) SELECT id,allocation_id,item_id,project_id,item_name_snapshot,quantity,installed_at,notes,movement_id FROM installations")
                raw.execute("DROP TABLE installations")
                raw.execute("ALTER TABLE installations_new RENAME TO installations")
        raw.execute("DROP TABLE IF EXISTS machines")
        raw.commit()
    finally:
        raw.close()
def code(c, table, prefix):
    n=c.execute(f"SELECT COALESCE(MAX(id),0)+1 n FROM {table}").fetchone()["n"]
    return f"{prefix}-{n:05d}"
def stock(item_id, c=None):
    own=c is None
    c=c or connect()
    try:
        item=c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not item: raise ValueError("Item not found")
        ins=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM installations WHERE item_id=?", (item_id,)).fetchone()["n"]
        alloc=c.execute("""SELECT COALESCE(SUM(a.quantity),0)
          -COALESCE((SELECT SUM(i.quantity) FROM installations i JOIN allocations x ON x.id=i.allocation_id WHERE x.item_id=?),0)
          -COALESCE((SELECT SUM(r.quantity) FROM returns r JOIN allocations x ON x.id=r.allocation_id WHERE x.item_id=?),0) n
          FROM allocations a WHERE a.item_id=?""",(item_id,item_id,item_id)).fetchone()["n"]
        good=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE item_id=? AND condition='Good / reusable'",(item_id,)).fetchone()["n"]
        received=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM movements WHERE item_id=? AND movement_type IN ('Stock Received','Opening Stock')",(item_id,)).fetchone()["n"]
        damaged=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE item_id=? AND condition='Damaged'",(item_id,)).fetchone()["n"]
        quarantine=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE item_id=? AND condition IN ('Requires inspection','Other')",(item_id,)).fetchone()["n"]
        # Stock adjustment ledger entries use signed delta stored in reason as 'delta=+N' / 'delta=-N'.
        adjustment=0
        for m in c.execute("SELECT reason FROM movements WHERE item_id=? AND movement_type='Stock Adjustment'",(item_id,)):
            try: adjustment += float(m["reason"].split("delta=")[1].split()[0])
            except Exception: pass
        physical=float(item["opening_qty"])+float(received)-float(item["opening_qty"])-float(ins)+float(good)+adjustment
        # Opening quantity is represented in opening_qty and ledger, so subtract its ledger duplicate above.
        allocated=max(0,float(alloc or 0))
        return {"physical":round(physical,4),"allocated":round(allocated,4),"available":round(physical-allocated,4),
                "installed":round(float(ins),4),"damaged":round(float(damaged),4),"quarantined":round(float(quarantine),4)}
    finally:
        if own: c.close()
