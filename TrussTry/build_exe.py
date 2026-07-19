"""
build_exe.py
============
Run this ONCE to package TrussTry into a standalone Windows .exe
with a double-click shortcut.

Usage (from inside the TrussTry folder):
    python build_exe.py

Output:
    dist/TrussTry/TrussTry.exe   <-- the packaged app
    dist/TrussTry/               <-- folder to share / zip up

Requirements:
    pip install pyinstaller
"""

import subprocess, sys, shutil
from pathlib import Path

HERE = Path(__file__).parent


def main():
    # ── 1. Make sure PyInstaller is available ─────────────────────
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    icon = str(HERE / "assets" / "icon.ico")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",               # one folder (faster startup than --onefile)
        "--windowed",             # no console window
        f"--icon={icon}",
        "--name=TrussTry",
        # Add the assets folder so the icon is bundled
        f"--add-data=assets{':' if sys.platform != 'win32' else ';'}assets",
        "main.py",
    ]

    print("Running PyInstaller...")
    subprocess.check_call(cmd, cwd=str(HERE))
    print("\nDone!  Your app is at:  dist/TrussTry/TrussTry.exe")
    print("Double-click that exe, or create a shortcut to it on your Desktop.")


if __name__ == "__main__":
    main()
