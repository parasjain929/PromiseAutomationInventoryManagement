import os,sys,subprocess
from PySide6.QtWidgets import *
from PySide6.QtWidgets import QCompleter
from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QColor, QStandardItemModel, QFont
from . import services
from .db import connect, stock, set_session_authenticated
from .config import APP_DIR,DB_PATH
from .backups import local_backup,backups,restore,google_drive_backup
from .exports import export_csv,export_excel
from . import auth

NAV=["Dashboard","Inventory","Projects","Project Details","Allocate / Install Components","Returns","Stock Movements","Reports & Exports","Backup & Restore","Settings"]
class Dialog(QDialog):
    """Consistent, readable data-entry dialog used throughout the application."""
    def __init__(self,title,fields,parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(500)
        self.setModal(True)
        self.fields={}
        outer=QVBoxLayout(self)
        outer.setContentsMargins(24,22,24,20)
        outer.setSpacing(16)
        heading=QLabel(title)
        heading.setObjectName("dialogTitle")
        outer.addWidget(heading)
        form=QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(13)
        for key,label,kind,opts in fields:
            if kind=="num":
                w=QSpinBox();w.setRange(0,1000000000);w.setMinimumHeight(38)
            elif kind=="choice":
                w=QComboBox();w.addItems(opts);w.setMinimumHeight(38)
            elif kind=="multi":
                w=QTextEdit();w.setMinimumHeight(90)
            else:
                w=QLineEdit();w.setMinimumHeight(38)
            self.fields[key]=w
            lab=QLabel(label)
            lab.setObjectName("fieldLabel")
            form.addRow(lab,w)
        outer.addLayout(form)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
    def values(self):
        out={}
        for key,w in self.fields.items():
            out[key]=w.value() if isinstance(w,(QDoubleSpinBox,QSpinBox)) else w.currentText() if isinstance(w,QComboBox) else w.toPlainText().strip() if isinstance(w,QTextEdit) else w.text().strip()
        return out


class MultiAllocationDialog(QDialog):
    """Responsive, searchable multi-item allocation dialog."""
    def __init__(self, projects, items, parent=None, lock_project=False):
        super().__init__(parent)
        self.setWindowTitle("Allocate components to project")
        self.setModal(True)
        self.setMinimumSize(760, 560)
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.resize(min(980, int(area.width() * .78)), min(760, int(area.height() * .84)))
        self.projects, self.items = projects, items
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 22)
        root.setSpacing(14)

        heading = QLabel("Allocate components to project")
        heading.setObjectName("dialogTitle")
        root.addWidget(heading)
        intro = QLabel("Choose a project, set the allocation date, then add the components and quantities.")
        intro.setObjectName("dialogIntro")
        intro.setWordWrap(True)
        root.addWidget(intro)

        project_row = QHBoxLayout()
        project_col = QVBoxLayout(); project_col.setSpacing(6)
        project_label = QLabel("Project"); project_label.setObjectName("fieldLabel")
        self.project = QComboBox(); self.project.setMinimumHeight(42); self.project.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for project in projects:
            self.project.addItem(f"{project[1]} — {project[2]}", project[0])
        project_col.addWidget(project_label); project_col.addWidget(self.project)
        project_row.addLayout(project_col, 3)
        date_col = QVBoxLayout(); date_col.setSpacing(6)
        date_label = QLabel("Allocation date"); date_label.setObjectName("fieldLabel")
        self.allocation_date = QDateEdit(); self.allocation_date.setCalendarPopup(True); self.allocation_date.setDisplayFormat("dd MMM yyyy")
        self.allocation_date.setDate(__import__('PySide6.QtCore', fromlist=['QDate']).QDate.currentDate())
        self.allocation_date.setMinimumHeight(42); self.allocation_date.setMinimumWidth(170)
        date_col.addWidget(date_label); date_col.addWidget(self.allocation_date)
        project_row.addLayout(date_col, 1)
        root.addLayout(project_row)
        if lock_project: self.project.setEnabled(False)

        section_row = QHBoxLayout()
        section = QLabel("Items to allocate"); section.setObjectName("sectionTitle")
        section_row.addWidget(section); section_row.addStretch(1)
        self.count_label = QLabel("0 items added"); self.count_label.setObjectName("mutedLabel")
        section_row.addWidget(self.count_label); root.addLayout(section_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["INVENTORY ITEM", "QUANTITY", "ACTION"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 145); self.table.setColumnWidth(2, 105)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.setMinimumHeight(180); self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        root.addWidget(self.table, 1)

        add_row = QHBoxLayout()
        add = QPushButton("＋  Add another item"); add.setObjectName("secondaryButton")
        add.clicked.connect(self.add_row); add_row.addWidget(add); add_row.addStretch(1)
        root.addLayout(add_row)

        notes_row = QHBoxLayout()
        notes_col = QVBoxLayout(); notes_col.setSpacing(6)
        notes_label = QLabel("Allocation notes (optional)"); notes_label.setObjectName("fieldLabel")
        self.notes = QLineEdit(); self.notes.setPlaceholderText("Add any instructions or context for this allocation")
        notes_col.addWidget(notes_label); notes_col.addWidget(self.notes)
        operator_col = QVBoxLayout(); operator_col.setSpacing(6)
        operator_label = QLabel("Operator (optional)"); operator_label.setObjectName("fieldLabel")
        self.operator = QLineEdit(); self.operator.setPlaceholderText("Name of person handling allocation")
        operator_col.addWidget(operator_label); operator_col.addWidget(self.operator)
        notes_row.addLayout(notes_col, 2); notes_row.addLayout(operator_col, 1)
        root.addLayout(notes_row)

        footer = QHBoxLayout(); footer.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Allocate all items")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primaryButton")
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        footer.addWidget(buttons); root.addLayout(footer)
        self.add_row()

    def add_row(self):
        row = self.table.rowCount(); self.table.insertRow(row); self.table.setRowHeight(row, 58)
        combo = QComboBox(); combo.setEditable(True); combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        combo.setMinimumHeight(38); combo.setPlaceholderText("Search inventory items…")
        for item in self.items:
            combo.addItem(item["name"], item["id"])
            combo.setItemData(combo.count() - 1, f"{item['name']} · {item['item_code']}", Qt.ItemDataRole.ToolTipRole)
        completer = combo.completer(); completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains); completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        combo.setCurrentIndex(-1); combo.lineEdit().setPlaceholderText("Type an item name to search")
        qty = QSpinBox(); qty.setRange(1, 1000000000); qty.setValue(1); qty.setMinimumHeight(38); qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        remove = QPushButton("Remove"); remove.setObjectName("quietButton"); remove.setMinimumHeight(36)
        remove.clicked.connect(lambda _=False, b=remove: self.remove_button_row(b))
        self.table.setCellWidget(row, 0, combo); self.table.setCellWidget(row, 1, qty); self.table.setCellWidget(row, 2, remove)
        combo.currentIndexChanged.connect(self.update_count)
        self.update_count()

    def remove_button_row(self, button):
        if self.table.rowCount() <= 1: return
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 2) is button:
                self.table.removeRow(row); break
        self.update_count()

    def update_count(self, *_):
        self.count_label.setText(f"{self.table.rowCount()} item row(s)")

    def values(self):
        entries = []
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 0)
            item_id = combo.currentData()
            if item_id is None: raise ValueError(f"Choose an inventory item for row {row + 1}.")
            entries.append((item_id, self.table.cellWidget(row, 1).value()))
        if len({x[0] for x in entries}) != len(entries):
            raise ValueError("Each item should appear only once. Combine quantities for duplicate items.")
        return (self.project.currentData(), entries, self.notes.text().strip(),
                self.operator.text().strip(), self.allocation_date.date().toString("yyyy-MM-dd"))

    def accept(self):
        try: self.values(); super().accept()
        except Exception as error: QMessageBox.warning(self, "Check allocation", str(error))


