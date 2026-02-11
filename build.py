"""Build DiskPilot.exe using PyInstaller."""
import subprocess
import sys
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--windowed",
    "--name", "DiskPilot",
    "--icon", os.path.join(ROOT, "diskpilot.ico"),
    "--add-data", f"{os.path.join(ROOT, 'diskpilot.ico')};.",
    "--hidden-import", "customtkinter",
    "--collect-all", "customtkinter",
    "--noconfirm",
    "--clean",
    os.path.join(ROOT, "app.py"),
]

print("Building DiskPilot.exe...")
print(f"Command: {' '.join(cmd)}")
subprocess.run(cmd, cwd=ROOT)
print("\nDone! Check dist/DiskPilot.exe")
