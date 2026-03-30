"""
Docker Janitor Pro - Simple GUI Launcher
A clean, simple interface to run the Docker VHDX cleaner.

Usage:
    python docker_janitor_gui.py
    python docker_janitor_gui.py --cli          (CLI mode, no GUI)
    python docker_janitor_gui.py --cli --nuke   (CLI full nuclear, no GUI)

Requirements:
    pip install pyinstaller   (only if building .exe)
"""

import os
import sys
import subprocess
import threading
import time
import tempfile
import ctypes
from pathlib import Path
from datetime import datetime

try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext
    HAS_TK = True
except ImportError:
    HAS_TK = False

# ─────────────────────────────────────────────────────────────────────────────
#  COLOURS & FONTS  (terminal-green-on-black — industrial hacker aesthetic)
# ─────────────────────────────────────────────────────────────────────────────
BG        = "#0a0c10"
PANEL     = "#111318"
CARD      = "#181c24"
GREEN     = "#00e676"
GREEN_DIM = "#1b5e38"
RED       = "#ff3d5a"
YELLOW    = "#ffd740"
MUTED     = "#4a5568"
TEXT      = "#cdd6f4"
BORDER    = "#1e2535"

F_MONO  = ("Cascadia Code", 9) if sys.platform == "win32" else ("Courier New", 9)
F_BODY  = ("Segoe UI",      10) if sys.platform == "win32" else ("Helvetica", 10)
F_TITLE = ("Segoe UI Black",13) if sys.platform == "win32" else ("Helvetica", 13)
F_GIANT = ("Segoe UI Black",22) if sys.platform == "win32" else ("Helvetica", 22)

DEFAULT_VHDX = r"D:\docker_images\DockerDesktopWSL\disk\docker_data.vhdx"


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd, timeout=600, shell=False, input_data=None):
    """Run command → (ok:bool, output:str)"""
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            shell=shell, timeout=timeout, input=input_data
        )
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "Timed out."
    except Exception as e:
        return False, str(e)


def _fmt_bytes(b: int) -> str:
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if abs(b) < 1024.0:
            return f"{b:.1f} {u}"
        b /= 1024.0
    return f"{b:.1f} PB"


def _vhdx_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate():
    """Re-launch as Administrator."""
    try:
        if not _is_admin():
            script = os.path.abspath(sys.argv[0])
            args   = " ".join(f'"{a}"' for a in sys.argv[1:])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {args}', None, 1
            )
            sys.exit(0)
    except Exception:
        pass


def _ts():
    return datetime.now().strftime("%H:%M:%S")


# ─────────────────────────────────────────────────────────────────────────────
#  CORE OPERATIONS  (pure functions, called from GUI *or* CLI)
# ─────────────────────────────────────────────────────────────────────────────

def op_docker_prune(log):
    log("── Docker: system prune -a --volumes ──")
    ok, out = _run(["docker", "system", "prune", "-f", "-a", "--volumes"], timeout=300)
    log(out[:600] if out.strip() else "(no output)")
    log("── Docker: buildx prune ──")
    _run(["docker", "buildx", "prune", "-f", "-a"], timeout=180)
    return ok


def op_stop_docker(log):
    log("── Stopping Docker Desktop… ──")
    _run(["taskkill", "/F", "/IM", "Docker Desktop.exe"], timeout=20)
    time.sleep(3)
    log("── WSL shutdown… ──")
    _run(["wsl", "--shutdown"], timeout=60)
    _run(["wsl", "-t", "docker-desktop"],      timeout=15)
    _run(["wsl", "-t", "docker-desktop-data"], timeout=15)
    time.sleep(3)
    log("   Docker + WSL stopped.")


