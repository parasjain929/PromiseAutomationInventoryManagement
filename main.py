import sys
from PySide6.QtWidgets import QApplication
from promise_inventory.db import initialize_database, set_session_authenticated
import promise_inventory.db as database
from promise_inventory.ui import MainWindow, LoginDialog

if __name__ == "__main__":
    initialize_database()
    app = QApplication(sys.argv)
    app.setApplicationName("Promise Automation Inventory Manager")
    database.ENFORCE_SESSION = True
    while True:
        login = LoginDialog()
        if login.exec() != LoginDialog.DialogCode.Accepted:
            break
        set_session_authenticated(True)
        window = MainWindow(username=login.account())
        window.logout_requested.connect(app.quit)
        window.show()
        app.exec()
        set_session_authenticated(False)
        if not window.logged_out:
            break
    sys.exit(0)