class PasswordDialog(QDialog):
    def __init__(self, title, require_current=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title); self.setMinimumWidth(430)
        layout=QVBoxLayout(self); layout.setContentsMargins(24,22,24,20); layout.setSpacing(12)
        heading=QLabel(title); heading.setObjectName("dialogTitle"); layout.addWidget(heading)
        self.current=QLineEdit(); self.current.setEchoMode(QLineEdit.EchoMode.Password); self.current.setPlaceholderText("Current password")
        self.new=QLineEdit(); self.new.setEchoMode(QLineEdit.EchoMode.Password); self.new.setPlaceholderText("At least 10 characters")
        self.confirm=QLineEdit(); self.confirm.setEchoMode(QLineEdit.EchoMode.Password); self.confirm.setPlaceholderText("Confirm new password")
        if require_current: layout.addWidget(QLabel("Current password")); layout.addWidget(self.current)
        layout.addWidget(QLabel("New password")); layout.addWidget(self.new)
        layout.addWidget(QLabel("Confirm new password")); layout.addWidget(self.confirm)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.require_current=require_current
    def _accept(self):
        if len(self.new.text()) < 10: QMessageBox.warning(self,"Password too short","Use at least 10 characters."); return
        if self.new.text()!=self.confirm.text(): QMessageBox.warning(self,"Passwords do not match","Enter the same new password in both fields."); return
        self.accept()
    def values(self): return self.current.text(),self.new.text(),self.confirm.text()

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.first_run=not auth.has_users()
        self.setWindowTitle("Promise Automation | " + ("Create administrator" if self.first_run else "Sign in"))
        self.setFixedWidth(440)
        layout=QVBoxLayout(self); layout.setContentsMargins(28,26,28,24); layout.setSpacing(13)
        title=QLabel("PROMISE AUTOMATION"); title.setStyleSheet("font-size:20px;font-weight:800;color:#142B4E;"); layout.addWidget(title)
        subtitle=QLabel("Create your administrator account" if self.first_run else "Sign in to Inventory Manager")
        subtitle.setStyleSheet("color:#718096;font-size:13px;"); layout.addWidget(subtitle)
        self.username=QLineEdit(); self.username.setPlaceholderText("Username"); layout.addWidget(self.username)
        self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password); self.password.setPlaceholderText("Password"); layout.addWidget(self.password)
        self.confirm=QLineEdit(); self.confirm.setEchoMode(QLineEdit.EchoMode.Password); self.confirm.setPlaceholderText("Confirm password (first setup)")
        if self.first_run: layout.addWidget(QLabel("Use at least 10 characters for the password.")); layout.addWidget(self.confirm)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create account" if self.first_run else "Sign in")
        buttons.accepted.connect(self._submit); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.setStyleSheet(APP_STYLE)
    def _submit(self):
        username=self.username.text().strip(); password=self.password.text()
        try:
            if self.first_run:
                if password != self.confirm.text(): raise ValueError("Passwords do not match.")
                auth.create_admin(username,password)
            elif not auth.authenticate(username,password):
                raise ValueError("Username or password is incorrect.")
            self.accept()
        except Exception as e: QMessageBox.warning(self,"Unable to sign in",str(e))
    def account(self): return self.username.text().strip()


