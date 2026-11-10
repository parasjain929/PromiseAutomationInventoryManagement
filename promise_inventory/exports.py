import csv
from datetime import datetime
from openpyxl import Workbook
from .db import connect, stock

def export_csv(path):
    with connect() as c:
        rows=c.execute("""SELECT m.id,m.occurred_at,i.item_code,i.name,m.movement_type,m.quantity,i.unit,
        p.project_code,m.source,m.destination,m.reason FROM movements m JOIN items i ON i.id=m.item_id
        LEFT JOIN projects p ON p.id=m.project_id ORDER BY m.id DESC""").fetchall()
    with open(path,"w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f);w.writerow(["Movement ID","Date/time","Item ID","Item","Type","Quantity","Unit","Project","Source","Destination","Reason","Generated"])
        for r in rows:w.writerow([*r,datetime.now().isoformat(timespec="seconds")])

def export_excel(path):
    with connect() as c:items=c.execute("SELECT * FROM items ORDER BY name").fetchall()
    wb=Workbook();ws=wb.active;ws.title="Inventory"
    ws.append(["Item ID","Name","Category","Unit","Location","Physical","Allocated","Available","Minimum stock","Active"])
    for i in items:
        s=stock(i["id"]);ws.append([i["item_code"],i["name"],i["category"],i["unit"],i["location"],s["physical"],s["allocated"],s["available"],i["min_stock"],bool(i["active"])])
    ws.freeze_panes="A2";ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:ws.column_dimensions[col[0].column_letter].width=min(35,max(12,max(len(str(x.value or "")) for x in col)+2))
    wb.save(path)
