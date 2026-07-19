"""
create_shortcut.py
==================
Creates a Desktop shortcut that launches TrussTry directly from
its source folder (no need to build an EXE first).

Run this once:
    python create_shortcut.py

After running, a "TrussTry" icon appears on your Desktop.
Double-clicking it launches the app exactly like a real installed program.

Requires: pywin32   (pip install pywin32)
"""

import sys, subprocess
from pathlib import Path


def create_shortcut():
    try:
        import win32com.client
    except ImportError:
        print("Installing pywin32 (needed to create shortcuts)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32"])
        import win32com.client

    import winreg, os

    HERE       = Path(__file__).parent.resolve()
    python_exe = Path(sys.executable).resolve()
    # Switch python.exe → pythonw.exe (no console window)
    python_exe = python_exe.parent / "pythonw.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable).resolve()  # fallback
    main_py    = HERE / "main.py"
    icon_path  = HERE / "assets" / "icon.ico"

    # Desktop path (works for all Windows versions)
    desktop = Path.home() / "Desktop"
    if not desktop.exists():
        # Try the shell folder registry key
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
            desktop = Path(winreg.QueryValueEx(key, "Desktop")[0])

    shortcut_path = desktop / "TrussTry.lnk"

    shell    = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath      = str(python_exe)
    shortcut.Arguments       = f'"{main_py}"'
    shortcut.WorkingDirectory= str(HERE)
    shortcut.Description     = "TrussTry – 2D Truss FEA"
    if icon_path.exists():
        shortcut.IconLocation = str(icon_path)
    shortcut.save()

    print(f"Shortcut created: {shortcut_path}")
    print("You can now double-click 'TrussTry' on your Desktop to launch the app!")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("This script is for Windows only.")
        sys.exit(1)
    create_shortcut()