def op_fstrim(log):
    log("── fstrim inside docker-desktop-data… ──")
    # wake the distro first
    _run(["wsl", "-d", "docker-desktop-data", "-e", "echo", "wake"], timeout=30)
    ok, out = _run(
        ["wsl", "-d", "docker-desktop-data", "-e", "fstrim", "-av"],
        timeout=120
    )
    log(out[:400] if out.strip() else "(no output)")
    if not ok:
        log("   Trying default WSL distro…")
        ok, out = _run(["wsl", "-e", "fstrim", "-av"], timeout=120)
        log(out[:400])
    _run(["wsl", "--shutdown"], timeout=60)
    time.sleep(2)
    return ok


def op_zerofill(log):
    log("── Zero-fill free space (dd — this is slow) ──")
    script = (
        "dd if=/dev/zero of=/tmp/_z.tmp bs=4M 2>/dev/null; "
        "sync; rm -f /tmp/_z.tmp; echo done"
    )
    _run(["wsl", "-d", "docker-desktop-data", "-e", "echo", "wake"], timeout=30)
    ok, out = _run(
        ["wsl", "-d", "docker-desktop-data", "-e", "bash", "-c", script],
        timeout=900
    )
    log(out[:300] if out.strip() else "(no output)")
    _run(["wsl", "--shutdown"], timeout=60)
    time.sleep(2)
    return ok


def op_optimize_vhd(log, vhdx_path):
    log(f"── Optimize-VHD -Mode Full ──")
    ps  = f'Optimize-VHD -Path "{vhdx_path}" -Mode Full'
    ok, out = _run(["powershell", "-Command", ps], timeout=600)
    log(out[:400] if out.strip() else "(no output)")
    log("   ✅ Optimize-VHD done." if ok else "   ⚠️  Optimize-VHD failed (sparse VHDX?).")
    return ok


def op_diskpart(log, vhdx_path):
    log("── diskpart compact vdisk ──")
    script = (
        f'select vdisk file="{vhdx_path}"\n'
        "attach vdisk readonly\n"
        "compact vdisk\n"
        "detach vdisk\n"
        "exit\n"
    )
    tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    tmp.write(script)
    tmp.close()
    ok, out = _run(["diskpart", "/s", tmp.name], timeout=600)
    os.unlink(tmp.name)
    log(out[:400] if out.strip() else "(no output)")
    log("   ✅ diskpart done." if ok else "   ⚠️  diskpart failed.")
    return ok


def op_restart_docker(log):
    docker_exe = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) \
                 / "Docker/Docker/Docker Desktop.exe"
    if docker_exe.exists():
        log("── Restarting Docker Desktop… ──")
        subprocess.Popen([str(docker_exe)])
    else:
        log("   Docker Desktop.exe not found — start manually.")


def run_nuclear(vhdx_path, opts: dict, log) -> dict:
    """
    opts keys: prune, fstrim, zerofill, optimize, diskpart, restart
    Returns result dict with before/after sizes.
    """
    before = _vhdx_size(vhdx_path)
    log(f"[{_ts()}] ═══════════════════════════════════════")
    log(f"[{_ts()}] ☢️  NUCLEAR SEQUENCE START")
    log(f"[{_ts()}] VHDX before: {_fmt_bytes(before)}")
    log(f"[{_ts()}] ═══════════════════════════════════════")

    def _step(name, fn, *a, **kw):
        log(f"\n[{_ts()}] ▶ {name}")
        return fn(log, *a, **kw)

    if opts.get("prune"):
        _step("Docker Prune", op_docker_prune)

    _step("Stop Docker + WSL", op_stop_docker)

    if opts.get("fstrim"):
        _step("fstrim", op_fstrim)

    if opts.get("zerofill"):
        _step("Zero-fill", op_zerofill)

    if opts.get("optimize"):
        _step("Optimize-VHD", op_optimize_vhd, vhdx_path)

    if opts.get("diskpart"):
        _step("diskpart compact", op_diskpart, vhdx_path)

    if opts.get("restart"):
        _step("Restart Docker", op_restart_docker)

    after = _vhdx_size(vhdx_path)
    saved = max(0, before - after)

    log(f"\n[{_ts()}] ═══════════════════════════════════════")
    log(f"[{_ts()}] ✅ DONE")
    log(f"[{_ts()}]    Before : {_fmt_bytes(before)}")
    log(f"[{_ts()}]    After  : {_fmt_bytes(after)}")
    log(f"[{_ts()}]    Saved  : {_fmt_bytes(saved)} ({saved/max(1,before)*100:.1f}%)")
    log(f"[{_ts()}] ═══════════════════════════════════════")

    return {
        "before": _fmt_bytes(before),
        "after":  _fmt_bytes(after),
        "saved":  _fmt_bytes(saved),
        "pct":    f"{saved/max(1,before)*100:.1f}%",
    }


