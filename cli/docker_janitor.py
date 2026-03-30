"""
Docker Janitor Pro - NUCLEAR EDITION
A powerful GUI tool to clean Docker and shrink docker_data.vhdx to the bone.
Requirements: pip install rich psutil
Run as ADMINISTRATOR for full power.
"""

import os
import sys
import subprocess
import threading
import time
import json
import shutil
import tempfile
import ctypes
from datetime import datetime
from pathlib import Path

# ── Try importing tkinter (stdlib) ──────────────────────────────────────────
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, scrolledtext
except ImportError:
    print("tkinter not found — install Python with Tk support.")
    sys.exit(1)

# ── Optional rich for CLI fallback ───────────────────────────────────────────
try:
    from rich.console import Console
    from rich.table import Table
    RICH = True
    console = Console()
except ImportError:
    RICH = False


# ════════════════════════════════════════════════════════════════════════════
#  CORE ENGINE
# ════════════════════════════════════════════════════════════════════════════

class DockerEngine:
    """All the heavy lifting — pure logic, no GUI calls."""

    def __init__(self, vhdx_path: str, log_cb=None):
        self.vhdx_path = vhdx_path
        self._log = log_cb or print

    # ── helpers ─────────────────────────────────────────────────────────────

    def _run(self, cmd, shell=False, timeout=600, input_data=None):
        """Run a command. Returns (ok, stdout+stderr)."""
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True,
                shell=shell, timeout=timeout,
                input=input_data
            )
            out = (r.stdout or "") + (r.stderr or "")
            return r.returncode == 0, out
        except subprocess.TimeoutExpired:
            return False, "⏱ Command timed out."
        except Exception as e:
            return False, str(e)

    def _size(self) -> int:
        try:
            return os.path.getsize(self.vhdx_path)
        except Exception:
            return 0

    @staticmethod
    def _fmt(b: int) -> str:
        for u in ["B", "KB", "MB", "GB", "TB"]:
            if abs(b) < 1024:
                return f"{b:.2f} {u}"
            b /= 1024
        return f"{b:.2f} PB"

    def log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._log(f"[{ts}] {msg}")

    # ── docker queries ───────────────────────────────────────────────────────

    def docker_running(self) -> bool:
        ok, _ = self._run(["docker", "info"], timeout=10)
        return ok

    def list_containers(self, all_=True) -> list[dict]:
        flag = "-a" if all_ else ""
        cmd = f'docker ps {flag} --format "{{{{.ID}}}}|{{{{.Names}}}}|{{{{.Image}}}}|{{{{.Status}}}}|{{{{.Size}}}}"'
        ok, out = self._run(cmd, shell=True, timeout=30)
        rows = []
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 5:
                rows.append({
                    "id": parts[0], "name": parts[1],
                    "image": parts[2], "status": parts[3], "size": parts[4]
                })
        return rows

    def list_images(self) -> list[dict]:
        cmd = 'docker images --format "{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}|{{.CreatedSince}}"'
        ok, out = self._run(cmd, shell=True, timeout=30)
        rows = []
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 5:
                rows.append({
                    "id": parts[0], "repo": parts[1],
                    "tag": parts[2], "size": parts[3], "created": parts[4]
                })
        return rows

    def list_volumes(self) -> list[dict]:
        cmd = 'docker volume ls --format "{{.Name}}|{{.Driver}}|{{.Mountpoint}}"'
        ok, out = self._run(cmd, shell=True, timeout=30)
        rows = []
        for line in out.strip().splitlines():
            parts = line.split("|")
            if len(parts) == 3:
                rows.append({"name": parts[0], "driver": parts[1], "mount": parts[2]})
        return rows

    def disk_usage(self) -> str:
        ok, out = self._run(["docker", "system", "df"], timeout=30)
        return out if ok else "Could not retrieve docker df."

    # ── docker cleanup ───────────────────────────────────────────────────────

    def stop_containers(self, ids: list[str]) -> tuple[bool, str]:
        if not ids:
            return True, "Nothing to stop."
        self.log(f"Stopping {len(ids)} container(s)…")
        ok, out = self._run(["docker", "stop"] + ids, timeout=120)
        return ok, out

    def remove_containers(self, ids: list[str], force=True) -> tuple[bool, str]:
        if not ids:
            return True, "Nothing to remove."
        flag = ["-f"] if force else []
        self.log(f"Removing {len(ids)} container(s)…")
        ok, out = self._run(["docker", "rm"] + flag + ids, timeout=120)
        return ok, out

    def remove_images(self, ids: list[str], force=True) -> tuple[bool, str]:
        if not ids:
            return True, "Nothing to remove."
        flag = ["-f"] if force else []
        self.log(f"Removing {len(ids)} image(s)…")
        ok, out = self._run(["docker", "rmi"] + flag + ids, timeout=120)
        return ok, out

    def remove_volumes(self, names: list[str]) -> tuple[bool, str]:
        if not names:
            return True, "Nothing to remove."
        self.log(f"Removing {len(names)} volume(s)…")
        ok, out = self._run(["docker", "volume", "rm"] + names, timeout=120)
        return ok, out

    def prune_system(self, all_=True, volumes=True) -> tuple[bool, str]:
        cmd = ["docker", "system", "prune", "-f"]
        if all_:
            cmd.append("-a")
        if volumes:
            cmd.append("--volumes")
        self.log("Running docker system prune…")
        ok, out = self._run(cmd, timeout=300)
        return ok, out

    def prune_builds(self) -> tuple[bool, str]:
        self.log("Running docker buildx prune…")
        ok, out = self._run(["docker", "buildx", "prune", "-f", "-a"], timeout=180)
        return ok, out

    # ── WSL / VHDX ──────────────────────────────────────────────────────────

    def wsl_shutdown(self):
        self.log("Shutting down WSL…")
        self._run(["wsl", "--shutdown"], timeout=60)
        time.sleep(5)

    def stop_docker_desktop(self):
        self.log("Stopping Docker Desktop…")
        self._run(["taskkill", "/F", "/IM", "Docker Desktop.exe"], timeout=30)
        time.sleep(4)
        self._run(["wsl", "-t", "docker-desktop"], timeout=15)
        self._run(["wsl", "-t", "docker-desktop-data"], timeout=15)
        time.sleep(2)

    def fstrim(self) -> tuple[bool, str]:
        self.log("Running fstrim inside docker-desktop-data…")
        ok, out = self._run(
            ["wsl", "-d", "docker-desktop-data", "-e", "fstrim", "-av"],
            timeout=120
        )
        if ok:
            self.log("✅ fstrim OK")
        else:
            self.log("⚠️  fstrim on docker-desktop-data failed, trying default WSL…")
            ok, out = self._run(["wsl", "-e", "fstrim", "-av"], timeout=120)
        return ok, out

    def zerofill_wsl(self) -> tuple[bool, str]:
        """Write zeros to free space inside WSL so compaction reclaims more."""
        self.log("Zero-filling free space in WSL (dd /dev/zero)…")
        script = (
            "dd if=/dev/zero of=/tmp/_zero.tmp bs=1M 2>/dev/null; "
            "sync; rm -f /tmp/_zero.tmp; echo done"
        )
        ok, out = self._run(
            ["wsl", "-d", "docker-desktop-data", "-e", "bash", "-c", script],
            timeout=600
        )
        return ok, out

    def optimize_vhd(self) -> tuple[bool, str]:
        self.log(f"Optimize-VHD (Full mode) on {self.vhdx_path}…")
        ps = f'Optimize-VHD -Path "{self.vhdx_path}" -Mode Full'
        ok, out = self._run(["powershell", "-Command", ps], timeout=600)
        if ok:
            self.log("✅ Optimize-VHD succeeded")
        else:
            self.log(f"⚠️  Optimize-VHD: {out[:300]}")
        return ok, out

    def diskpart_compact(self) -> tuple[bool, str]:
        self.log("diskpart compact vdisk…")
        script = (
            f'select vdisk file="{self.vhdx_path}"\n'
            "attach vdisk readonly\n"
            "compact vdisk\n"
            "detach vdisk\n"
            "exit\n"
        )
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        tmp.write(script)
        tmp.close()
        ok, out = self._run(["diskpart", "/s", tmp.name], timeout=600)
        os.unlink(tmp.name)
        if ok and "successfully" in out.lower():
            self.log("✅ diskpart compact succeeded")
        else:
            self.log(f"⚠️  diskpart: {out[:300]}")
        return ok, out

    def resize_wsl_vhd(self, new_gb: int) -> tuple[bool, str]:
        """Resize the VHDX to a specific GB size (must be smaller than current)."""
        mb = new_gb * 1024
        self.log(f"Resizing VHDX to {new_gb} GB via WSL --manage…")
        ok, out = self._run(
            ["wsl", "--manage", "docker-desktop-data", f"--resize-{mb}MB"],
            timeout=120
        )
        return ok, out

    def export_import_recreate(self, export_path: str) -> tuple[bool, str]:
        """
        Nuclear option: export docker-desktop-data, unregister, re-import.
        This creates a fresh VHDX at the actual data size.
        """
        lines = []
        self.log("☢️  EXPORT/IMPORT RECREATION — this may take a while…")

        # Export
        self.log(f"Exporting docker-desktop-data to {export_path}…")
        ok, out = self._run(
            ["wsl", "--export", "docker-desktop-data", export_path],
            timeout=3600
        )
        lines.append(out)
        if not ok:
            return False, "\n".join(lines)

        self.log("Unregistering docker-desktop-data…")
        ok, out = self._run(
            ["wsl", "--unregister", "docker-desktop-data"],
            timeout=60
        )
        lines.append(out)
        if not ok:
            return False, "\n".join(lines)

        import_dir = str(Path(self.vhdx_path).parent)
        self.log(f"Importing back from {export_path} into {import_dir}…")
        ok, out = self._run(
            ["wsl", "--import", "docker-desktop-data", import_dir, export_path, "--version", "2"],
            timeout=3600
        )
        lines.append(out)
        return ok, "\n".join(lines)

    def vhdx_size_str(self) -> str:
        return self._fmt(self._size())

    # ── NUCLEAR SEQUENCE ─────────────────────────────────────────────────────

    def nuclear(
        self,
        do_prune=True,
        do_fstrim=True,
        do_zerofill=False,
        do_optimize=True,
        do_diskpart=True,
        progress_cb=None
    ) -> dict:
        steps = []
        before = self._size()

        def step(name, fn, *args, **kwargs):
            if progress_cb:
                progress_cb(name)
            self.log(f"── {name} ──")
            t0 = time.time()
            ok, out = fn(*args, **kwargs)
            elapsed = time.time() - t0
            steps.append({"step": name, "ok": ok, "elapsed": f"{elapsed:.1f}s", "out": out[:400]})
            self.log(out[:300] if out.strip() else "(no output)")
            return ok

        # 1. Docker prune
        if do_prune:
            step("Docker system prune (all + volumes)", self.prune_system, True, True)
            step("Docker buildx prune", self.prune_builds)

        # 2. Stop everything
        if progress_cb:
            progress_cb("Stopping Docker Desktop & WSL")
        self.stop_docker_desktop()
        self.wsl_shutdown()

        # 3. fstrim
        if do_fstrim:
            # WSL must be running for fstrim; restart it briefly
            self.log("Restarting docker-desktop-data for fstrim…")
            self._run(["wsl", "-d", "docker-desktop-data", "-e", "echo", "wake"], timeout=30)
            step("fstrim (mark free blocks)", self.fstrim)
            self.wsl_shutdown()

        # 4. Zero-fill free space (optional, slower but more effective)
        if do_zerofill:
            self.log("Restarting docker-desktop-data for zerofill…")
            self._run(["wsl", "-d", "docker-desktop-data", "-e", "echo", "wake"], timeout=30)
            step("Zerofill free space (dd)", self.zerofill_wsl)
            self.wsl_shutdown()

        # 5. Compact VHDX
        if do_optimize:
            step("Optimize-VHD (PowerShell)", self.optimize_vhd)
        if do_diskpart:
            step("diskpart compact vdisk", self.diskpart_compact)

        after = self._size()
        saved = before - after

        return {
            "before": self._fmt(before),
            "after": self._fmt(after),
            "saved": self._fmt(max(0, saved)),
            "pct": f"{saved/max(1,before)*100:.1f}%",
            "steps": steps
        }

    def start_docker_desktop(self):
        docker_exe = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Docker/Docker/Docker Desktop.exe"
        if docker_exe.exists():
            self.log("Restarting Docker Desktop…")
            subprocess.Popen([str(docker_exe)])
        else:
            self.log("Docker Desktop.exe not found — start it manually.")