PAGE_HELP={
    "Dashboard":"A clear overview of stock, projects, and recent inventory activity.",
    "Inventory":"Maintain item details and keep stock quantities accurate.",
    "Projects":"Manage customer projects and review their component usage.",
    "Project Details":"Review and manage all component allocations for one project until it is completed.",
    "Allocate / Install Components":"Reserve components for a project and record component consumption against that project.",
    "Returns":"Record unused components returned from a project.",
    "Stock Movements":"Review the history of stock receipts, allocations, installations, returns, and adjustments.",
    "Reports & Exports":"Export inventory and movement data for review or record keeping.",
    "Backup & Restore":"Create a local backup, restore a previous backup, or copy data to Google Drive.",
    "Settings":"View application data location and run a database integrity check.",
}

APP_STYLE="""
QMainWindow, QDialog { background: #F5F7FB; color: #172B4D; }
QWidget { font-family: 'Inter', 'Segoe UI', 'Arial'; font-size: 13px; }
QLabel { color: #26364B; }
QLabel#pageTitle { font-size: 27px; font-weight: 700; color: #142B4E; }
QLabel#pageSubtitle { font-size: 13px; color: #718096; padding-bottom: 8px; }
QLabel#brandTitle { color: #FFFFFF; font-size: 16px; font-weight: 700; }
QLabel#brandSub { color: #B9C7DA; font-size: 11px; letter-spacing: 1px; }
QLabel#dialogTitle { font-size: 23px; font-weight: 750; color: #142B4E; }
QLabel#dialogIntro, QLabel#mutedLabel { color: #718096; }
QLabel#sectionTitle { font-size: 16px; font-weight: 700; color: #203650; }
QLabel#fieldLabel { color: #34445B; font-weight: 600; }
QWidget#sidebar { background: #142B4E; }
QListWidget { background: transparent; color: #D9E3F0; border: none; outline: none; padding: 6px 8px; }
QListWidget::item { padding: 12px 13px; margin: 3px 0; border-radius: 7px; }
QListWidget::item:hover { background: #203D65; color: #FFFFFF; }
QListWidget::item:selected { background: #2E5B91; color: #FFFFFF; font-weight: 600; }
QPushButton { background: #E8EEF6; color: #1E3A5F; border: 1px solid #D5DFEB; border-radius: 7px; padding: 9px 14px; min-height: 19px; font-weight: 600; }
QPushButton:hover { background: #DCE7F4; border-color: #B7C9DF; }
QPushButton:pressed { background: #CEDCED; }
QPushButton#primaryButton { background: #245A96; color: white; border: 1px solid #245A96; }
QPushButton#primaryButton:hover { background: #1D4A7C; }
QPushButton#quietButton { background: transparent; border-color: transparent; color: #52657D; }
QPushButton#quietButton:hover { background: #FDECEC; color: #B42318; }
QPushButton#secondaryButton { background: #EDF3FA; color: #245A96; border-color: #D7E3F1; }
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox, QTextEdit { background: #FFFFFF; color: #1D2F45; border: 1px solid #D5DEE9; border-radius: 7px; padding: 8px 10px; selection-background-color: #CFE1F6; }
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus, QTextEdit:focus { border: 1px solid #4B83BE; }
QComboBox QAbstractItemView { background: #FFFFFF; color: #1D2F45; selection-background-color: #245A96; selection-color: #FFFFFF; border: 1px solid #CBD6E4; padding: 5px; }
QComboBox::drop-down { border: none; width: 30px; background: #F1F5FA; border-top-right-radius: 7px; border-bottom-right-radius: 7px; }
QComboBox QAbstractItemView::item { min-height: 32px; padding: 7px 10px; }
QDateEdit { background: #FFFFFF; color: #1D2F45; border: 1px solid #D5DEE9; border-radius: 7px; padding: 8px 10px; min-height: 24px; }
QDateEdit::drop-down { border: none; width: 30px; background: #F1F5FA; }
QCalendarWidget QWidget { background: #FFFFFF; color: #1D2F45; }
QTableWidget { background: #FFFFFF; alternate-background-color: #F8FAFD; color: #27384D; border: 1px solid #E0E7F0; border-radius: 9px; gridline-color: #EDF1F6; selection-background-color: #E5EFFB; selection-color: #142B4E; outline: none; }
QTableWidget::item { padding: 7px 9px; border-bottom: 1px solid #F0F3F7; }
QHeaderView::section { background: #EAF0F7; color: #53657C; padding: 11px 9px; border: none; border-bottom: 1px solid #DCE5EF; font-weight: 700; }
QGroupBox { background: #FFFFFF; border: 1px solid #E0E7F0; border-radius: 10px; margin-top: 8px; padding: 15px; font-weight: 600; color: #61738A; }
QGroupBox::title { subcontrol-origin: margin; left: 13px; padding: 0 5px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #CAD5E3; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QDialogButtonBox QPushButton { min-width: 88px; }
"""