# ─────────────────────────────────────────────────────────────────────────────
#  CLI MODE
# ─────────────────────────────────────────────────────────────────────────────

def run_cli():
    import argparse
    p = argparse.ArgumentParser(
        description="Docker Janitor Pro — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full nuclear (default options, interactive confirm)
  python docker_janitor_gui.py --cli --nuke

  # Custom VHDX path, skip prune, skip restart
  python docker_janitor_gui.py --cli --nuke --vhdx "E:\\data\\docker_data.vhdx" --no-prune --no-restart

  # Just docker prune, no VHDX compaction
  python docker_janitor_gui.py --cli --prune-only

  # Show VHDX size
  python docker_janitor_gui.py --cli --size
"""
    )
    p.add_argument("--cli",        action="store_true", help="Run in CLI mode (required for all below)")
    p.add_argument("--nuke",       action="store_true", help="Run full nuclear sequence")
    p.add_argument("--prune-only", action="store_true", help="Only run docker prune, skip VHDX")
    p.add_argument("--size",       action="store_true", help="Print VHDX size and exit")
    p.add_argument("--vhdx",       default=DEFAULT_VHDX, help="Path to docker_data.vhdx")
    p.add_argument("--no-prune",   action="store_true", help="Skip docker prune step")
    p.add_argument("--no-fstrim",  action="store_true", help="Skip fstrim step")
    p.add_argument("--zerofill",   action="store_true", help="Enable zerofill (slow but thorough)")
    p.add_argument("--no-optimize",action="store_true", help="Skip Optimize-VHD")
    p.add_argument("--no-diskpart",action="store_true", help="Skip diskpart compact")
    p.add_argument("--no-restart", action="store_true", help="Don't restart Docker when done")
    p.add_argument("--yes",        action="store_true", help="Skip confirmation prompts")

    args = p.parse_args()

    def log(msg): print(msg)

    if args.size:
        sz = _vhdx_size(args.vhdx)
        print(f"VHDX: {args.vhdx}")
        print(f"Size: {_fmt_bytes(sz)}")
        return

    if args.prune_only:
        print("Running docker prune only…")
        op_docker_prune(log)
        return

    if args.nuke:
        if not args.yes:
            print(f"\n⚠️  About to run NUCLEAR sequence on:\n   {args.vhdx}")
            print("This will STOP Docker Desktop and WSL.")
            yn = input("Proceed? [y/N]: ").strip().lower()
            if yn != "y":
                print("Aborted.")
                return

        opts = {
            "prune":    not args.no_prune,
            "fstrim":   not args.no_fstrim,
            "zerofill": args.zerofill,
            "optimize": not args.no_optimize,
            "diskpart": not args.no_diskpart,
            "restart":  not args.no_restart,
        }
        run_nuclear(args.vhdx, opts, log)
        return

    print("No action specified. Use --nuke, --prune-only, or --size.")
    print("Run with --help for full usage.")


# ─────────────────────────────────────────────────────────────────────────────
#  GUI MODE
# ─────────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Docker Janitor Pro")
        self.geometry("860x640")
        self.minsize(720, 520)
        self.configure(bg=BG)
        self.resizable(True, True)
        self._busy = False

        self._vhdx   = tk.StringVar(value=DEFAULT_VHDX)
        self._prune  = tk.BooleanVar(value=True)
        self._fstrim = tk.BooleanVar(value=True)
        self._zero   = tk.BooleanVar(value=False)
        self._opt    = tk.BooleanVar(value=True)
        self._disk   = tk.BooleanVar(value=True)
        self._restart= tk.BooleanVar(value=True)

        self._build()
        self.after(200, self._check_admin_badge)
        self.after(600, self._auto_size)

    # ── LAYOUT ────────────────────────────────────────────────────────────

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=BG, pady=10)
        hdr.pack(fill="x", padx=18)

        tk.Label(hdr, text="🐳 Docker Janitor Pro",
                 font=F_GIANT, bg=BG, fg=GREEN).pack(side="left")
        self._admin_lbl = tk.Label(hdr, text="", font=F_BODY, bg=BG, fg=YELLOW)
        self._admin_lbl.pack(side="right", padx=8)

        # Thin green rule
        tk.Frame(self, bg=GREEN_DIM, height=1).pack(fill="x", padx=18)

        # VHDX path row
        prow = tk.Frame(self, bg=PANEL, pady=8, padx=14)
        prow.pack(fill="x", padx=18, pady=(8, 0))
        tk.Label(prow, text="VHDX Path", font=F_BODY, bg=PANEL, fg=MUTED, width=10, anchor="w").pack(side="left")
        tk.Entry(prow, textvariable=self._vhdx, font=F_MONO,
                 bg=CARD, fg=TEXT, insertbackground=GREEN,
                 relief="flat", bd=0).pack(side="left", fill="x", expand=True, padx=6)
        self._btn(prow, "Browse", self._browse, small=True).pack(side="left", padx=2)
        self._size_var = tk.StringVar(value="—")
        tk.Label(prow, textvariable=self._size_var, font=F_BODY, bg=PANEL, fg=GREEN, width=12).pack(side="left", padx=(8,0))

        # Main body: options left, log right
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=10)

        # ── OPTIONS PANEL ──
        opts = tk.Frame(body, bg=PANEL, padx=14, pady=12, width=260)
        opts.pack(side="left", fill="y", padx=(0, 10))
        opts.pack_propagate(False)

        tk.Label(opts, text="SEQUENCE OPTIONS", font=("Segoe UI Black", 9),
                 bg=PANEL, fg=MUTED).pack(anchor="w", pady=(0, 8))

        steps = [
            (self._prune,  "🧹  Docker prune -a --volumes"),
            (self._fstrim, "✂️   fstrim  (mark free blocks)"),
            (self._zero,   "🕳   Zero-fill  (slow, thorough)"),
            (self._opt,    "💿  Optimize-VHD  (PowerShell)"),
            (self._disk,   "💾  diskpart  compact vdisk"),
            (self._restart,"🔄  Restart Docker when done"),
        ]
        for var, label in steps:
            self._chk(opts, var, label)

        tk.Frame(opts, bg=BORDER, height=1).pack(fill="x", pady=10)

        # size display card
        size_card = tk.Frame(opts, bg=CARD, padx=10, pady=8)
        size_card.pack(fill="x")
        tk.Label(size_card, text="Current VHDX Size", font=("Segoe UI", 8),
                 bg=CARD, fg=MUTED).pack()
        tk.Label(size_card, textvariable=self._size_var, font=("Segoe UI Black", 18),
                 bg=CARD, fg=GREEN).pack()
        self._btn(size_card, "↺  Refresh", self._auto_size, small=True).pack(pady=(4, 0))

        tk.Frame(opts, bg=BORDER, height=1).pack(fill="x", pady=10)

        # NUKE button
        nuke = tk.Button(
            opts, text="☢  NUKE IT",
            command=self._confirm_nuke,
            bg=RED, fg="white",
            activebackground="#cc1a2e", activeforeground="white",
            font=("Segoe UI Black", 13),
            relief="flat", cursor="hand2",
            padx=0, pady=12
        )
        nuke.pack(fill="x")

        tk.Frame(opts, bg=BORDER, height=1).pack(fill="x", pady=8)

        # Quick actions
        tk.Label(opts, text="QUICK ACTIONS", font=("Segoe UI Black", 9),
                 bg=PANEL, fg=MUTED).pack(anchor="w")
        self._btn(opts, "🧹  Prune only (fast)",  self._quick_prune, fill="x").pack(fill="x", pady=2)
        self._btn(opts, "📋  docker system df",   self._show_df,     fill="x").pack(fill="x", pady=2)
        self._btn(opts, "📦  List containers",    self._list_containers, fill="x").pack(fill="x", pady=2)

        # ── LOG PANEL ──
        log_frame = tk.Frame(body, bg=PANEL)
        log_frame.pack(side="left", fill="both", expand=True)

        log_hdr = tk.Frame(log_frame, bg=PANEL, pady=4, padx=8)
        log_hdr.pack(fill="x")
        tk.Label(log_hdr, text="OUTPUT LOG", font=("Segoe UI Black", 9),
                 bg=PANEL, fg=MUTED).pack(side="left")
        self._btn(log_hdr, "Clear", self._clear_log, small=True).pack(side="right")
        self._btn(log_hdr, "Save…", self._save_log,  small=True).pack(side="right", padx=4)

        self._log = scrolledtext.ScrolledText(
            log_frame, bg="#050810", fg=GREEN, font=F_MONO,
            relief="flat", bd=0, state="disabled",
            insertbackground=GREEN, wrap="word"
        )
        self._log.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Status bar
        sb = tk.Frame(self, bg=BORDER, height=24)
        sb.pack(fill="x")
        sb.pack_propagate(False)
        self._status = tk.StringVar(value="Ready — run as Administrator for best results.")
        tk.Label(sb, textvariable=self._status, font=("Segoe UI", 8),
                 bg=BORDER, fg=MUTED, anchor="w").pack(side="left", padx=10, fill="y")
        self._pb = ttk.Progressbar(sb, mode="indeterminate", length=160)
        self._pb.pack(side="right", padx=10, pady=3)

    # ── WIDGET FACTORIES ───────────────────────────────────────────────────

    def _btn(self, parent, text, cmd, small=False, fill=None):
        b = tk.Button(
            parent, text=text, command=cmd,
            bg=CARD, fg=GREEN, activebackground=BORDER, activeforeground=GREEN,
            relief="flat", font=("Segoe UI", 8 if small else 9),
            cursor="hand2", padx=6, pady=2,
            highlightthickness=1, highlightbackground=BORDER
        )
        return b

    def _chk(self, parent, var, text):
        tk.Checkbutton(
            parent, text=text, variable=var,
            bg=PANEL, fg=TEXT, selectcolor=CARD,
            activebackground=PANEL, activeforeground=GREEN,
            font=("Segoe UI", 9)
        ).pack(anchor="w", pady=2)

    # ── LOGGING ────────────────────────────────────────────────────────────

    def _write(self, msg: str):
        self._log.configure(state="normal")
        self._log.insert("end", msg + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._log.get("1.0", "end"))

    # ── HELPERS ────────────────────────────────────────────────────────────

    def _check_admin_badge(self):
        if _is_admin():
            self._admin_lbl.config(text="✅ Administrator", fg=GREEN)
        else:
            self._admin_lbl.config(text="⚠️ Not Admin — elevate for diskpart/VHD", fg=YELLOW)

    def _auto_size(self):
        def _w():
            sz = _vhdx_size(self._vhdx.get())
            txt = _fmt_bytes(sz) if sz else "Not found"
            self.after(0, lambda: self._size_var.set(txt))
        threading.Thread(target=_w, daemon=True).start()

    def _browse(self):
        p = filedialog.askopenfilename(
            title="Select docker_data.vhdx",
            filetypes=[("VHDX", "*.vhdx"), ("All", "*.*")]
        )
        if p:
            self._vhdx.set(p)
            self._auto_size()

    def _busy_start(self, msg="Working…"):
        self._busy = True
        self._status.set(msg)
        self._pb.start(10)

    def _busy_stop(self, msg="Done."):
        self._busy = False
        self._status.set(msg)
        self._pb.stop()

    # ── QUICK ACTIONS ──────────────────────────────────────────────────────

    def _quick_prune(self):
        if self._busy: return
        def _w():
            self._busy_start("Running docker prune…")
            op_docker_prune(lambda m: self.after(0, lambda: self._write(m)))
            self.after(0, lambda: self._busy_stop("Prune done."))
        threading.Thread(target=_w, daemon=True).start()

    def _show_df(self):
        if self._busy: return
        def _w():
            self._busy_start("Running docker system df…")
            ok, out = _run(["docker", "system", "df"], timeout=30)
            self.after(0, lambda: self._write(out))
            self.after(0, lambda: self._busy_stop("df done."))
        threading.Thread(target=_w, daemon=True).start()

    def _list_containers(self):
        if self._busy: return
        def _w():
            ok, out = _run(
                'docker ps -a --format "table {{.Names}}\\t{{.Status}}\\t{{.Image}}\\t{{.Size}}"',
                shell=True, timeout=20
            )
            self.after(0, lambda: self._write(out if out.strip() else "No containers found."))
        threading.Thread(target=_w, daemon=True).start()

    # ── NUCLEAR ────────────────────────────────────────────────────────────

    def _confirm_nuke(self):
        if self._busy:
            messagebox.showwarning("Busy", "Already running.")
            return

        steps = []
        if self._prune.get():  steps.append("• docker system prune -a --volumes")
        steps.append("• Stop Docker Desktop + WSL")
        if self._fstrim.get(): steps.append("• fstrim (mark free blocks)")
        if self._zero.get():   steps.append("• Zero-fill free space (SLOW)")
        if self._opt.get():    steps.append("• Optimize-VHD -Mode Full")
        if self._disk.get():   steps.append("• diskpart compact vdisk")
        if self._restart.get():steps.append("• Restart Docker Desktop")

        msg = (
            f"NUCLEAR SEQUENCE — are you sure?\n\n"
            + "\n".join(steps)
            + f"\n\nVHDX: {self._vhdx.get()}"
        )
        if not messagebox.askyesno("Confirm ☢️", msg, icon="warning"):
            return

        self._do_nuke()

    def _do_nuke(self):
        opts = {
            "prune":    self._prune.get(),
            "fstrim":   self._fstrim.get(),
            "zerofill": self._zero.get(),
            "optimize": self._opt.get(),
            "diskpart": self._disk.get(),
            "restart":  self._restart.get(),
        }
        vhdx = self._vhdx.get()

        def _log(m): self.after(0, lambda msg=m: self._write(msg))

        def _work():
            self.after(0, lambda: self._busy_start("☢️  Nuclear sequence running…"))
            result = run_nuclear(vhdx, opts, _log)
            self.after(0, lambda: self._busy_stop("☢️  Nuclear complete."))
            self.after(0, lambda: self._auto_size())
            self.after(0, lambda: messagebox.showinfo(
                "Done ✅",
                f"Nuclear complete!\n\n"
                f"Before : {result['before']}\n"
                f"After  : {result['after']}\n"
                f"Saved  : {result['saved']} ({result['pct']})"
            ))

        threading.Thread(target=_work, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if "--cli" in sys.argv:
        run_cli()
    else:
        if "--no-elevate" not in sys.argv:
            _elevate()
        if not HAS_TK:
            print("tkinter not available. Run with --cli flag.")
            sys.exit(1)
        App().mainloop()