# ════════════════════════════════════════════════════════════════════════════
#  GUI
# ════════════════════════════════════════════════════════════════════════════

DARK_BG   = "#0e1117"
PANEL_BG  = "#161b27"
ACCENT    = "#00ff9d"
ACCENT2   = "#ff4d6d"
WARN      = "#ffcc00"
TEXT      = "#e2e8f0"
MUTED     = "#64748b"
BORDER    = "#1e293b"
FONT_MONO = ("Cascadia Code", 9) if sys.platform == "win32" else ("Courier New", 9)
FONT_UI   = ("Segoe UI", 10) if sys.platform == "win32" else ("Helvetica", 10)
FONT_HEAD = ("Segoe UI Semibold", 11) if sys.platform == "win32" else ("Helvetica", 11)
FONT_BIG  = ("Segoe UI Black", 28) if sys.platform == "win32" else ("Helvetica", 28)


class JanitorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("🐳 Docker Janitor Pro — NUCLEAR EDITION")
        self.geometry("1200x800")
        self.minsize(900, 600)
        self.configure(bg=DARK_BG)
        self._busy = False

        self._vhdx_var = tk.StringVar(value=r"D:\docker_images\DockerDesktopWSL\disk\docker_data.vhdx")
        self._opt_prune     = tk.BooleanVar(value=True)
        self._opt_fstrim    = tk.BooleanVar(value=True)
        self._opt_zerofill  = tk.BooleanVar(value=False)
        self._opt_optimize  = tk.BooleanVar(value=True)
        self._opt_diskpart  = tk.BooleanVar(value=True)
        self._opt_restart   = tk.BooleanVar(value=True)

        self._build_ui()
        self._check_admin()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        # ── TOP BAR ──
        top = tk.Frame(self, bg=DARK_BG, pady=8)
        top.pack(fill="x", padx=16)

        tk.Label(top, text="🐳", font=("Segoe UI Emoji", 22), bg=DARK_BG, fg=ACCENT).pack(side="left")
        tk.Label(top, text=" Docker Janitor Pro", font=FONT_BIG,
                 bg=DARK_BG, fg=ACCENT).pack(side="left", padx=(4, 0))
        tk.Label(top, text="NUCLEAR EDITION", font=("Segoe UI Black", 11),
                 bg=DARK_BG, fg=ACCENT2).pack(side="left", padx=(8, 0), pady=(12, 0))

        # admin badge
        self._admin_lbl = tk.Label(top, text="", font=FONT_UI, bg=DARK_BG, fg=WARN)
        self._admin_lbl.pack(side="right")

        # ── VHDX PATH ROW ──
        pf = tk.Frame(self, bg=PANEL_BG, padx=12, pady=8)
        pf.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(pf, text="VHDX Path:", font=FONT_UI, bg=PANEL_BG, fg=MUTED).pack(side="left")
        vhdx_entry = tk.Entry(pf, textvariable=self._vhdx_var, font=FONT_MONO,
                              bg="#1e293b", fg=TEXT, insertbackground=ACCENT,
                              relief="flat", width=80)
        vhdx_entry.pack(side="left", fill="x", expand=True, padx=8)
        self._mk_btn(pf, "Browse…", self._browse_vhdx, side="left", small=True)
        self._size_lbl = tk.Label(pf, text="", font=FONT_UI, bg=PANEL_BG, fg=ACCENT)
        self._size_lbl.pack(side="left", padx=(12, 0))
        self._mk_btn(pf, "📏 Check Size", self._refresh_size, side="left", small=True)

        # ── NOTEBOOK ──
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Custom.TNotebook", background=DARK_BG, borderwidth=0)
        style.configure("Custom.TNotebook.Tab", background=PANEL_BG, foreground=MUTED,
                        padding=[14, 6], font=FONT_UI)
        style.map("Custom.TNotebook.Tab",
                  background=[("selected", BORDER)],
                  foreground=[("selected", ACCENT)])

        nb = ttk.Notebook(self, style="Custom.TNotebook")
        nb.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        self._tab_overview = tk.Frame(nb, bg=DARK_BG)
        self._tab_containers = tk.Frame(nb, bg=DARK_BG)
        self._tab_images = tk.Frame(nb, bg=DARK_BG)
        self._tab_volumes = tk.Frame(nb, bg=DARK_BG)
        self._tab_nuclear = tk.Frame(nb, bg=DARK_BG)
        self._tab_log = tk.Frame(nb, bg=DARK_BG)

        nb.add(self._tab_overview,   text="  📊 Overview  ")
        nb.add(self._tab_containers, text="  📦 Containers  ")
        nb.add(self._tab_images,     text="  🖼️ Images  ")
        nb.add(self._tab_volumes,    text="  💾 Volumes  ")
        nb.add(self._tab_nuclear,    text="  ☢️ NUCLEAR  ")
        nb.add(self._tab_log,        text="  📋 Log  ")

        self._build_overview()
        self._build_containers()
        self._build_images()
        self._build_volumes()
        self._build_nuclear()
        self._build_log()

        # ── STATUS BAR ──
        sb = tk.Frame(self, bg=BORDER, height=28)
        sb.pack(fill="x", padx=0)
        sb.pack_propagate(False)
        self._status_var = tk.StringVar(value="Ready.")
        tk.Label(sb, textvariable=self._status_var, font=FONT_UI,
                 bg=BORDER, fg=MUTED, anchor="w").pack(side="left", padx=12, fill="y")
        self._progress = ttk.Progressbar(sb, mode="indeterminate", length=200)
        self._progress.pack(side="right", padx=12, pady=4)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _mk_btn(self, parent, text, cmd, side="top", small=False, danger=False, fill=None):
        fg = ACCENT2 if danger else ACCENT
        font = FONT_UI if not small else ("Segoe UI", 9)
        b = tk.Button(parent, text=text, command=cmd,
                      bg=PANEL_BG, fg=fg, activebackground=BORDER, activeforeground=fg,
                      relief="flat", font=font, cursor="hand2",
                      padx=8 if small else 14, pady=2 if small else 7,
                      highlightthickness=1, highlightbackground=BORDER)
        if fill:
            b.pack(side=side, fill=fill, padx=4, pady=2)
        else:
            b.pack(side=side, padx=4, pady=2)
        return b

    def _tree(self, parent, cols, col_widths=None):
        frame = tk.Frame(parent, bg=DARK_BG)
        frame.pack(fill="both", expand=True, padx=8, pady=4)

        style = ttk.Style()
        style.configure("Dark.Treeview",
                         background=PANEL_BG, foreground=TEXT, fieldbackground=PANEL_BG,
                         rowheight=24, font=FONT_UI, borderwidth=0)
        style.configure("Dark.Treeview.Heading",
                         background=BORDER, foreground=ACCENT, font=FONT_HEAD, relief="flat")
        style.map("Dark.Treeview", background=[("selected", BORDER)], foreground=[("selected", ACCENT)])

        sb = tk.Scrollbar(frame, orient="vertical", bg=DARK_BG)
        sb.pack(side="right", fill="y")
        tree = ttk.Treeview(frame, columns=cols, show="headings",
                             style="Dark.Treeview", yscrollcommand=sb.set,
                             selectmode="extended")
        sb.config(command=tree.yview)

        for i, col in enumerate(cols):
            tree.heading(col, text=col)
            w = col_widths[i] if col_widths and i < len(col_widths) else 120
            tree.column(col, width=w, stretch=(i == len(cols)-1))

        tree.pack(side="left", fill="both", expand=True)
        return tree

    def _log_line(self, msg: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _set_status(self, msg: str):
        self._status_var.set(msg)

    def _busy_start(self, msg="Working…"):
        self._busy = True
        self._set_status(msg)
        self._progress.start(12)

    def _busy_stop(self, msg="Done."):
        self._busy = False
        self._set_status(msg)
        self._progress.stop()

    def _engine(self) -> DockerEngine:
        return DockerEngine(self._vhdx_var.get(), log_cb=self._log_line)

    # ── admin check ─────────────────────────────────────────────────────────

    def _check_admin(self):
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            is_admin = False
        if is_admin:
            self._admin_lbl.config(text="✅ Running as Administrator", fg=ACCENT)
        else:
            self._admin_lbl.config(text="⚠️ NOT Administrator — some features may fail", fg=ACCENT2)

    # ── OVERVIEW tab ─────────────────────────────────────────────────────────

    def _build_overview(self):
        p = self._tab_overview
        hdr = tk.Frame(p, bg=DARK_BG)
        hdr.pack(fill="x", padx=8, pady=8)
        tk.Label(hdr, text="Docker System Overview", font=FONT_HEAD, bg=DARK_BG, fg=ACCENT).pack(side="left")
        self._mk_btn(hdr, "🔄 Refresh", self._refresh_overview, side="right", small=True)

        self._df_box = scrolledtext.ScrolledText(
            p, bg=PANEL_BG, fg=TEXT, font=FONT_MONO,
            relief="flat", state="disabled", height=14
        )
        self._df_box.pack(fill="both", expand=True, padx=8, pady=4)

        stats = tk.Frame(p, bg=DARK_BG)
        stats.pack(fill="x", padx=8, pady=8)

        self._stat_cards = {}
        for label in ["Containers", "Images", "Volumes", "VHDX Size"]:
            card = tk.Frame(stats, bg=PANEL_BG, padx=20, pady=12, relief="flat",
                            highlightthickness=1, highlightbackground=BORDER)
            card.pack(side="left", expand=True, fill="both", padx=6)
            tk.Label(card, text=label, font=FONT_UI, bg=PANEL_BG, fg=MUTED).pack()
            val = tk.Label(card, text="—", font=("Segoe UI Black", 18), bg=PANEL_BG, fg=ACCENT)
            val.pack()
            self._stat_cards[label] = val

        self.after(500, self._refresh_overview)

    def _refresh_overview(self):
        def _work():
            eng = self._engine()
            self._busy_start("Refreshing overview…")
            df = eng.disk_usage()
            containers = eng.list_containers()
            images = eng.list_images()
            volumes = eng.list_volumes()
            size = eng.vhdx_size_str()

            def _update():
                self._df_box.configure(state="normal")
                self._df_box.delete("1.0", "end")
                self._df_box.insert("end", df)
                self._df_box.configure(state="disabled")
                self._stat_cards["Containers"].config(text=str(len(containers)))
                self._stat_cards["Images"].config(text=str(len(images)))
                self._stat_cards["Volumes"].config(text=str(len(volumes)))
                self._stat_cards["VHDX Size"].config(text=size)
                self._size_lbl.config(text=size)
                self._busy_stop("Overview refreshed.")
            self.after(0, _update)
        threading.Thread(target=_work, daemon=True).start()

    # ── CONTAINERS tab ───────────────────────────────────────────────────────

    def _build_containers(self):
        p = self._tab_containers
        toolbar = tk.Frame(p, bg=DARK_BG)
        toolbar.pack(fill="x", padx=8, pady=6)
        tk.Label(toolbar, text="Containers", font=FONT_HEAD, bg=DARK_BG, fg=ACCENT).pack(side="left")
        self._mk_btn(toolbar, "🔄 Refresh", self._refresh_containers, side="right", small=True)
        self._mk_btn(toolbar, "🗑 Remove Selected", self._remove_selected_containers, side="right", small=True, danger=True)
        self._mk_btn(toolbar, "⏹ Stop Selected", self._stop_selected_containers, side="right", small=True)
        self._mk_btn(toolbar, "☠️ Stop & Remove ALL", self._nuke_all_containers, side="right", small=True, danger=True)

        self._cont_tree = self._tree(
            p,
            cols=["ID", "Name", "Image", "Status", "Size"],
            col_widths=[80, 160, 180, 120, 100]
        )
        self.after(800, self._refresh_containers)

    def _refresh_containers(self):
        def _work():
            eng = self._engine()
            rows = eng.list_containers()
            def _update():
                self._cont_tree.delete(*self._cont_tree.get_children())
                for r in rows:
                    tag = "running" if "Up" in r["status"] else "stopped"
                    self._cont_tree.insert("", "end", iid=r["id"],
                        values=(r["id"][:12], r["name"], r["image"], r["status"], r["size"]),
                        tags=(tag,))
                self._cont_tree.tag_configure("running", foreground=ACCENT)
                self._cont_tree.tag_configure("stopped", foreground=MUTED)
            self.after(0, _update)
        threading.Thread(target=_work, daemon=True).start()

    def _get_selected_ids(self, tree) -> list[str]:
        return list(tree.selection())

    def _stop_selected_containers(self):
        ids = self._get_selected_ids(self._cont_tree)
        if not ids:
            messagebox.showinfo("No selection", "Select containers first.")
            return
        def _work():
            self._busy_start("Stopping containers…")
            ok, out = self._engine().stop_containers(ids)
            self._log_line(out)
            self.after(0, self._refresh_containers)
            self._busy_stop("Containers stopped.")
        threading.Thread(target=_work, daemon=True).start()

    def _remove_selected_containers(self):
        ids = self._get_selected_ids(self._cont_tree)
        if not ids:
            messagebox.showinfo("No selection", "Select containers first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove {len(ids)} container(s)?"):
            return
        def _work():
            self._busy_start("Removing containers…")
            ok, out = self._engine().remove_containers(ids)
            self._log_line(out)
            self.after(0, self._refresh_containers)
            self._busy_stop("Done.")
        threading.Thread(target=_work, daemon=True).start()

    def _nuke_all_containers(self):
        if not messagebox.askyesno("CONFIRM", "Stop AND remove ALL containers? Cannot be undone!", icon="warning"):
            return
        def _work():
            eng = self._engine()
            self._busy_start("Nuking all containers…")
            rows = eng.list_containers()
            ids = [r["id"] for r in rows]
            eng.stop_containers(ids)
            ok, out = eng.remove_containers(ids)
            self._log_line(out)
            self.after(0, self._refresh_containers)
            self._busy_stop("All containers removed.")
        threading.Thread(target=_work, daemon=True).start()

    # ── IMAGES tab ───────────────────────────────────────────────────────────

    def _build_images(self):
        p = self._tab_images
        toolbar = tk.Frame(p, bg=DARK_BG)
        toolbar.pack(fill="x", padx=8, pady=6)
        tk.Label(toolbar, text="Images", font=FONT_HEAD, bg=DARK_BG, fg=ACCENT).pack(side="left")
        self._mk_btn(toolbar, "🔄 Refresh", self._refresh_images, side="right", small=True)
        self._mk_btn(toolbar, "🗑 Remove Selected", self._remove_selected_images, side="right", small=True, danger=True)
        self._mk_btn(toolbar, "☠️ Remove ALL (prune -a)", self._prune_all_images, side="right", small=True, danger=True)

        self._img_tree = self._tree(
            p,
            cols=["ID", "Repository", "Tag", "Size", "Created"],
            col_widths=[80, 200, 100, 80, 120]
        )
        self.after(900, self._refresh_images)

    def _refresh_images(self):
        def _work():
            rows = self._engine().list_images()
            def _update():
                self._img_tree.delete(*self._img_tree.get_children())
                for r in rows:
                    self._img_tree.insert("", "end", iid=r["id"],
                        values=(r["id"][:12], r["repo"], r["tag"], r["size"], r["created"]))
            self.after(0, _update)
        threading.Thread(target=_work, daemon=True).start()

    def _remove_selected_images(self):
        ids = self._get_selected_ids(self._img_tree)
        if not ids:
            messagebox.showinfo("No selection", "Select images first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove {len(ids)} image(s)?"):
            return
        def _work():
            self._busy_start("Removing images…")
            ok, out = self._engine().remove_images(ids)
            self._log_line(out)
            self.after(0, self._refresh_images)
            self._busy_stop("Done.")
        threading.Thread(target=_work, daemon=True).start()

    def _prune_all_images(self):
        if not messagebox.askyesno("CONFIRM", "Remove ALL unused images? This frees significant space.", icon="warning"):
            return
        def _work():
            self._busy_start("Pruning all images…")
            ok, out = self._engine().prune_system(all_=True, volumes=False)
            self._log_line(out)
            self.after(0, self._refresh_images)
            self._busy_stop("Done.")
        threading.Thread(target=_work, daemon=True).start()

    # ── VOLUMES tab ──────────────────────────────────────────────────────────

    def _build_volumes(self):
        p = self._tab_volumes
        toolbar = tk.Frame(p, bg=DARK_BG)
        toolbar.pack(fill="x", padx=8, pady=6)
        tk.Label(toolbar, text="Volumes", font=FONT_HEAD, bg=DARK_BG, fg=ACCENT).pack(side="left")
        self._mk_btn(toolbar, "🔄 Refresh", self._refresh_volumes, side="right", small=True)
        self._mk_btn(toolbar, "🗑 Remove Selected", self._remove_selected_volumes, side="right", small=True, danger=True)
        self._mk_btn(toolbar, "☠️ Prune All Unused", self._prune_all_volumes, side="right", small=True, danger=True)

        self._vol_tree = self._tree(
            p,
            cols=["Name", "Driver", "Mountpoint"],
            col_widths=[200, 80, 400]
        )
        self.after(1000, self._refresh_volumes)

    def _refresh_volumes(self):
        def _work():
            rows = self._engine().list_volumes()
            def _update():
                self._vol_tree.delete(*self._vol_tree.get_children())
                for r in rows:
                    self._vol_tree.insert("", "end", iid=r["name"],
                        values=(r["name"], r["driver"], r["mount"]))
            self.after(0, _update)
        threading.Thread(target=_work, daemon=True).start()

    def _remove_selected_volumes(self):
        names = self._get_selected_ids(self._vol_tree)
        if not names:
            messagebox.showinfo("No selection", "Select volumes first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove {len(names)} volume(s)? DATA WILL BE LOST.", icon="warning"):
            return
        def _work():
            self._busy_start("Removing volumes…")
            ok, out = self._engine().remove_volumes(names)
            self._log_line(out)
            self.after(0, self._refresh_volumes)
            self._busy_stop("Done.")
        threading.Thread(target=_work, daemon=True).start()

    def _prune_all_volumes(self):
        if not messagebox.askyesno("CONFIRM", "Remove ALL unused volumes? DATA WILL BE LOST.", icon="warning"):
            return
        def _work():
            self._busy_start("Pruning volumes…")
            ok, out = self._engine()._run(["docker", "volume", "prune", "-f"], timeout=120)
            self._log_line(out)
            self.after(0, self._refresh_volumes)
            self._busy_stop("Done.")
        threading.Thread(target=_work, daemon=True).start()

    # ── NUCLEAR tab ──────────────────────────────────────────────────────────

    def _build_nuclear(self):
        p = self._tab_nuclear

        # Warning banner
        warn = tk.Frame(p, bg="#1a0a0a", padx=16, pady=10,
                        highlightthickness=2, highlightbackground=ACCENT2)
        warn.pack(fill="x", padx=16, pady=12)
        tk.Label(warn, text="☢️  NUCLEAR VHDX SHRINK SEQUENCE", font=("Segoe UI Black", 13),
                 bg="#1a0a0a", fg=ACCENT2).pack()
        tk.Label(warn,
                 text="This will STOP Docker Desktop, prune everything, run fstrim,\n"
                      "and compact the VHDX. Docker will restart automatically.\n"
                      "Run as Administrator for full effectiveness.",
                 font=FONT_UI, bg="#1a0a0a", fg=WARN, justify="center").pack(pady=4)

        # Options
        opts = tk.LabelFrame(p, text=" Options ", bg=DARK_BG, fg=ACCENT,
                             font=FONT_HEAD, padx=16, pady=8, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER)
        opts.pack(fill="x", padx=16, pady=4)

        def _chk(parent, var, text, row, col, tooltip=""):
            cb = tk.Checkbutton(parent, text=text, variable=var,
                                bg=DARK_BG, fg=TEXT, selectcolor=PANEL_BG,
                                activebackground=DARK_BG, activeforeground=ACCENT,
                                font=FONT_UI)
            cb.grid(row=row, column=col, sticky="w", padx=16, pady=4)
            return cb

        _chk(opts, self._opt_prune,    "🧹 docker system prune -a --volumes", 0, 0)
        _chk(opts, self._opt_fstrim,   "✂️  fstrim (mark free blocks in WSL)", 1, 0)
        _chk(opts, self._opt_zerofill, "🕳  Zero-fill free space (dd, SLOW but thorough)", 2, 0)
        _chk(opts, self._opt_optimize, "💿 Optimize-VHD -Mode Full (PowerShell)", 0, 1)
        _chk(opts, self._opt_diskpart, "💿 diskpart compact vdisk",             1, 1)
        _chk(opts, self._opt_restart,  "🔄 Restart Docker Desktop when done",   2, 1)

        # Export/Import section
        ei = tk.LabelFrame(p, text=" ☢️ MAXIMUM NUKE: Export → Unregister → Reimport ",
                           bg=DARK_BG, fg=ACCENT2, font=FONT_HEAD, padx=16, pady=8,
                           relief="flat", highlightthickness=1, highlightbackground=ACCENT2)
        ei.pack(fill="x", padx=16, pady=8)

        tk.Label(ei,
                 text="Creates a brand-new VHDX at actual data size (may save 100+ GB).\n"
                      "Requires: WSL export/import. Docker data is preserved. Takes 10-60 min.",
                 bg=DARK_BG, fg=WARN, font=FONT_UI, justify="left").pack(anchor="w")

        ef = tk.Frame(ei, bg=DARK_BG)
        ef.pack(fill="x", pady=4)
        tk.Label(ef, text="Export tar path:", bg=DARK_BG, fg=MUTED, font=FONT_UI).pack(side="left")
        self._export_var = tk.StringVar(value=r"D:\docker_backup\docker-desktop-data.tar")
        ent = tk.Entry(ef, textvariable=self._export_var, bg=PANEL_BG, fg=TEXT,
                       font=FONT_MONO, relief="flat", width=60, insertbackground=ACCENT)
        ent.pack(side="left", padx=8)
        self._mk_btn(ef, "Browse", self._browse_export, side="left", small=True)

        self._mk_btn(ei, "☢️  RUN EXPORT/IMPORT RECREATION", self._run_export_import,
                     side="top", danger=True, fill="x")

        # NUKE button
        nuke_frame = tk.Frame(p, bg=DARK_BG)
        nuke_frame.pack(pady=12)
        nuke_btn = tk.Button(
            nuke_frame, text="☢️  LAUNCH NUCLEAR SEQUENCE",
            command=self._run_nuclear,
            bg=ACCENT2, fg="white", activebackground="#cc1a3a",
            font=("Segoe UI Black", 14), relief="flat",
            cursor="hand2", padx=30, pady=14
        )
        nuke_btn.pack()

        # Result area
        self._nuke_result = scrolledtext.ScrolledText(
            p, bg=PANEL_BG, fg=TEXT, font=FONT_MONO,
            relief="flat", state="disabled", height=6
        )
        self._nuke_result.pack(fill="both", expand=True, padx=16, pady=(0, 8))

    def _browse_vhdx(self):
        path = filedialog.askopenfilename(
            title="Select docker_data.vhdx",
            filetypes=[("VHDX files", "*.vhdx"), ("All files", "*.*")]
        )
        if path:
            self._vhdx_var.set(path)

    def _browse_export(self):
        path = filedialog.asksaveasfilename(
            title="Save export tar",
            defaultextension=".tar",
            filetypes=[("TAR files", "*.tar"), ("All files", "*.*")]
        )
        if path:
            self._export_var.set(path)

    def _refresh_size(self):
        try:
            size = self._engine().vhdx_size_str()
            self._size_lbl.config(text=size)
        except Exception as e:
            self._size_lbl.config(text=f"Error: {e}")

    def _run_nuclear(self):
        if self._busy:
            messagebox.showwarning("Busy", "Already running an operation.")
            return
        if not messagebox.askyesno(
            "CONFIRM NUCLEAR",
            "This will:\n"
            "• Stop Docker Desktop & WSL\n"
            "• Prune all containers/images/volumes (if checked)\n"
            "• Run fstrim + compact on the VHDX\n\n"
            "Docker will restart when done.\nProceed?",
            icon="warning"
        ):
            return

        def _work():
            self._busy_start("☢️ NUCLEAR SEQUENCE IN PROGRESS…")
            eng = self._engine()

            def _progress(step):
                self.after(0, lambda s=step: self._set_status(f"☢️ {s}"))

            result = eng.nuclear(
                do_prune=self._opt_prune.get(),
                do_fstrim=self._opt_fstrim.get(),
                do_zerofill=self._opt_zerofill.get(),
                do_optimize=self._opt_optimize.get(),
                do_diskpart=self._opt_diskpart.get(),
                progress_cb=_progress,
            )

            if self._opt_restart.get():
                eng.start_docker_desktop()

            def _update():
                self._nuke_result.configure(state="normal")
                self._nuke_result.delete("1.0", "end")
                report = (
                    f"{'='*50}\n"
                    f"  ☢️  NUCLEAR COMPLETE\n"
                    f"{'='*50}\n"
                    f"  Before : {result['before']}\n"
                    f"  After  : {result['after']}\n"
                    f"  Saved  : {result['saved']} ({result['pct']})\n"
                    f"{'='*50}\n\n"
                )
                for s in result["steps"]:
                    icon = "✅" if s["ok"] else "⚠️"
                    report += f"{icon} [{s['elapsed']}] {s['step']}\n"
                    if not s["ok"] and s["out"]:
                        report += f"   {s['out'][:200]}\n"
                self._nuke_result.insert("end", report)
                self._nuke_result.configure(state="disabled")
                self._busy_stop("☢️ Nuclear sequence complete.")

                saved_bytes = result["saved"]
                messagebox.showinfo(
                    "Nuclear Complete",
                    f"VHDX shrink complete!\n\n"
                    f"Before : {result['before']}\n"
                    f"After  : {result['after']}\n"
                    f"Saved  : {result['saved']} ({result['pct']})"
                )
            self.after(0, _update)

        threading.Thread(target=_work, daemon=True).start()

    def _run_export_import(self):
        export_path = self._export_var.get().strip()
        if not export_path:
            messagebox.showerror("Error", "Set an export tar path first.")
            return
        # Ensure export directory exists
        export_dir = str(Path(export_path).parent)
        os.makedirs(export_dir, exist_ok=True)

        if not messagebox.askyesno(
            "CONFIRM MAXIMUM NUKE",
            f"This will:\n"
            f"1. STOP Docker Desktop\n"
            f"2. Export docker-desktop-data → {export_path}\n"
            f"3. Unregister the distro (DELETES current VHDX!)\n"
            f"4. Re-import from the tar (new compact VHDX)\n\n"
            f"This takes 10–60 minutes.\n"
            f"Docker Desktop MUST be reinstalled/restarted after.\n\n"
            f"PROCEED?",
            icon="warning"
        ):
            return

        def _work():
            self._busy_start("☢️☢️ EXPORT/IMPORT RECREATION IN PROGRESS…")
            eng = self._engine()
            eng.stop_docker_desktop()
            eng.wsl_shutdown()
            ok, out = eng.export_import_recreate(export_path)
            self._log_line(out)
            if ok:
                msg = f"✅ Recreated!\nNew VHDX at: {eng.vhdx_path}\nStart Docker Desktop manually."
                self.after(0, lambda: messagebox.showinfo("Done", msg))
            else:
                self.after(0, lambda: messagebox.showerror("Failed", f"Export/import failed.\n{out[:400]}"))
            self._busy_stop("Export/import done." if ok else "Export/import FAILED.")
        threading.Thread(target=_work, daemon=True).start()

    # ── LOG tab ──────────────────────────────────────────────────────────────

    def _build_log(self):
        p = self._tab_log
        toolbar = tk.Frame(p, bg=DARK_BG)
        toolbar.pack(fill="x", padx=8, pady=6)
        tk.Label(toolbar, text="Operation Log", font=FONT_HEAD, bg=DARK_BG, fg=ACCENT).pack(side="left")
        self._mk_btn(toolbar, "🗑 Clear", self._clear_log, side="right", small=True)
        self._mk_btn(toolbar, "💾 Save", self._save_log, side="right", small=True)

        self._log_box = scrolledtext.ScrolledText(
            p, bg="#050810", fg=ACCENT, font=FONT_MONO,
            relief="flat", state="disabled", insertbackground=ACCENT
        )
        self._log_box.pack(fill="both", expand=True, padx=8, pady=4)

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            title="Save log",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")]
        )
        if path:
            content = self._log_box.get("1.0", "end")
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Saved", f"Log saved to {path}")


# ════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ════════════════════════════════════════════════════════════════════════════

def _request_admin():
    """Re-launch self as Administrator if not already."""
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            script = os.path.abspath(sys.argv[0])
            params = " ".join([f'"{a}"' for a in sys.argv[1:]])
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {params}', None, 1
            )
            sys.exit(0)
    except Exception:
        pass


if __name__ == "__main__":
    # Optionally auto-elevate (comment out if you handle UAC yourself)
    if "--no-elevate" not in sys.argv:
        _request_admin()

    app = JanitorApp()
    app.mainloop()