class MainWindow(QMainWindow):
    logout_requested = Signal()
    def __init__(self, username="admin"):
        super().__init__()
        self.username=username
        self.logged_out=False
        self.setWindowTitle("Promise Automation | Inventory Manager")
        self.resize(1400,860)
        self.setMinimumSize(1080,700)
        root=QWidget();self.setCentralWidget(root)
        h=QHBoxLayout(root);h.setContentsMargins(0,0,0,0);h.setSpacing(0)
        side=QWidget();side.setObjectName("sidebar");side.setFixedWidth(238)
        sv=QVBoxLayout(side);sv.setContentsMargins(14,22,14,18);sv.setSpacing(8)
        brand=QLabel("PROMISE AUTOMATION");brand.setObjectName("brandTitle");sv.addWidget(brand)
        sub=QLabel("INVENTORY MANAGEMENT");sub.setObjectName("brandSub");sv.addWidget(sub)
        divider=QFrame();divider.setFrameShape(QFrame.Shape.HLine);divider.setStyleSheet("color:#2B4567;margin:12px 0;");sv.addWidget(divider)
        self.nav=QListWidget();self.nav.addItems(NAV);self.nav.setCurrentRow(0);sv.addWidget(self.nav,1)
        footer=QLabel("Local workspace  •  Single user");footer.setStyleSheet("color:#9FB0C6;font-size:11px;padding:8px 4px;");sv.addWidget(footer)
        h.addWidget(side)
        content=QWidget();v=QVBoxLayout(content);v.setContentsMargins(30,26,30,24);v.setSpacing(12)
        headingRow=QHBoxLayout();headingRow.setSpacing(16)
        headingCol=QVBoxLayout();headingCol.setSpacing(4)
        self.title=QLabel();self.title.setObjectName("pageTitle");headingCol.addWidget(self.title)
        self.subtitle=QLabel();self.subtitle.setObjectName("pageSubtitle");headingCol.addWidget(self.subtitle)
        headingRow.addLayout(headingCol,1)
        self.pageAction=QLabel("PROMISE AUTOMATION");self.pageAction.setStyleSheet("color:#8493A7;font-size:10px;font-weight:700;letter-spacing:1px;");headingRow.addWidget(self.pageAction,0,Qt.AlignmentFlag.AlignTop)
        headingRow.addWidget(QLabel(f"Signed in: {self.username}"),0,Qt.AlignmentFlag.AlignTop)
        headingRow.addWidget(self.btn("Log out",self.logout),0,Qt.AlignmentFlag.AlignTop)
        v.addLayout(headingRow)
        self.stack=QStackedWidget();v.addWidget(self.stack,1);h.addWidget(content,1)
        self.tables={}
        for name in NAV:
            page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,4,0,0);layout.setSpacing(14);self.stack.addWidget(page)
            if name=="Dashboard":
                self.cards=QGridLayout();self.cards.setHorizontalSpacing(14);self.cards.setVerticalSpacing(14);layout.addLayout(self.cards)
                section=QLabel("Recent inventory activity");section.setStyleSheet("font-size:16px;font-weight:700;color:#203650;padding-top:8px;");layout.addWidget(section)
                self.tables[name]=self.table(["Date and time","Item","Movement type","Quantity","Project","Notes"]);layout.addWidget(self.tables[name],1)
            elif name=="Inventory":
                bar=QHBoxLayout();bar.setSpacing(9);self.search=QLineEdit();self.search.setPlaceholderText("Search by item name or internal ID…");self.search.setClearButtonEnabled(True);self.search.textChanged.connect(self.refresh);bar.addWidget(self.search,1)
                for text,fn,kind in [("Add item",self.add_item,"primaryButton"),("Record stock receipt",self.receive,""),("Adjust stock count",self.adjust,""),("Edit selected item",self.edit_item,"")]:bar.addWidget(self.btn(text,fn,kind))
                layout.addLayout(bar);self.tables[name]=self.table(["Internal ID","Item name","Category","Unit","Storage location","Physical stock","Allocated to projects","Available stock","Minimum stock level","Status"]);layout.addWidget(self.tables[name],1)
            elif name=="Projects":
                bar=QHBoxLayout();self.ps=QLineEdit();self.ps.setPlaceholderText("Search by project, code, or customer…");self.ps.setClearButtonEnabled(True);self.ps.textChanged.connect(self.refresh);bar.addWidget(self.ps,1);bar.addWidget(self.btn("Create project",self.add_project,"primaryButton"));bar.addWidget(self.btn("Project stock reconciliation",self.reconcile));layout.addLayout(bar)
                self.tables[name]=self.table(["Internal ID","Project code","Project name","Customer","Project manager","Status"]);layout.addWidget(self.tables[name],1)
            elif name=="Project Details":
                bar=QHBoxLayout();self.project_detail_combo=QComboBox();self.project_detail_combo.setMinimumWidth(420);self.project_detail_combo.currentIndexChanged.connect(self.refresh);bar.addWidget(QLabel("Select project"));bar.addWidget(self.project_detail_combo,1);bar.addWidget(self.btn("Add multiple items",self.allocate_to_detail,"primaryButton"));bar.addWidget(self.btn("Edit selected allocation",self.edit_allocation));bar.addWidget(self.btn("Remove selected allocation",self.remove_allocation));layout.addLayout(bar)
                self.project_detail_summary=QLabel("Select a project to view its allocated components.");self.project_detail_summary.setObjectName("pageSubtitle");layout.addWidget(self.project_detail_summary)
                self.tables[name]=self.table(["Allocation ID","Allocation date","Item code","Item name","Allocated","Installed / Consumed","Returned","Remaining","Unit","Notes"]);layout.addWidget(self.tables[name],1)
            elif name=="Allocate / Install Components":
                intro=QLabel("Reserve stock for a project, then record components consumed for that project. No machine-level tracking is maintained.");intro.setObjectName("pageSubtitle");layout.addWidget(intro)
                bar=QHBoxLayout();bar.addWidget(self.btn("Allocate components to project",self.allocate,"primaryButton"));bar.addWidget(self.btn("Record component installation",self.install));bar.addStretch(1);layout.addLayout(bar)
                self.tables[name]=self.table(["Allocation ID","Project code","Component","Allocated quantity","Installed quantity","Returned quantity","Quantity remaining","Unit"]);layout.addWidget(self.tables[name],1)
            elif name=="Returns":
                intro=QLabel("Only unused components in reusable condition are returned to available stock.");intro.setObjectName("pageSubtitle");layout.addWidget(intro)
                bar=QHBoxLayout();bar.addWidget(self.btn("Return unused components",self.return_item,"primaryButton"));bar.addStretch(1);layout.addLayout(bar)
                self.tables[name]=self.table(["Return ID","Project code","Component","Quantity","Condition","Date and time","Notes"]);layout.addWidget(self.tables[name],1)
            elif name=="Stock Movements":
                bar=QHBoxLayout();bar.addWidget(self.btn("Refresh movement history",self.refresh,"primaryButton"));bar.addStretch(1);layout.addLayout(bar)
                self.tables[name]=self.table(["Movement ID","Date and time","Item ID","Item name","Movement type","Quantity","Project code","Source","Destination","Reason / notes"]);layout.addWidget(self.tables[name],1)
            elif name=="Reports & Exports":
                intro=QLabel("Export business records for review, sharing, or record keeping.");intro.setObjectName("pageSubtitle");layout.addWidget(intro)
                layout.addWidget(self.report_card("Inventory report","Export item details and current stock quantities to an Excel workbook.","Export inventory to Excel",self.excel))
                layout.addWidget(self.report_card("Stock movement report","Export the stock movement ledger as a CSV file.","Export stock movements to CSV",self.csv));layout.addStretch(1)
            elif name=="Backup & Restore":
                info=QLabel(f"Application data folder: {APP_DIR}");info.setWordWrap(True);info.setObjectName("pageSubtitle");layout.addWidget(info)
                bar=QHBoxLayout();bar.addWidget(self.btn("Create local backup",self.backup,"primaryButton"));bar.addWidget(self.btn("Restore selected backup",self.restore_backup));bar.addWidget(self.btn("Back up to Google Drive",self.drive));bar.addStretch(1);layout.addLayout(bar)
                self.tables[name]=self.table(["Backup file","Last modified","File size (KB)"]);layout.addWidget(self.tables[name],1)
            else:
                info=QLabel(f"Database file: {DB_PATH}");info.setWordWrap(True);info.setObjectName("pageSubtitle");layout.addWidget(info)
                layout.addWidget(self.report_card("Database integrity","Check whether the local database passes SQLite's integrity check.","Check database integrity",self.integrity))
                layout.addWidget(self.report_card("Application data","Open the folder containing local application data and backups.","Open data folder",self.open_folder))
                layout.addWidget(self.report_card("Account security","Change the password for the account currently signed in.","Change password",self.change_password))
                layout.addStretch(1)
        self.nav.currentRowChanged.connect(self.change)
        self.setStyleSheet(APP_STYLE)
        self.change(0)

    def btn(self,text,fn,kind=""):
        b=QPushButton(text)
        if kind:b.setObjectName(kind)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(fn)
        return b

    def report_card(self,title,description,button_text,callback):
        box=QGroupBox(title);row=QHBoxLayout(box);row.setContentsMargins(18,18,18,18);row.setSpacing(20)
        text_col=QVBoxLayout();heading=QLabel(title);heading.setStyleSheet("font-size:15px;font-weight:700;color:#203650;")
        desc=QLabel(description);desc.setWordWrap(True);desc.setStyleSheet("color:#718096;")
        text_col.addWidget(heading);text_col.addWidget(desc);row.addLayout(text_col,1);row.addWidget(self.btn(button_text,callback,"primaryButton"));return box

    def table(self,headers):
        t=QTableWidget(0,len(headers));t.setHorizontalHeaderLabels(headers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True);t.setShowGrid(False);t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(46)
        t.verticalHeader().setMinimumSectionSize(42)
        t.setCornerButtonEnabled(False)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        t.horizontalHeader().setStretchLastSection(True)
        t.setWordWrap(False);t.setSortingEnabled(False)
        t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        t.setMinimumWidth(500)
        return t

    def rows(self,t,rows):
        t.setUpdatesEnabled(False);t.setRowCount(len(rows))
        for r,row in enumerate(rows):
            for c,val in enumerate(row):
                item=QTableWidgetItem("" if val is None else str(val))
                if c==0:item.setForeground(QColor("#52657D"))
                t.setItem(r,c,item)
        t.resizeColumnsToContents()
        # Keep wide tables usable instead of letting long text dictate the entire window width.
        for col in range(t.columnCount()):
            header=t.horizontalHeaderItem(col).text().lower()
            if any(word in header for word in ("name","notes","reason","customer","location","component","project")):
                t.setColumnWidth(col,min(max(t.columnWidth(col),120),260))
            else:t.setColumnWidth(col,min(max(t.columnWidth(col),86),180))
        t.setUpdatesEnabled(True)

    def change(self,i):
        if i<0:return
        self.stack.setCurrentIndex(i);self.title.setText(NAV[i]);self.subtitle.setText(PAGE_HELP.get(NAV[i],""));self.refresh()

    def msg(self,title,text):QMessageBox.information(self,title,text)
    def fail(self,e):QMessageBox.warning(self,"Unable to complete action",str(e))
    def selected(self,t,col=0):
        r=t.currentRow()
        if r<0:raise ValueError("Select a record from the table first.")
        cell=t.item(r,col)
        if cell is None:raise ValueError("The selected record could not be read. Refresh the table and try again.")
        return cell.text()
    def refresh(self,*args):
        name=NAV[self.stack.currentIndex()]
        try:
            if name=="Dashboard":
                while self.cards.count():
                    item=self.cards.takeAt(0)
                    if item.widget():item.widget().deleteLater()
                with connect() as c:
                    n=c.execute("SELECT COUNT(*) n FROM items WHERE active=1").fetchone()["n"]
                    p=c.execute("SELECT COUNT(*) n FROM projects WHERE status='Active'").fetchone()["n"]
                    active_items=c.execute("SELECT id,min_stock FROM items WHERE active=1").fetchall()
                    low_stock=sum(1 for item in active_items if stock(item["id"])["available"] <= float(item["min_stock"] or 0))
                    allocated=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM allocations").fetchone()["n"]
                    installed=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM installations").fetchone()["n"]
                    returned=c.execute("SELECT COALESCE(SUM(quantity),0) n FROM returns").fetchone()["n"]
                    outstanding=max(0,allocated-installed-returned)
                    recent=c.execute("SELECT m.occurred_at,i.name,m.movement_type,m.quantity,COALESCE(pr.project_code,''),m.reason FROM movements m JOIN items i ON i.id=m.item_id LEFT JOIN projects pr ON pr.id=m.project_id ORDER BY m.id DESC LIMIT 15").fetchall()
                metrics=[("Active item types",n,"Items currently available for use"),("Active projects",p,"Projects in progress"),("Items at or below minimum",low_stock,"Review stock levels"),("Outstanding allocation qty.",f"{outstanding:g}","Allocated, not yet installed or returned")]
                for ix,(label,val,detail) in enumerate(metrics):
                    box=QGroupBox();box.setMinimumHeight(112);vl=QVBoxLayout(box);vl.setContentsMargins(18,14,18,14);vl.setSpacing(5)
                    title=QLabel(label);title.setStyleSheet("color:#6B7C91;font-size:12px;font-weight:600;")
                    value=QLabel(str(val));value.setStyleSheet("font-size:27px;font-weight:700;color:#1D4F85;")
                    hint=QLabel(detail);hint.setStyleSheet("color:#8795A7;font-size:11px;");hint.setWordWrap(True)
                    vl.addWidget(title);vl.addWidget(value);vl.addWidget(hint);self.cards.addWidget(box,0,ix)
                self.rows(self.tables[name],[[r[0],r[1],r[2].replace("_"," ").title(),r[3],r[4],r[5]] for r in recent])
            elif name=="Inventory":
                with connect() as c:items=c.execute("SELECT * FROM items WHERE name LIKE ? OR item_code LIKE ? ORDER BY name", (f"%{self.search.text()}%",f"%{self.search.text()}%")).fetchall()
                out=[]
                for i in items:
                    s=stock(i["id"]);out.append([i["item_code"],i["name"],i["category"],i["unit"],i["location"],s["physical"],s["allocated"],s["available"],i["min_stock"],"Active" if i["active"] else "Inactive"])
                self.rows(self.tables[name],out)
            elif name=="Projects":
                with connect() as c:r=c.execute("SELECT id,project_code,name,customer,manager,status FROM projects WHERE name LIKE ? OR project_code LIKE ? OR customer LIKE ? ORDER BY id DESC",(f"%{self.ps.text()}%",)*3).fetchall()
                self.rows(self.tables[name],[list(x) for x in r])
            elif name=="Project Details":
                with connect() as c: projects=c.execute("SELECT id,project_code,name,status FROM projects ORDER BY id DESC").fetchall()
                current=self.project_detail_combo.currentData() if self.project_detail_combo.count() else None
                self.project_detail_combo.blockSignals(True);self.project_detail_combo.clear()
                for p in projects:self.project_detail_combo.addItem(f'{p["project_code"]} — {p["name"]} ({p["status"]})',p["id"])
                idx=self.project_detail_combo.findData(current)
                if idx>=0:self.project_detail_combo.setCurrentIndex(idx)
                self.project_detail_combo.blockSignals(False)
                pid=self.project_detail_combo.currentData()
                if pid is None:self.rows(self.tables[name],[]);self.project_detail_summary.setText("No projects have been created yet.")
                else:
                    with connect() as c:r=c.execute("SELECT a.id,a.allocated_at,i.item_code,i.name,a.quantity,COALESCE((SELECT SUM(quantity) FROM installations WHERE allocation_id=a.id),0) ins,COALESCE((SELECT SUM(quantity) FROM returns WHERE allocation_id=a.id),0) ret,i.unit,a.notes FROM allocations a JOIN items i ON i.id=a.item_id WHERE a.project_id=? ORDER BY a.id",(pid,)).fetchall()
                    def display_allocation_date(value):
                        try:
                            from datetime import datetime
                            return datetime.fromisoformat(str(value)).strftime("%d %b %Y")
                        except (TypeError, ValueError):
                            return str(value or "—")
                    self.rows(self.tables[name],[[x["id"],display_allocation_date(x["allocated_at"]),x["item_code"],x["name"],int(x["quantity"]),int(x["ins"]),int(x["ret"]),int(x["quantity"]-x["ins"]-x["ret"]),x["unit"],x["notes"]] for x in r])
                    self.project_detail_summary.setText(f'{len(r)} allocation record(s) · {sum(x["quantity"] for x in r):g} total units allocated · Editing is available until the project is completed or cancelled.')
            elif name=="Allocate / Install Components":
                with connect() as c:r=c.execute("""SELECT a.id,p.project_code,i.name,a.quantity,
                COALESCE((SELECT SUM(quantity) FROM installations WHERE allocation_id=a.id),0) ins,
                COALESCE((SELECT SUM(quantity) FROM returns WHERE allocation_id=a.id),0) ret,i.unit
                FROM allocations a JOIN projects p ON p.id=a.project_id JOIN items i ON i.id=a.item_id ORDER BY a.id DESC""").fetchall()
                self.rows(self.tables[name],[[x["id"],x["project_code"],x["name"],x["quantity"],x["ins"],x["ret"],x["quantity"]-x["ins"]-x["ret"],x["unit"]] for x in r])
            elif name=="Returns":
                with connect() as c:r=c.execute("SELECT r.id,p.project_code,i.name,r.quantity,r.condition,r.returned_at,r.notes FROM returns r JOIN projects p ON p.id=r.project_id JOIN items i ON i.id=r.item_id ORDER BY r.id DESC").fetchall()
                self.rows(self.tables[name],[list(x) for x in r])
            elif name=="Stock Movements":
                with connect() as c:r=c.execute("SELECT m.id,m.occurred_at,i.item_code,i.name,m.movement_type,m.quantity,COALESCE(p.project_code,''),m.source,m.destination,m.reason FROM movements m JOIN items i ON i.id=m.item_id LEFT JOIN projects p ON p.id=m.project_id ORDER BY m.id DESC LIMIT 2000").fetchall()
                self.rows(self.tables[name],[list(x) for x in r])
            elif name=="Backup & Restore":
                from .backups import backups
                self.rows(self.tables[name],[[p.name,__import__("datetime").datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes"),round(p.stat().st_size/1024,1)] for p in backups()])
        except Exception as e:self.fail(e)
    def item_id(self):
        code=self.selected(self.tables["Inventory"],0)
        with connect() as c:return c.execute("SELECT id FROM items WHERE item_code=?",(code,)).fetchone()["id"]
    def add_item(self):
        d=Dialog("Add inventory item",[("name","Item name","text",None),("category","Category","text",None),("unit","Unit","choice",["pieces","metres","sets","boxes","kg","litres","rolls","other"]),("location","Location","text",None),("min_stock","Minimum stock level","num",None),("opening_qty","Opening stock quantity","num",None),("notes","Notes","text",None)],self)
        if d.exec():
            try:services.create_item(**d.values());self.refresh()
            except Exception as e:self.fail(e)
    def receive(self):
        try:i=self.item_id()
        except Exception as e:self.fail(e);return
        d=Dialog("Record stock receipt",[("quantity","Quantity","num",None),("reason","Reason","text",None),("operator","Operator","text",None)],self)
        if d.exec():
            try:services.receive(i,**d.values());self.refresh()
            except Exception as e:self.fail(e)
    def adjust(self):
        try:i=self.item_id()
        except Exception as e:self.fail(e);return
        d=Dialog("Adjust physical stock count",[("new_qty","Counted physical quantity","num",None),("reason","Reason","text",None),("operator","Operator","text",None)],self)
        if d.exec():
            try:services.adjust(i,**d.values());self.refresh()
            except Exception as e:self.fail(e)
    def edit_item(self):
        try:i=self.item_id()
        except Exception as e:self.fail(e);return
        with connect() as c:r=c.execute("SELECT * FROM items WHERE id=?",(i,)).fetchone()
        d=Dialog("Edit inventory item",[("name","Name","text",None),("category","Category","text",None),("unit","Unit","text",None),("location","Location","text",None),("min_stock","Minimum stock level","num",None),("status","Status","choice",["Active","Inactive"]),("notes","Notes","text",None)],self)
        for k,w in d.fields.items():
            val=("Active" if r["active"] else "Inactive") if k=="status" else r[k]
            if hasattr(w,"setText"):w.setText(str(val or ""))
            elif hasattr(w,"setValue"):w.setValue(float(val or 0))
            elif hasattr(w,"setCurrentText"):w.setCurrentText(str(val))
        if d.exec():
            v=d.values()
            try:
                with connect() as c:c.execute("UPDATE items SET name=?,category=?,unit=?,location=?,min_stock=?,active=?,notes=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(v["name"],v["category"],v["unit"],v["location"],v["min_stock"],int(v["status"]=="Active"),v["notes"],i));c.commit()
                self.refresh()
            except Exception as e:self.fail(e)
    def add_project(self):
        d=Dialog("Create project",[("project_code","Project code","text",None),("name","Project name","text",None),("customer","Customer","text",None),("location","Location","text",None),("manager","Manager","text",None),("status","Status","choice",["Planned","Active","On Hold","Completed","Cancelled"]),("start_date","Start date","text",None),("notes","Notes","text",None)],self)
        if d.exec():
            try:services.create_project(**d.values());self.refresh()
            except Exception as e:self.fail(e)
    def options(self):
        with connect() as c:return c.execute("SELECT id,project_code,name FROM projects WHERE status NOT IN ('Completed','Cancelled')").fetchall(),c.execute("SELECT id,item_code,name FROM items WHERE active=1").fetchall()
    def allocate(self):
        ps,items=self.options()
        if not ps or not items:self.msg("Missing data","Create a project and an inventory item before allocating components.");return
        d=MultiAllocationDialog(ps,items,self)
        if d.exec():
            try:
                project_id,entries,notes,operator,allocated_at=d.values()
                services.allocate_many(project_id,entries,notes,operator,allocated_at)
                self.refresh()
                self.msg("Allocation saved",f"{len(entries)} item(s) allocated to the project in one entry.")
            except Exception as e:self.fail(e)
    def allocate_to_detail(self):
        if not self.project_detail_combo.count():return
        project_id=int(self.project_detail_combo.currentData())
        _,items=self.options()
        if not items:self.msg("Missing items","Create an active inventory item first.");return
        d=MultiAllocationDialog([(project_id,self.project_detail_combo.currentText().split(" — ")[0],self.project_detail_combo.currentText())],items,self,lock_project=True)
        if d.exec():
            try:
                pid,entries,notes,operator,allocated_at=d.values();services.allocate_many(pid,entries,notes,operator,allocated_at);self.refresh()
            except Exception as e:self.fail(e)
    def edit_allocation(self):
        try: aid=int(self.selected(self.tables["Project Details"],0))
        except Exception as e:self.fail(e);return
        with connect() as c:
            a=c.execute("SELECT * FROM allocations WHERE id=?",(aid,)).fetchone()
            items=c.execute("SELECT id,item_code,name FROM items WHERE active=1 ORDER BY name").fetchall()
        d=Dialog("Edit project allocation",[("item","Item","choice",[f'{x["id"]} | {x["item_code"]} — {x["name"]}' for x in items]),("quantity","Quantity (whole number)","num",None),("notes","Notes","text",None)],self)
        d.fields["item"].setCurrentText(next((f'{x["id"]} | {x["item_code"]} — {x["name"]}' for x in items if x["id"]==a["item_id"]),""))
        d.fields["quantity"].setValue(int(a["quantity"]));d.fields["notes"].setText(a["notes"] or "")
        if d.exec():
            try:
                v=d.values();services.update_allocation(aid,int(v["item"].split("|")[0]),v["quantity"],v["notes"]);self.refresh()
            except Exception as e:self.fail(e)
    def remove_allocation(self):
        try:aid=int(self.selected(self.tables["Project Details"],0))
        except Exception as e:self.fail(e);return
        if QMessageBox.question(self,"Remove allocation","Remove this allocation record? This is allowed only when no installation or return history exists.")!=QMessageBox.Yes:return
        try:services.delete_allocation(aid);self.refresh()
        except Exception as e:self.fail(e)
    def allocations(self):
        with connect() as c:return c.execute("""SELECT a.id,p.project_code,i.name,a.quantity,
        COALESCE((SELECT SUM(quantity) FROM installations WHERE allocation_id=a.id),0) ins,
        COALESCE((SELECT SUM(quantity) FROM returns WHERE allocation_id=a.id),0) ret FROM allocations a JOIN projects p ON p.id=a.project_id JOIN items i ON i.id=a.item_id""").fetchall()
    def install(self):
        aa=[a for a in self.allocations() if a["quantity"]-a["ins"]-a["ret"]>0]
        if not aa:self.msg("No allocations","Allocate components to a project before recording an installation.");return
        d=Dialog("Record component consumption",[("allocation","Allocation","choice",[f'{a["id"]} | {a["project_code"]} — {a["name"]} (left {a["quantity"]-a["ins"]-a["ret"]:g})' for a in aa]),("quantity","Quantity","num",None),("installed_at","Date and time (optional)","text",None),("notes","Notes","text",None)],self)
        if d.exec():
            try:v=d.values();services.install(int(v["allocation"].split("|")[0]),v["quantity"],v["installed_at"],v["notes"]);self.refresh()
            except Exception as e:self.fail(e)
    def return_item(self):
        aa=[a for a in self.allocations() if a["quantity"]-a["ins"]-a["ret"]>0]
        if not aa:self.msg("No outstanding allocation","There are no outstanding allocated components to return.");return
        d=Dialog("Return unused components",[("allocation","Allocation","choice",[f'{a["id"]} | {a["project_code"]} — {a["name"]} (left {a["quantity"]-a["ins"]-a["ret"]:g})' for a in aa]),("quantity","Quantity","num",None),("condition","Condition","choice",["Good / reusable","Damaged","Requires inspection","Other"]),("notes","Notes","text",None)],self)
        if d.exec():
            try:v=d.values();services.return_unused(int(v["allocation"].split("|")[0]),v["quantity"],v["condition"],v["notes"]);self.refresh()
            except Exception as e:self.fail(e)
    def reconcile(self):
        try:pid=int(self.selected(self.tables["Projects"],0))
        except Exception as e:self.fail(e);return
        from .services import reconciliation
        rr=reconciliation(pid);self.msg("Reconciliation","\n".join(f'{x["item_code"]} {x["name"]}: allocated {x["allocated"]}, installed {x["installed"]}, returned {x["returned"]}, outstanding {x["outstanding"]} {x["unit"]}' for x in rr) or "No allocations.")
    def excel(self):
        p,_=QFileDialog.getSaveFileName(self,"Export inventory","inventory.xlsx","Excel (*.xlsx)")
        if p:
            try:export_excel(p);self.msg("Exported",p)
            except Exception as e:self.fail(e)
    def csv(self):
        p,_=QFileDialog.getSaveFileName(self,"Export movements","movements.csv","CSV (*.csv)")
        if p:
            try:export_csv(p);self.msg("Exported",p)
            except Exception as e:self.fail(e)
    def backup(self):
        try:p=local_backup();self.refresh();self.msg("Backup complete",str(p))
        except Exception as e:self.fail(e)
    def restore_backup(self):
        try:
            p=self.selected(self.tables["Backup & Restore"],0);path=next(x for x in backups() if x.name==p)
            if QMessageBox.question(self,"Confirm restore","The current database will be replaced. A safety backup will be created first. Continue only if you intend to restore this older version of the data.")!=QMessageBox.Yes:return
            safety=restore(path);self.msg("Restore complete",f"The selected backup was restored. A safety backup was saved at: {safety}. Restart the application before continuing.")
        except Exception as e:self.fail(e)
    def drive(self):
        if QMessageBox.question(self,"Google Drive","Start Google OAuth and upload a verified database snapshot?")!=QMessageBox.Yes:return
        try:r=google_drive_backup();self.msg("Google Drive backup",f'Backup uploaded successfully: {r.get("name")}')
        except Exception as e:self.fail(e)
    def integrity(self):
        with connect() as c:r=c.execute("PRAGMA integrity_check").fetchone()[0]
        self.msg("Integrity check",r)
    def change_password(self):
        d=PasswordDialog("Change password", require_current=True, parent=self)
        if d.exec():
            current,new,confirm=d.values()
            try:
                if new != confirm: raise ValueError("New password and confirmation do not match.")
                auth.change_password(self.username,current,new)
                self.msg("Password changed","Your password has been updated successfully.")
            except Exception as e:self.fail(e)
    def logout(self):
        if QMessageBox.question(self,"Log out","Log out of Promise Automation Inventory Manager?") != QMessageBox.Yes:return
        self.logged_out=True
        set_session_authenticated(False)
        self.close()
        self.logout_requested.emit()
    def open_folder(self):
        if sys.platform=="win32":os.startfile(str(APP_DIR))
        elif sys.platform=="darwin":subprocess.Popen(["open",str(APP_DIR)])
        else:subprocess.Popen(["xdg-open",str(APP_DIR)])
