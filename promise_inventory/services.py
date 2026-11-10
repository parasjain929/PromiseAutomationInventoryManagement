from datetime import datetime
from .db import transaction, connect, code, stock

def create_item(name, category="", unit="pieces", location="", min_stock=0, opening_qty=0, notes=""):
    name=name.strip()
    if not name: raise ValueError("Item name is required")
    if min_stock<0 or opening_qty<0: raise ValueError("Quantities cannot be negative")
    with transaction() as c:
        dup=c.execute("SELECT item_code FROM items WHERE name=? COLLATE NOCASE AND active=1",(name,)).fetchone()
        if dup: raise ValueError(f"Possible duplicate item: {dup['item_code']}")
        cur=c.execute("INSERT INTO items(item_code,name,category,unit,location,min_stock,opening_qty,notes) VALUES(?,?,?,?,?,?,?,?)",
            (code(c,"items","PA-ITEM"),name,category,unit,location,min_stock,opening_qty,notes))
        iid=cur.lastrowid
        if opening_qty:
            c.execute("INSERT INTO movements(item_id,movement_type,quantity,reason) VALUES(?,?,?,?)",(iid,"Opening Stock",opening_qty,"Opening quantity"))
        return iid

def create_project(project_code,name,customer="",location="",manager="",status="Planned",start_date="",notes=""):
    if not project_code.strip() or not name.strip(): raise ValueError("Project code and name are required")
    with transaction() as c:
        return c.execute("INSERT INTO projects(project_code,name,customer,location,manager,status,start_date,notes) VALUES(?,?,?,?,?,?,?,?)",
          (project_code,name,customer,location,manager,status,start_date,notes)).lastrowid

def receive(item_id,quantity,reason,operator=""):
    if quantity<=0 or not reason.strip(): raise ValueError("Enter positive quantity and reason")
    with transaction() as c:
        c.execute("INSERT INTO movements(item_id,movement_type,quantity,reason,operator,destination) VALUES(?,?,?,?,?,?)",
          (item_id,"Stock Received",quantity,reason,operator,"Warehouse"))
    return stock(item_id)

def adjust(item_id,new_qty,reason,operator=""):
    if new_qty<0 or not reason.strip(): raise ValueError("Enter a valid physical count and reason")
    with transaction() as c:
        old=stock(item_id,c)
        delta=new_qty-old["physical"]
        if new_qty<old["allocated"]: raise ValueError("Physical stock cannot be lower than allocated quantity")
        c.execute("INSERT INTO movements(item_id,movement_type,quantity,reason,operator) VALUES(?,?,?,?,?)",
          (item_id,"Stock Adjustment",abs(delta),f"{reason} delta={delta:+g}",operator))
    return stock(item_id)

def allocate(project_id,item_id,quantity,notes="",operator="",allocated_at=None):
    if quantity<=0: raise ValueError("Quantity must be positive")
    with transaction() as c:
        p=c.execute("SELECT status FROM projects WHERE id=?",(project_id,)).fetchone()
        if not p or p["status"] in ("Completed","Cancelled"): raise ValueError("Project is not active for allocations")
        s=stock(item_id,c)
        if quantity>s["available"]+1e-8: raise ValueError(f"Insufficient stock. Available: {s['available']:g}")
        a=c.execute("INSERT INTO allocations(project_id,item_id,quantity,notes,operator,allocated_at) VALUES(?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP))",(project_id,item_id,quantity,notes,operator,allocated_at)).lastrowid
        c.execute("INSERT INTO movements(item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason,operator) VALUES(?,?,?,?,?,?,?,?,?)",
          (item_id,"Project Allocation",quantity,project_id,a,"Warehouse","Project",notes or "Allocated to project",operator))
        return a

def install(allocation_id,quantity,installed_at="",notes=""):
    if quantity<=0: raise ValueError("Quantity must be positive")
    with transaction() as c:
        a=c.execute("SELECT a.*,i.name FROM allocations a JOIN items i ON i.id=a.item_id WHERE a.id=?",(allocation_id,)).fetchone()
        if not a: raise ValueError("Allocation not found")
        ins=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM installations WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        ret=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        outstanding=a["quantity"]-ins-ret
        if quantity>outstanding+1e-8: raise ValueError(f"Only {outstanding:g} remains outstanding")
        mid=c.execute("INSERT INTO movements(item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason) VALUES(?,?,?,?,?,?,?,?)",
          (a["item_id"],"Installation/consumption",quantity,a["project_id"],allocation_id,"Project","Consumed",notes or "Installed / consumed for project")).lastrowid
        c.execute("INSERT INTO installations(allocation_id,item_id,project_id,item_name_snapshot,quantity,installed_at,notes,movement_id) VALUES(?,?,?,?,?,?,?,?)",
          (allocation_id,a["item_id"],a["project_id"],a["name"],quantity,installed_at or datetime.now().isoformat(timespec="seconds"),notes,mid))
    return stock(a["item_id"])

def return_unused(allocation_id,quantity,condition="Good / reusable",notes=""):
    if quantity<=0: raise ValueError("Quantity must be positive")
    with transaction() as c:
        a=c.execute("SELECT * FROM allocations WHERE id=?",(allocation_id,)).fetchone()
        if not a: raise ValueError("Allocation not found")
        ins=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM installations WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        ret=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        outstanding=a["quantity"]-ins-ret
        if quantity>outstanding+1e-8: raise ValueError(f"Only {outstanding:g} remains outstanding")
        rid=c.execute("INSERT INTO returns(allocation_id,item_id,project_id,quantity,condition,notes) VALUES(?,?,?,?,?,?)",
          (allocation_id,a["item_id"],a["project_id"],quantity,condition,notes)).lastrowid
        c.execute("INSERT INTO movements(item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason) VALUES(?,?,?,?,?,?,?,?)",
          (a["item_id"],"Unused Return",quantity,a["project_id"],allocation_id,"Project","Warehouse" if condition=="Good / reusable" else condition,notes or condition))
    return rid

