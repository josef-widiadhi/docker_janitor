"""
build_exe.py — Build docker_janitor_gui.py into a standalone Windows EXE
using PyInstaller.

Usage:
    python build_exe.py
    python build_exe.py --onefile      (single EXE, slower to start)
    python build_exe.py --debug        (keep console window for debugging)
    python build_exe.py --clean        (delete build/ and dist/ first)

Requirements:
    pip install pyinstaller
"""

import os
import sys
import shutil
import subprocess
import argparse


SCRIPT      = "docker_janitor_gui.py"
APP_NAME    = "DockerJanitorPro"
ICON_FILE   = "icon.ico"          # optional — place icon.ico next to this script
DIST_DIR    = "dist"
BUILD_DIR   = "build"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--onefile", action="store_true",
                    help="Bundle into a single EXE (slower startup, easier to share)")
    ap.add_argument("--debug",   action="store_true",
                    help="Keep console window (useful for debugging)")
    ap.add_argument("--clean",   action="store_true",
                    help="Delete dist/ and build/ before building")
    args = ap.parse_args()

    # ── sanity checks ────────────────────────────────────────────────────────
    if not os.path.exists(SCRIPT):
        print(f"❌  {SCRIPT} not found. Run this script from the same folder.")
        sys.exit(1)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("❌  PyInstaller not installed.\n   Run: pip install pyinstaller")
        sys.exit(1)

    # ── clean ─────────────────────────────────────────────────────────────────
    if args.clean:
        for d in (DIST_DIR, BUILD_DIR):
            if os.path.isdir(d):
                print(f"   Removing {d}/…")
                shutil.rmtree(d)

    # ── build command ─────────────────────────────────────────────────────────
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name",       APP_NAME,
        "--distpath",   DIST_DIR,
        "--workpath",   BUILD_DIR,
        "--noconfirm",
    ]

    if args.onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")          # default: faster launch, folder output

    if not args.debug:
        cmd.append("--noconsole")       # hide black console window
    else:
        cmd.append("--console")

    if os.path.exists(ICON_FILE):
        cmd += ["--icon", ICON_FILE]
        print(f"   Using icon: {ICON_FILE}")
    else:
        print(f"   (No {ICON_FILE} found — building without custom icon)")

    # Hidden imports tkinter needs on some systems
    cmd += [
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.filedialog",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "tkinter.scrolledtext",
    ]

    cmd.append(SCRIPT)

    # ── run ───────────────────────────────────────────────────────────────────
    print("\n🔨 Building EXE…")
    print("   " + " ".join(cmd) + "\n")

    result = subprocess.run(cmd)

    if result.returncode != 0:
        print("\n❌  Build failed. Check output above.")
        sys.exit(1)

    # ── report ────────────────────────────────────────────────────────────────
    if args.onefile:
        exe = os.path.join(DIST_DIR, APP_NAME + ".exe")
    else:
        exe = os.path.join(DIST_DIR, APP_NAME, APP_NAME + ".exe")

    if os.path.exists(exe):
        size = os.path.getsize(exe) / (1024 * 1024)
        print(f"\n✅  Build complete!")
        print(f"   EXE : {exe}")
        print(f"   Size: {size:.1f} MB")
        if not args.onefile:
            print(f"   Note: Distribute the entire {DIST_DIR}/{APP_NAME}/ folder.")
    else:
        print(f"\n⚠️  Build finished but EXE not found at expected path: {exe}")

    print("\n💡 To run as Administrator automatically:")
    print("   Right-click the EXE → Properties → Compatibility")
    print("   → Check 'Run this program as an administrator'")


if __name__ == "__main__":
    main()
