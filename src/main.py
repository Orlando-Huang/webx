# nuitka-project: --quiet
# nuitka-project: --standalone
# nuitka-project: --enable-plugin=pyside6
# nuitka-project: --lto=yes
# nuitka-project: --clang
# nuitka-project: --assume-yes-for-downloads
# not-nuitka-project: --windows-console-mode=disable
# nuitka-project: --windows-icon-from-ico=src/icons/WebX.ico

import os
import sys
import csv
import socket
import requests
import argparse
import subprocess
import portalocker
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from typing import Literal
from PySide6 import (
    QtCore,
    QtWidgets,
    QtWebEngineWidgets,
    QtWebEngineCore,
    QtGui
)
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"

app = QtWidgets.QApplication(sys.argv)
THEME = 'dark' if app.palette().color(QtGui.QPalette.ColorRole.Window).value()<128 else 'light'

WEBX = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons', 'WebX.png')
ICONS = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons', THEME)
HTML = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'html')
DATA = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'data')

VERSION = 0.1
LATEST_VERSION_URL = "https://raw.githubusercontent.com/not-immortalcoding/webx/refs/heads/main/latest_version.txt"

BUILTIN_PATHS: dict[QtCore.QUrl, str] = {
    QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'home.html')): '',
    QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'snake.html')): 'webx://snake'
}

bookmarks_window = None
history_window = None
permissions_window = None
   
with open(os.path.join(DATA, 'bookmarks.csv'), 'r', newline='', encoding='utf-8') as f:
    bookmarks = list(csv.reader(f))[1:]
with open(os.path.join(DATA, 'history.csv'), 'r', newline='', encoding='utf-8') as f:
    history = list(csv.reader(f))[1:][::-1]
with open(os.path.join(DATA, 'permissions.csv'), 'r', newline='', encoding='utf-8') as f:
    permissions = list(csv.reader(f))[1:]


def is_connected():
    try:
        socket.create_connection(("1.1.1.1", 53))
        return True
    except OSError:
        return False


def write(data=None):
    if data is bookmarks:
        with open(os.path.join(DATA, 'bookmarks.csv'), 'w', newline='', encoding='utf-8') as file:
            w = csv.writer(file)
            w.writerow(['Name', 'Url'])
            w.writerows(bookmarks)
        if bookmarks_window: bookmarks_window.refresh()
    elif data is history:
        with open(os.path.join(DATA, 'history.csv'), 'w', newline='', encoding='utf-8') as file:
            w = csv.writer(file)
            w.writerow(['Title', 'Url'])
            w.writerows(history[::-1])
        if history_window: history_window.refresh()
    elif data is permissions:
        with open(os.path.join(DATA, 'permissions.csv'), 'w', newline='', encoding='utf-8') as file:
            w = csv.writer(file)
            w.writerow(['Origin', 'Permission', 'Granted'])
            w.writerows(permissions)
        if permissions_window: permissions_window.refresh()
    for w in QtWidgets.QApplication.topLevelWidgets():
        if isinstance(w, MainWindow) and data in (bookmarks, history):
            w.update_menu_items(data)


def byte_to_string(byte):
    match byte:
        case 0: return "?"
        case b if b < 1024: return f"{b} B"
        case b if b < 1024 ** 2: return f"{b / 1024:.2f} KB"
        case b if b < 1024 ** 3: return f"{b / (1024 ** 2):.2f} MB"
        case b: return f"{b / (1024 ** 3):.2f} GB"


class Signals(QtCore.QObject):
    create_window = QtCore.Signal(object)


class StatusFileHandler(FileSystemEventHandler):
    def on_modified(self, event):
        status = os.path.join(DATA, 'status')
        if event.src_path == status:
            with open(status, 'r+') as f:
                cmd = f.readline().split()
                if cmd: signals.create_window.emit(cmd[1] if len(cmd) > 1 else None)
                f.truncate(0)


class CheckUpdateWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Check Updates")
        self.setWindowIcon(QtGui.QIcon(WEBX))

        self.root = QtWidgets.QVBoxLayout()
        self.label = QtWidgets.QLabel("Checking for Updates (Keep waiting if it displays not responding)...")
        self.upgrade_button = QtWidgets.QPushButton("Upgrade")
        self.done = False
        self.label.setFont(QtGui.QFont(QtGui.QFont().family(), 12, QtGui.QFont.Weight.Medium, False))
        self.upgrade_button.clicked.connect(self.upgrade)
        self.root.addWidget(self.label)
        self.setLayout(self.root)
        self.setWindowFlags(QtCore.Qt.WindowType.WindowMinimizeButtonHint)
        self.show()
        QtCore.QTimer.singleShot(0, self.check_updates)

    def check_updates(self):
        latest = float(requests.get(LATEST_VERSION_URL).text) if is_connected() else None
        if latest == VERSION:
            self.label.setText("Already Latest Version")
        else:
            self.label.setText("You need to upgrade WebX!")
            self.root.addWidget(self.upgrade_button)
        if not latest: self.label.setText("No internet!")

        self.setWindowFlags(QtCore.Qt.WindowType.WindowMinimizeButtonHint | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.show()
        self.adjustSize()
        self.done = True

    @staticmethod
    def upgrade():
        subprocess.Popen([os.path.join(os.path.dirname(os.path.realpath(__file__)), 'upgrade.exe')])
        sys.exit()

    def resizeEvent(self, _): self.adjustSize()
    def closeEvent(self, event): event.accept() if self.done else event.ignore()


class DownloadWindow(QtWidgets.QWidget):
    def __init__(self, name, total_size):
        super().__init__()

        self.setWindowTitle(f"Download File: {name}")
        self.setWindowIcon(QtGui.QIcon(WEBX))

        root = QtWidgets.QVBoxLayout()
        self.done = False
        self.name = name
        self.total_size = byte_to_string(total_size)
        self.label = QtWidgets.QLabel(f"{self.name} downloaded 0 B/{self.total_size}")

        self.label.setFont(QtGui.QFont(QtGui.QFont().family(), 12, QtGui.QFont.Weight.Medium, False))
        root.addWidget(self.label)
        self.setLayout(root)
        self.setWindowFlags(QtCore.Qt.WindowType.WindowMinimizeButtonHint)
        self.show()

    def update_size(self, received_bytes):
        received = byte_to_string(received_bytes)
        self.label.setText(f"{self.name} downloaded {received}/{self.total_size}")

    def set_done(self):
        self.label.setText(f"{self.name} download finished!")
        self.adjustSize()
        self.setWindowFlags(QtCore.Qt.WindowType.WindowMinimizeButtonHint | QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.show()
        self.done = True

    def resizeEvent(self, _): self.adjustSize()
    def closeEvent(self, event): event.accept() if self.done else event.ignore()


class TableWindow(QtWidgets.QWidget):
    def __init__(self, data, from_window):
        super().__init__()

        self.setFixedSize(QtCore.QSize(600, 400))
        self.setWindowIcon(QtGui.QIcon(WEBX))
        self.data = data
        self.from_window = from_window

        root = QtWidgets.QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.table = QtWidgets.QTableWidget()
        self.table.setRowCount(len(self.data))
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.doubleClicked.connect(self.double_clicked)

        add = QtWidgets.QPushButton("Add Bookmark", self)
        add.clicked.connect(self.add_bookmark)

        remove = QtWidgets.QPushButton("Remove Selected", self)
        remove.clicked.connect(self.remove_selected)

        clear = QtWidgets.QPushButton("Clear All", self)
        clear.clicked.connect(self.clear_all)

        root.addWidget(self.table)
        root.addWidget(remove)

        if data is bookmarks:
            self.setWindowTitle("Manage Bookmarks")
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Name", "Url"])
            root.addWidget(add)
        elif data is history:
            self.setWindowTitle("Manage History")
            self.table.setColumnCount(2)
            self.table.setHorizontalHeaderLabels(["Title", "Url"])
            root.addWidget(clear)
        elif data is permissions:
            self.setWindowTitle("Manage Permission")
            self.table.setColumnCount(3)
            self.table.setHorizontalHeaderLabels(["Origin", "Permission", "State"])
            self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            root.addWidget(clear)

        self.table.horizontalHeader().setMaximumSectionSize(200)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        [self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value)) for row, value in enumerate(data) for col, value in enumerate(value)]
        self.setLayout(root)
        self.show()

    def refresh(self):
        self.table.setRowCount(len(self.data))
        [self.table.setItem(row, col, QtWidgets.QTableWidgetItem(value)) for row, value in enumerate(self.data) for col, value in enumerate(value)]

    def double_clicked(self):
        self.destroy()
        if self.data is permissions:
            self.from_window.new_tab(self.table.item(self.table.currentRow(), 0).text())
        else:
            self.from_window.new_tab(self.table.item(self.table.currentRow(), 1).text())

    def add_bookmark(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Bookmark Name", "Name:")
        if not name or not ok:
            return

        url, ok = QtWidgets.QInputDialog.getText(self, "Bookmark Link", "Url:") if ok else None
        if not url and not ok:
            return

        self.data.append([name, url])
        write(bookmarks)

    def remove_selected(self):
        row = self.table.currentRow()
        if row == -1:
            return
        self.table.removeRow(row)
        del self.data[row]
        write(self.data)
        if self.data is permissions: self.from_window.profile.listAllPermissions()[row].reset()

    def clear_all(self):
        self.table.setRowCount(0)
        self.data.clear()
        write(self.data)
        if self.data is permissions: [p.reset() for p in self.from_window.profile.listAllPermissions()]


class WebEnginePage(QtWebEngineCore.QWebEnginePage):
    def __init__(self, window, *args):
        super().__init__(*args)

        self.from_window = window
        self.permissionRequested.connect(self.permission_requested)

    def createWindow(self, _type):
        page = WebEnginePage(self, self.from_window)
        page.urlChanged.connect(lambda url: self.from_window.new_tab(url))
        return page
    
    def permission_requested(self, permission: QtWebEngineCore.QWebEnginePermission):
        clicked = QtWidgets.QMessageBox.question(
            self.from_window,
            f"{permission.permissionType().name} Requested - {self.title()}",
            f"Do you want to allow {permission.permissionType().name} for {permission.origin().toString()}?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        permission.grant() if clicked == QtWidgets.QMessageBox.StandardButton.Yes else permission.deny()
        permissions.append([permission.origin().toString(), permission.permissionType().name, permission.state().name])
        write(permissions)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, url=None):
        super().__init__()

        # Set Window Characteristics
        self.setMinimumSize(QtCore.QSize(900, 600))
        self.setWindowIcon(QtGui.QIcon(WEBX))
        self.setWindowTitle("WebX")

        # Browser Profile
        self.profile = QtWebEngineCore.QWebEngineProfile('WebX')
        self.profile.downloadRequested.connect(self.download_file)
        self.profile.setPersistentCookiesPolicy(QtWebEngineCore.QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setPersistentStoragePath(DATA)

        # Tabs
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.currentChanged.connect(lambda: self.update_url_bar(self.tabs.currentWidget().url(), self.tabs.currentWidget()))
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self.maximize)
        self.setCentralWidget(self.tabs)

        # New Tab Button
        self.new_tab_button = QtWidgets.QPushButton()
        self.new_tab_button.setIcon(QtGui.QIcon(os.path.join(ICONS, 'new_tab.png')))
        self.new_tab_button.setIconSize(QtCore.QSize(18, 18))
        self.new_tab_button.setFixedSize(20, 20)
        self.new_tab_button.pressed.connect(self.new_tab)
        self.new_tab_button.setShortcut('Ctrl+T')
        self.tabs.setCornerWidget(self.new_tab_button)

        # Toolbar
        self.navbar = QtWidgets.QToolBar()
        self.navbar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)
        self.navbar.setMovable(False)
        self.navbar.setIconSize(QtCore.QSize(20, 20))

        # Back Button
        back_button = QtGui.QAction(QtGui.QIcon(os.path.join(ICONS, 'back.png')), "Back", self)
        back_button.triggered.connect(lambda: self.tabs.currentWidget().back())

        # Forward Button
        forward_button = QtGui.QAction(QtGui.QIcon(os.path.join(ICONS, 'forward.png')), "Forward", self)
        forward_button.triggered.connect(lambda: self.tabs.currentWidget().forward())

        # Reload Button
        reload_button = QtGui.QAction(QtGui.QIcon(os.path.join(ICONS, 'reload.png')), "Reload", self)
        reload_button.triggered.connect(lambda: self.tabs.currentWidget().reload())

        # Address Bar
        self.url_bar = QtWidgets.QLineEdit()
        self.url_bar.setPlaceholderText("Type a url or Search")
        self.url_bar.returnPressed.connect(self.navigate_to_url)
        self.url_bar.mouseDoubleClickEvent = lambda e: self.url_bar.selectAll()

        # Add buttons to toolbar
        self.navbar.addAction(back_button)
        self.navbar.addAction(forward_button)
        self.navbar.addAction(reload_button)
        self.navbar.addSeparator()
        self.navbar.addWidget(self.url_bar)

        # Menu Bar
        self.menubar = self.menuBar()
        self.menubar.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.PreventContextMenu)

        # Add menus to menu bar
        self.file_menu = self.menubar.addMenu('&File')
        self.bookmarks_menu = self.menubar.addMenu('&Bookmarks')
        self.history_menu = self.menubar.addMenu('&History')
        self.help_menu = self.menubar.addMenu('&Help')

        # Open File
        open_file = QtGui.QAction("&Open File", self)
        open_file.setShortcut('Ctrl+O')
        open_file.triggered.connect(self.open_file)

        # New Window
        new = QtGui.QAction('&New Window', self)
        new.setShortcut('Ctrl+Shift+N')
        new.triggered.connect(MainWindow)

        # Exit App
        exit_app = QtGui.QAction('&Exit', self)
        exit_app.setShortcut('Ctrl+Shift+Q')
        exit_app.triggered.connect(self.close)

        # Manage Permissions
        manage_permissions = QtGui.QAction('&Manage Permissions', self)
        manage_permissions.triggered.connect(lambda: self.table_window(permissions))

        # Cookies
        remove_cookies = QtGui.QAction('&Clear Cookies', self)
        remove_cookies.triggered.connect(lambda: self.profile.cookieStore().deleteAllCookies())

        # Check for updates
        check_updates = QtGui.QAction('&Check for Updates', self)
        check_updates.setShortcut('Ctrl+Shift+U')
        check_updates.triggered.connect(self.check_updates)

        # About App
        about_app = QtGui.QAction('&About WebX', self)
        about_app.setShortcut('F1')
        about_app.triggered.connect(self.about)

        # Add actions to file menu
        self.file_menu.addAction(open_file)
        self.file_menu.addAction(new)
        self.file_menu.addSeparator()
        self.file_menu.addAction(exit_app)

        # Add actions to help menu
        self.help_menu.addAction(manage_permissions)
        self.help_menu.addAction(remove_cookies)
        self.help_menu.addSeparator()
        self.help_menu.addAction(check_updates)
        self.help_menu.addAction(about_app)

        # Add actions to bookmarks and history menu
        self.update_menu_items(bookmarks)
        self.update_menu_items(history)

        # Finalizing window
        self.addToolBar(self.navbar)
        self.new_tab(url)
        self.show()

    def new_tab(self, url=None):
        browser = QtWebEngineWidgets.QWebEngineView()
        idx = self.tabs.addTab(browser, "New Tab")
        qurl = QtCore.QUrl(url)
        self.tabs.setTabText(idx, url)

        browser.setPage(WebEnginePage(self, self.profile, browser))
        browser.urlChanged.connect(lambda qurl, b=browser: self.update_url_bar(qurl, b))
        browser.loadFinished.connect(lambda _, i=idx, b=browser:self.load_finished(i, b))
        browser.page().fullScreenRequested.connect(self.handle_fullscreen)
        browser.page().iconChanged.connect(lambda icon, i=idx: self.tabs.setTabIcon(i, icon))
        self.tabs.setCurrentIndex(idx)

        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.ScrollAnimatorEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.HyperlinkAuditingEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.FocusOnNavigationEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.JavascriptCanPaste, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.ScreenCaptureEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.DnsPrefetchEnabled, True)
        browser.settings().setAttribute(QtWebEngineCore.QWebEngineSettings.WebAttribute.BackForwardCacheEnabled, True)

        browser.setUrl(qurl.setScheme(qurl.scheme() or 'http') if url else QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'home.html')))

    def close_tab(self, i):
        if self.tabs.count() == 1:
            self.tabs.currentWidget().setUrl(QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'home.html')))
        else:
            self.tabs.removeTab(i)

    def navigate_to_url(self):
        url = self.url_bar.text()
        self.tabs.setTabText(self.tabs.currentIndex(), url)

        # Check if user is trying to search
        if ' ' in url or not any(i in url for i in ['.', ':']):
            url = f"https://www.google.com/search?q={url}"

        match url.replace('://', ':'):
            case "chrome:dino": url = QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'snake.html')).toString()
            case "webx:snake": url = QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'snake.html')).toString()
            case "webx:home": url = QtCore.QUrl.fromLocalFile(os.path.join(HTML, 'home.html')).toString()

        if QtCore.QUrl(url).scheme() == 'webx': url = 'chrome'+url.removeprefix('webx')
        if not QtCore.QUrl(url).scheme(): url = 'http:'+url

        # Set Url
        self.tabs.currentWidget().setUrl(QtCore.QUrl(url))
        self.update_url_bar(QtCore.QUrl(url), self.tabs.currentWidget())

    def update_url_bar(self, qurl, browser):
        url = qurl.toString()
        if QtCore.QUrl(url).scheme() == 'chrome': url = 'webx'+url.removeprefix('chrome')
        if browser != self.tabs.currentWidget(): return
        self.url_bar.setText(BUILTIN_PATHS.get(qurl, url))

    def load_finished(self, i, browser):
        title = browser.page().title()
        qurl = browser.url()
        # Set tab Text
        self.tabs.setTabText(i, title)

        # Add to history
        if qurl in BUILTIN_PATHS or qurl.scheme() in ('chrome', 'view-source') or not is_connected(): return
        history.insert(0, [title, qurl.toString()])
        if len(history) > 100: history.pop()
        write(history)

    def open_file(self):
        ext_filter = "HTML Files (*.htm *.html *.xhtml) ;; PDF Files (*.pdf) ;; All Files (*)"
        filepath = QtWidgets.QFileDialog.getOpenFileUrl(self, "Open File", os.path.expanduser('~'), ext_filter)[0].toString()
        if filepath: self.new_tab(filepath)
    
    @staticmethod
    def about():
        about_window = QtWidgets.QMessageBox()
        about_window.setWindowTitle("About WebX")
        about_window.setText('\n'.join([
            f"WebX Version {VERSION}",
            "",
            "© Orlando Huang. All rights reserved.",
        ]))
        about_window.setIcon(QtWidgets.QMessageBox.Icon.Information)
        about_window.setWindowIcon(QtGui.QIcon(WEBX))
        about_window.exec()

    def bookmark_current(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Bookmark Name", "Name:")
        if name and ok:
            bookmarks.append([name, self.tabs.currentWidget().url().toString()])
            write(bookmarks)

    def update_menu_items(self, data):
        menu = self.bookmarks_menu if data is bookmarks else self.history_menu
        menu.clear()
        if data is bookmarks:
            for name, url in bookmarks:
                action = QtGui.QAction(name, self)
                action.triggered.connect(lambda _, u=url: self.new_tab(u))
                menu.addAction(action)
        elif data is history:
            for i, (title, url) in enumerate(history):
                if i < 10:
                    action = QtGui.QAction(title, self)
                    action.triggered.connect(lambda _, u=url: self.new_tab(u))
                    menu.addAction(action)
                else:
                    break
        menu.addSeparator()
        add_current = QtGui.QAction("Bookmark Current Site", self)
        view = QtGui.QAction(f"Manage {'Bookmarks' if data is bookmarks else 'History'}", self)
        add_current.triggered.connect(self.bookmark_current)
        view.triggered.connect(lambda: self.table_window(data))
        if data is bookmarks: menu.addAction(add_current)
        menu.addAction(view)

    def table_window(self, data):
        global bookmarks_window, history_window, permissions_window
        if data is bookmarks:
            if bookmarks_window:
                bookmarks_window.show()
                bookmarks_window.activateWindow()
            else:
                bookmarks_window = TableWindow(bookmarks, self)
        elif data is history:
            if history_window:
                history_window.show()
                history_window.activateWindow()
            else:
                history_window = TableWindow(history, self)
        elif data is permissions:
            if permissions_window:
                permissions_window.show()
                permissions_window.activateWindow()
            else:
                permissions_window = TableWindow(permissions, self)

    def check_updates(self):
        self.check_updates_window = CheckUpdateWindow()

    def maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def handle_fullscreen(self, request):
        request.accept()
        maximized = True if self.isMaximized() else False
        if request.toggleOn():
            self.showFullScreen()
            self.menubar.hide()
            self.navbar.hide()
            self.tabs.tabBar().hide()
        else:
            self.menubar.show()
            self.navbar.show()
            self.tabs.tabBar().show()
            self.showMaximized() if maximized else self.showNormal()

    @staticmethod
    def download_file(item: QtWebEngineCore.QWebEngineDownloadRequest):
        def create_download_window():
            download_window = DownloadWindow(name, size)
            item.receivedBytesChanged.connect(lambda: download_window.update_size(item.receivedBytes()))
            item.isFinishedChanged.connect(lambda: download_window.set_done())

        name = item.suggestedFileName()
        size = item.totalBytes()
        dialog = QtWidgets.QMessageBox()
        dialog.setIcon(QtWidgets.QMessageBox.Icon.Question)
        dialog.setWindowIcon(QtGui.QIcon(WEBX))
        dialog.setWindowTitle(f"Download File: {name}")
        dialog.setText(f"What would you like to do with {name} (Size: {byte_to_string(size)})")

        dialog.addButton("Save", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Save As", QtWidgets.QMessageBox.ButtonRole.ActionRole)
        dialog.addButton("Cancel", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        dialog.exec()

        match dialog.clickedButton().text():
            case "Save":
                item.accept()
                create_download_window()
            case "Save As":
                folder = QtWidgets.QFileDialog.getExistingDirectory(dialog, "Save To", item.downloadDirectory())
                if folder:
                    item.setDownloadDirectory(folder)
                    item.accept()
                    create_download_window()


# Create Argument Parser
parser = argparse.ArgumentParser(
    description="WebX Browser",
    epilog="Only takes one argument."
)

# Process Arguments
if len(sys.argv) > 2: sys.exit("\033[31mERROR: Only takes one argument!\033[0m")
parser.add_argument('-v', '--version', action='store_true', help="show version")
parser.add_argument('url', nargs=argparse.OPTIONAL, help="url of first tab")
args = parser.parse_args()
if args.version: print(f"WebX {VERSION}"); sys.exit()

try:
    lock_file = open(os.path.join(DATA, 'webx.lock'), 'w')
    portalocker.lock(lock_file, portalocker.LOCK_EX | portalocker.LOCK_NB)
except portalocker.exceptions.LockException:
    open(os.path.join(DATA, 'status'), 'w').write(f'newwindow {args.url or ''}')
    sys.exit()

observer = Observer()
signals = Signals()

observer.schedule(StatusFileHandler(), path=DATA, recursive=False)
observer.start()

signals.create_window.connect(lambda url: MainWindow(url))

# Run App
app.setApplicationName("WebX")
app.setWindowIcon(QtGui.QIcon(os.path.join(ICONS, 'webx.py')))
MainWindow(args.url)
app.exec()

lock_file.close()
os.remove(os.path.join(DATA, 'webx.lock'))