def reconciliation(project_id):
    with connect() as c:
        rows=c.execute("""SELECT a.id allocation_id,i.item_code,i.name,i.unit,a.quantity allocated,
        COALESCE((SELECT SUM(quantity) FROM installations WHERE allocation_id=a.id),0) installed,
        COALESCE((SELECT SUM(quantity) FROM returns WHERE allocation_id=a.id),0) returned
        FROM allocations a JOIN items i ON i.id=a.item_id WHERE a.project_id=?""",(project_id,)).fetchall()
        return [dict(r,outstanding=round(r["allocated"]-r["installed"]-r["returned"],4)) for r in rows]


def allocate_many(project_id, entries, notes="", operator="", allocated_at=None):
    """Atomically allocate several distinct items to one project."""
    cleaned=[]
    for item_id, quantity in entries:
        if isinstance(quantity, bool) or int(quantity) != quantity or int(quantity) <= 0:
            raise ValueError("Allocation quantities must be positive whole numbers.")
        cleaned.append((int(item_id), int(quantity)))
    if not cleaned:
        raise ValueError("Add at least one item to the allocation.")
    if len({x[0] for x in cleaned}) != len(cleaned):
        raise ValueError("Each item should appear only once. Combine its quantity into one row.")
    with transaction() as c:
        p=c.execute("SELECT status FROM projects WHERE id=?",(project_id,)).fetchone()
        if not p or p["status"] in ("Completed","Cancelled"):
            raise ValueError("Project is not active for allocations")
        created=[]
        for item_id, quantity in cleaned:
            s=stock(item_id,c)
            if quantity > s["available"]:
                item=c.execute("SELECT name FROM items WHERE id=?",(item_id,)).fetchone()
                raise ValueError(f"Insufficient stock for {item['name']}. Available: {s['available']:g}")
            aid=c.execute("INSERT INTO allocations(project_id,item_id,quantity,notes,operator,allocated_at) VALUES(?,?,?,?,?,COALESCE(?,CURRENT_TIMESTAMP))",(project_id,item_id,quantity,notes,operator,allocated_at)).lastrowid
            c.execute("INSERT INTO movements(item_id,movement_type,quantity,project_id,allocation_id,source,destination,reason,operator) VALUES(?,?,?,?,?,?,?,?,?)",(item_id,"Project Allocation",quantity,project_id,aid,"Warehouse","Project",notes or "Allocated to project",operator))
            created.append(aid)
        return created


def update_allocation(allocation_id, item_id, quantity, notes=""):
    if isinstance(quantity, bool) or int(quantity) != quantity or int(quantity) <= 0:
        raise ValueError("Quantity must be a positive whole number.")
    quantity=int(quantity)
    with transaction() as c:
        a=c.execute("SELECT * FROM allocations WHERE id=?",(allocation_id,)).fetchone()
        if not a: raise ValueError("Allocation not found")
        p=c.execute("SELECT status FROM projects WHERE id=?",(a["project_id"],)).fetchone()
        if not p or p["status"] in ("Completed","Cancelled"): raise ValueError("Completed or cancelled projects cannot be edited.")
        ins=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM installations WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        ret=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns WHERE allocation_id=?",(allocation_id,)).fetchone()["n"]
        if int(item_id) != a["item_id"] and (ins or ret):
            raise ValueError("The item cannot be changed after installation or return activity has been recorded.")
        if quantity < ins+ret: raise ValueError(f"Quantity cannot be less than the {int(ins+ret)} already installed or returned.")
        delta=quantity-a["quantity"] if int(item_id)==a["item_id"] else quantity
        if delta>0:
            s=stock(int(item_id),c)
            if delta>s["available"]: raise ValueError(f"Insufficient stock. Available to add: {s['available']:g}")
        c.execute("UPDATE allocations SET item_id=?,quantity=?,notes=? WHERE id=?",(int(item_id),quantity,notes,allocation_id))
        movement=c.execute("SELECT id FROM movements WHERE allocation_id=? AND movement_type='Project Allocation' ORDER BY id LIMIT 1",(allocation_id,)).fetchone()
        if movement:
            c.execute("UPDATE movements SET item_id=?,quantity=?,reason=? WHERE id=?",(int(item_id),quantity,notes or "Allocated to project",movement["id"]))


def delete_allocation(allocation_id):
    with transaction() as c:
        a=c.execute("SELECT * FROM allocations WHERE id=?",(allocation_id,)).fetchone()
        if not a: raise ValueError("Allocation not found")
        p=c.execute("SELECT status FROM projects WHERE id=?",(a["project_id"],)).fetchone()
        if not p or p["status"] in ("Completed","Cancelled"): raise ValueError("Completed or cancelled projects cannot be edited.")
        downstream=c.execute("SELECT (SELECT COUNT(*) FROM installations WHERE allocation_id=?)+(SELECT COUNT(*) FROM returns WHERE allocation_id=?) n",(allocation_id,allocation_id)).fetchone()["n"]
        if downstream: raise ValueError("This allocation has installation or return history. It cannot be removed; edit its remaining quantity instead.")
        c.execute("DELETE FROM movements WHERE allocation_id=? AND movement_type='Project Allocation'",(allocation_id,))
        c.execute("DELETE FROM allocations WHERE id=?",(allocation_id,))
