# nuitka-project: --quiet
# nuitka-project: --standalone
# nuitka-project: --enable-plugin=tk-inter
# nuitka-project: --lto=yes
# nuitka-project: --clang
# nuitka-project: --assume-yes-for-downloads
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --windows-icon-from-ico=src/icons/WebX.ico


import os
import tempfile
import requests
import subprocess
import tkinter as tk
from threading import Thread


LATEST = "https://raw.githubusercontent.com/not-immortalcoding/webx/refs/heads/main/latest_version.txt"
    

def byte_to_string(byte):
    match byte:
        case b if b == 0: return "?"
        case b if b < 1024: return f"{byte} B"
        case b if b < 1024 ** 2: return f"{byte / 1024:.2f} KB"
        case b if b < 1024 ** 3: return f"{byte / (1024 ** 2):.2f} MB"
        case _: return f"{byte / (1024 ** 3):.2f} GB"


def download():
    upgrade_url = f"https://github.com/Orlando-Huang/webx/releases/download/v{requests.get(LATEST).text}/WebX Installer.exe"
    with requests.get(upgrade_url, stream=True) as r:
        r.raise_for_status()
        total_size = int(r.headers.get("Content-Length", 0))
        downloaded = 0
        with tempfile.TemporaryDirectory() as temp:
            webx_upgrade = os.path.join(temp, 'webx_upgrade.exe')
            with open(webx_upgrade, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        label.config(text=f'WebX Upgrade downloaded {byte_to_string(downloaded)}/{byte_to_string(total_size)}')
                label.config(text="WebX Upgrade download finished!")
            root.destroy()
            subprocess.run([webx_upgrade])


root = tk.Tk(className="WebX Upgrade")
root.title("WebX Upgrade")
root.iconphoto(False, tk.PhotoImage(file=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'icons', 'WebX.png')))
label = tk.Label(root, text="Starting WebX Upgrade download...")
label.pack()
root.protocol("WM_DELETE_WINDOW", lambda: None)
root.resizable(False, False)

Thread(target=download, daemon=True).start()
root.mainloop()