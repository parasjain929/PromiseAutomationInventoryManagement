import pytest
from promise_inventory import db, services

def test_core_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"test.db")
    db.initialize_database()
    item=services.create_item("Power supply",opening_qty=20)
    project=services.create_project("P-001","Machine build",status="Active")
    alloc=services.allocate(project,item,10)
    services.install(alloc,4)
    services.return_unused(alloc,3,"Good / reusable")
    r=services.reconciliation(project)[0]
    assert (r["allocated"],r["installed"],r["returned"],r["outstanding"])==(10,4,3,3)

def test_overallocation_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(db,"DB_PATH",tmp_path/"test.db")
    db.initialize_database()
    item=services.create_item("Sensor",opening_qty=2)
    project=services.create_project("P-002","Test",status="Active")
    with pytest.raises(ValueError):services.allocate(project,item,3)

def test_installation_is_project_level_only(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "project_only.db")
    db.initialize_database()
    item = services.create_item("Motor", opening_qty=5)
    project = services.create_project("P-003", "Assembly project", status="Active")
    allocation = services.allocate(project, item, 3)
    services.install(allocation, 2)
    with db.connect() as c:
        movement_columns = {r[1] for r in c.execute("PRAGMA table_info(movements)")}
        installation_columns = {r[1] for r in c.execute("PRAGMA table_info(installations)")}
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "machine_id" not in movement_columns
    assert "machine_id" not in installation_columns
    assert "machines" not in tables


def test_authentication_stores_hash_and_supports_password_change(tmp_path, monkeypatch):
    from promise_inventory import auth
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "auth.db")
    monkeypatch.setattr(auth, "DB_PATH", tmp_path / "auth.db")
    db.initialize_database()
    assert not auth.has_users()
    auth.create_admin("admin", "Correct-Horse-99")
    assert auth.authenticate("admin", "Correct-Horse-99")
    assert not auth.authenticate("admin", "wrong-password")
    with auth._connect() as c:
        row = c.execute("SELECT salt,password_hash FROM auth_users WHERE username='admin'").fetchone()
    assert row[0] != "Correct-Horse-99"
    assert row[1] != "Correct-Horse-99"
    auth.change_password("admin", "Correct-Horse-99", "New-Correct-Horse-99")
    assert not auth.authenticate("admin", "Correct-Horse-99")
    assert auth.authenticate("admin", "New-Correct-Horse-99")

def test_database_api_requires_authenticated_session_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "session.db")
    db.initialize_database()
    monkeypatch.setattr(db, "ENFORCE_SESSION", True)
    db.set_session_authenticated(False)
    with pytest.raises(PermissionError):
        db.connect()
    db.set_session_authenticated(True)
    with db.connect() as c:
        assert c.execute("SELECT 1").fetchone()[0] == 1
    db.set_session_authenticated(False)
    monkeypatch.setattr(db, "ENFORCE_SESSION", False)

def test_multi_item_allocation_and_project_editing(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "multi.db")
    db.initialize_database()
    motor = services.create_item("Motor", opening_qty=12)
    sensor = services.create_item("Sensor", opening_qty=20)
    project = services.create_project("P-004", "Multi item project", status="Active")
    ids = services.allocate_many(project, [(motor, 3), (sensor, 5)], notes="Initial allocation")
    assert len(ids) == 2
    rows = services.reconciliation(project)
    assert {r["name"]: r["allocated"] for r in rows} == {"Motor": 3, "Sensor": 5}
    services.update_allocation(ids[0], motor, 4, "Updated quantity")
    assert next(r for r in services.reconciliation(project) if r["name"] == "Motor")["allocated"] == 4
    services.delete_allocation(ids[1])
    assert len(services.reconciliation(project)) == 1


def test_allocation_cannot_be_removed_after_installation(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "history.db")
    db.initialize_database()
    item = services.create_item("Controller", opening_qty=10)
    project = services.create_project("P-005", "History project", status="Active")
    allocation = services.allocate(project, item, 5)
    services.install(allocation, 2)
    with pytest.raises(ValueError):
        services.delete_allocation(allocation)
    with pytest.raises(ValueError):
        services.update_allocation(allocation, item, 1)


def test_multi_allocation_persists_user_selected_allocation_date(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "allocation_date.db")
    db.initialize_database()
    item = services.create_item("Servo drive", opening_qty=10)
    project = services.create_project("P-006", "Date tracking project", status="Active")
    ids = services.allocate_many(project, [(item, 2)], allocated_at="2026-11-10")
    with db.connect() as c:
        row = c.execute("SELECT allocated_at FROM allocations WHERE id=?", (ids[0],)).fetchone()
    assert row["allocated_at"] == "2026-11-10"


def test_multi_allocation_rejects_fractional_quantity(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "integer_qty.db")
    db.initialize_database()
    item = services.create_item("Bearing", opening_qty=10)
    project = services.create_project("P-007", "Integer quantity project", status="Active")
    with pytest.raises(ValueError, match="whole numbers"):
        services.allocate_many(project, [(item, 1.5)])


def test_existing_database_migration_adds_allocation_date_without_losing_rows(tmp_path, monkeypatch):
    import sqlite3
    database = tmp_path / "legacy.db"
    monkeypatch.setattr(db, "DB_PATH", database)
    # Build the pre-date version of the allocation table and a row to preserve.
    raw = sqlite3.connect(database)
    raw.executescript("""
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info VALUES(2);
        CREATE TABLE items(id INTEGER PRIMARY KEY, item_code TEXT UNIQUE, name TEXT NOT NULL,
            category TEXT DEFAULT '', unit TEXT NOT NULL DEFAULT 'pieces', location TEXT DEFAULT '',
            min_stock REAL NOT NULL DEFAULT 0, opening_qty REAL NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1,
            notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE projects(id INTEGER PRIMARY KEY, project_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
            customer TEXT DEFAULT '', location TEXT DEFAULT '', manager TEXT DEFAULT '', status TEXT DEFAULT 'Planned',
            start_date TEXT DEFAULT '', notes TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE allocations(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, item_id INTEGER NOT NULL,
            quantity REAL NOT NULL, notes TEXT DEFAULT '', operator TEXT DEFAULT '', created_at TEXT DEFAULT '2026-11-01 10:00:00');
        INSERT INTO items(id,item_code,name) VALUES(1,'PA-ITEM-00001','Legacy item');
        INSERT INTO projects(id,project_code,name) VALUES(1,'P-OLD','Legacy project');
        INSERT INTO allocations(id,project_id,item_id,quantity) VALUES(1,1,1,4);
    """)
    raw.commit(); raw.close()
    db.initialize_database()
    with db.connect() as c:
        row = c.execute("SELECT quantity, allocated_at FROM allocations WHERE id=1").fetchone()
    assert row["quantity"] == 4
    assert row["allocated_at"] == "2026-11-01 10:00:00"
