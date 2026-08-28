"""
Automated Standalone Binary Build Script for Python CAD Pro.
Validates dependencies and executes PyInstaller with cad_pro.spec.
"""

import sys
import subprocess
import os

def build_standalone():
    print("=" * 60)
    print("  PYTHON CAD PRO — STANDALONE PACKAGING SUITE")
    print("=" * 60)

    # 1. Check PyInstaller availability
    try:
        import PyInstaller
        print(f"[OK] PyInstaller detected (version {PyInstaller.__version__})")
    except ImportError:
        print("[!] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 2. Check OpenCASCADE (OCP)
    try:
        import OCP
        print("[OK] OpenCASCADE C++ library bindings (OCP) verified.")
    except ImportError:
        print("[WARN] OCP library not found in python environment.")

    # 3. Execute PyInstaller build
    print("[*] Running PyInstaller build with cad_pro.spec...")
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "cad_pro.spec"]
    res = subprocess.run(cmd)

    if res.returncode == 0:
        print("\n" + "=" * 60)
        print("  [SUCCESS] Standalone bundle created in: dist/PythonCADPro/")
        print("=" * 60)
    else:
        print(f"\n[ERROR] PyInstaller failed with exit code {res.returncode}")

if __name__ == "__main__":
    build_standalone()
