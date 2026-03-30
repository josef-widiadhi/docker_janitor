# 🐳 Docker Janitor Pro

> **Shrink your bloated `docker_data.vhdx` — GUI, CLI, or standalone EXE.**

A Windows tool to clean Docker junk and compact the WSL2 VHDX disk image that
grows unbounded and never shrinks on its own.  Supports a full *nuclear*
sequence: Docker prune → fstrim → Optimize-VHD → diskpart compact.

---

## Table of Contents

- [Why You Need This](#why-you-need-this)
- [Requirements](#requirements)
- [Installation](#installation)
- [GUI Usage](#gui-usage)
- [CLI Usage](#cli-usage)
- [Building a Standalone EXE](#building-a-standalone-exe)
- [How the Nuclear Sequence Works](#how-the-nuclear-sequence-works)
- [Tips for Maximum Shrinkage](#tips-for-maximum-shrinkage)
- [Troubleshooting](#troubleshooting)

---

## Why You Need This

Docker Desktop on Windows uses a WSL2 virtual disk (`docker_data.vhdx`).
This file **grows** as you pull images, build layers, and create volumes —
but it **never shrinks automatically**, even after you delete everything.

A fresh Docker install might show 5 GB of real data yet the VHDX sits at
**200+ GB** on disk.  This tool reclaims that space.

---

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10/11 with WSL2 | Required |
| Docker Desktop installed | Must be installed (not just WSL docker) |
| **Run as Administrator** | Required for `Optimize-VHD` and `diskpart` |
| Python 3.10+ | Only needed if running `.py` directly |
| `pyinstaller` | Only needed if building an EXE |

---

## Installation

### Option A — Run the Python script directly (no install)

```bash
# Clone or download the files
git clone https://github.com/yourname/docker-janitor-pro
cd docker-janitor-pro

# No pip packages required for the GUI/CLI
# (pyinstaller only needed to BUILD an exe)
python docker_janitor_gui.py
```

### Option B — Use the pre-built EXE

Download `DockerJanitorPro.exe` from Releases, right-click → **Run as Administrator**.

---

## GUI Usage

```bash
# Launch the GUI (auto-requests Admin via UAC)
python docker_janitor_gui.py
```

Pass `--no-elevate` if you want to handle UAC yourself:

```bash
python docker_janitor_gui.py --no-elevate
```

### GUI Walkthrough

```
┌─────────────────────────────────────────────────────────────┐
│ 🐳 Docker Janitor Pro                     ✅ Administrator  │
├─────────────────────────────────────────────────────────────┤
│ VHDX Path  [D:\docker_images\...\docker_data.vhdx] [Browse] │
│                                              Current: 198 GB │
├──────────────────────┬──────────────────────────────────────┤
│ SEQUENCE OPTIONS     │  OUTPUT LOG                          │
│                      │                                      │
│ ☑ Docker prune       │  [08:14:22] ▶ Docker Prune           │
│ ☑ fstrim             │  Deleted: 47 containers              │
│ ☐ Zero-fill (slow)   │  Reclaimed: 12.3 GB                  │
│ ☑ Optimize-VHD       │  [08:15:01] ▶ fstrim                 │
│ ☑ diskpart compact   │  /: 38.4 GiB trimmed                 │
│ ☑ Restart Docker     │  [08:16:20] ▶ Optimize-VHD           │
│                      │  ...                                  │
│ Current VHDX Size    │                                      │
│   198.4 GB           │                                      │
│   [↺ Refresh]        │                          [Clear][Save]│
│ ─────────────────    │                                      │
│ [☢  NUKE IT]         │                                      │
│                      │                                      │
│ QUICK ACTIONS        │                                      │
│ [🧹 Prune only]      │                                      │
│ [📋 docker system df]│                                      │
│ [📦 List containers] │                                      │
└──────────────────────┴──────────────────────────────────────┘
```

**Steps:**

1. **Set VHDX Path** — default is the standard Docker Desktop location.
   Click **Browse** if yours is different.

2. **Check the Current Size** — click `↺ Refresh` to see how big it is now.

3. **Choose options** — tick the steps you want. Recommended for first run:
   all boxes checked except *Zero-fill* (that one is slow, enable if the
   others don't recover enough space).

4. **Hit ☢ NUKE IT** — confirm the prompt and watch the log.

5. **Done** — a popup shows Before/After/Saved when complete.

### Quick Actions (no confirmation needed)

| Button | What it does |
|---|---|
| 🧹 Prune only (fast) | `docker system prune -a --volumes` — safe, fast |
| 📋 docker system df | Shows disk usage breakdown by image/container/volume |
| 📦 List containers | Lists all containers with status |

---

## CLI Usage

Add `--cli` to use without a GUI (great for scripts and Task Scheduler).

### Show help

```bash
python docker_janitor_gui.py --cli --help
```

### Check VHDX size

```bash
python docker_janitor_gui.py --cli --size
python docker_janitor_gui.py --cli --size --vhdx "E:\data\docker_data.vhdx"
```

```
VHDX: D:\docker_images\DockerDesktopWSL\disk\docker_data.vhdx
Size: 198.4 GB
```

### Quick prune only (no VHDX compaction)

```bash
python docker_janitor_gui.py --cli --prune-only
```

### Full nuclear sequence (interactive confirm)

```bash
python docker_janitor_gui.py --cli --nuke
```

### Full nuclear — skip confirm (for automation)

```bash
python docker_janitor_gui.py --cli --nuke --yes
```

### Custom VHDX path

```bash
python docker_janitor_gui.py --cli --nuke --vhdx "E:\docker\docker_data.vhdx"
```

### Pick and choose steps

```bash
# Nuclear without docker prune (keep your images)
python docker_janitor_gui.py --cli --nuke --no-prune

# Nuclear without restarting Docker after
python docker_janitor_gui.py --cli --nuke --no-restart

# Enable zero-fill (slow but reclaims more space)
python docker_janitor_gui.py --cli --nuke --zerofill

# Only run Optimize-VHD + diskpart (skip prune and fstrim)
python docker_janitor_gui.py --cli --nuke --no-prune --no-fstrim --no-restart
```

### All CLI flags

| Flag | Default | Description |
|---|---|---|
| `--cli` | — | **Required** to enter CLI mode |
| `--nuke` | — | Run the nuclear sequence |
| `--prune-only` | — | Only run docker prune, exit |
| `--size` | — | Print VHDX size and exit |
| `--vhdx PATH` | Standard Docker path | Path to docker_data.vhdx |
| `--yes` | False | Skip confirmation prompt |
| `--no-prune` | False | Skip docker prune |
| `--no-fstrim` | False | Skip fstrim |
| `--zerofill` | False | Enable zero-fill (slow) |
| `--no-optimize` | False | Skip Optimize-VHD |
| `--no-diskpart` | False | Skip diskpart compact |
| `--no-restart` | False | Don't restart Docker |

### Schedule with Windows Task Scheduler

Run automatically every Sunday at 2am:

```powershell
# In PowerShell (as Admin):
$action = New-ScheduledTaskAction `
    -Execute "python" `
    -Argument '"C:\tools\docker_janitor_gui.py" --cli --nuke --yes --no-restart'

$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 2am

Register-ScheduledTask `
    -TaskName "DockerJanitor" `
    -Action $action `
    -Trigger $trigger `
    -RunLevel Highest `
    -Force
```

---

## Building a Standalone EXE

No Python needed on the target machine.

### 1. Install PyInstaller

```bash
pip install pyinstaller
```

### 2. Run the build script

```bash
# Standard build (folder output, fast launch)
python build_exe.py

# Single-file EXE (easier to share, ~1-2s slower to start)
python build_exe.py --onefile

# With debug console visible (useful for troubleshooting)
python build_exe.py --debug

# Clean old build artefacts first
python build_exe.py --clean --onefile
```

### 3. Find your EXE

| Build type | Output location |
|---|---|
| Default (folder) | `dist/DockerJanitorPro/DockerJanitorPro.exe` |
| `--onefile` | `dist/DockerJanitorPro.exe` |

For the **folder build**: distribute the entire `dist/DockerJanitorPro/` folder
(not just the `.exe`).  The EXE won't run without the supporting files next to it.

For **`--onefile`**: distribute just the single `.exe`.

### 4. Optional: add a custom icon

Place an `icon.ico` file next to `build_exe.py` before running it.
Free converters: [convertio.co](https://convertio.co/png-ico/) or [icoconvert.com](https://icoconvert.com).

### 5. Set to always run as Admin

Right-click the EXE → **Properties** → **Compatibility** tab →
☑ **Run this program as an administrator** → OK.

Or embed it via manifest (advanced):

```bash
# Add to build_exe.py cmd list:
"--manifest", "admin.manifest"
```

`admin.manifest`:
```xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>
```

---

## How the Nuclear Sequence Works

Each step builds on the last.  You can enable/disable any step.

```
Step 1  docker system prune -a --volumes
        Deletes stopped containers, unused images, dangling volumes.
        Reclaims space INSIDE the VHDX but doesn't shrink the file yet.

Step 2  Stop Docker Desktop + WSL
        Required — you cannot compact a mounted VHDX.

Step 3  fstrim -av  (inside docker-desktop-data WSL distro)
        Tells the Linux filesystem to mark deleted blocks as free.
        Without this, the VHDX compactor sees "used" blocks even for
        deleted files. CRITICAL for good results.

Step 4  Zero-fill free space  (optional, slow)
        Writes zeros to all free space with dd, then deletes the temp file.
        Forces the compactor to reclaim even more. Takes 5-30 minutes
        depending on VHDX size. Recommended if fstrim alone doesn't help.

Step 5  Optimize-VHD -Mode Full  (PowerShell / Hyper-V)
        Windows native VHDX compaction. Works on dynamic VHDs.
        May fail on sparse VHDs (that's OK — diskpart covers it).

Step 6  diskpart compact vdisk
        Attaches VHDX read-only, compacts, detaches.
        Works alongside or instead of Optimize-VHD.

Step 7  Restart Docker Desktop
        Gets you back to work automatically.
```

### Why the VHDX is still big after compaction

If you save less than 1 GB after nuclear:

- **Your VHDX might be sparse** — modern Docker Desktop uses sparse VHDs.
  Traditional compaction tools struggle with these.  
  **Solution:** Use Docker Desktop → Troubleshoot → *Clean / Purge data* →
  *WSL 2 data* → Delete. This recreates the VHDX from scratch. ⚠️ Removes
  all images and containers.

- **fstrim isn't reaching the right distro** — the tool tries
  `docker-desktop-data` first, then falls back to default WSL. Check the log
  to see which ran.

- **Not running as Administrator** — `Optimize-VHD` and `diskpart` silently
  fail without Admin rights. The badge in the top-right corner tells you.

---

## Tips for Maximum Shrinkage

1. **Run as Administrator** — always. Many steps silently fail without it.

2. **Delete what you don't need first** — before running nuclear, manually
   remove images/containers you know you won't use. In Docker Desktop or:
   ```bash
   docker rmi $(docker images -q)
   docker rm $(docker ps -aq)
   docker volume rm $(docker volume ls -q)
   ```

3. **Enable Zero-fill** — slow but significantly improves compaction results
   on older VHDX files. Enable it in the GUI or via `--zerofill`.

4. **Run nuclear monthly** — set up Task Scheduler (see CLI section above).

5. **If nothing works → Export/Import recreation** — this is the guaranteed
   nuclear option. Use `docker_janitor_pro.py` (the advanced version) which
   has this feature built in. It exports the WSL distro, unregisters it, and
   re-imports — creating a brand-new compact VHDX at the true data size.

---

## Troubleshooting

### "Access denied" or "diskpart failed"
→ Not running as Administrator. Right-click → *Run as administrator*.

### "Optimize-VHD failed (sparse VHDX)"
→ Expected on modern Docker Desktop. diskpart will also try. If both fail,
use Docker Desktop → Troubleshoot → Clean / Purge data.

### "fstrim failed — distro not running"
→ The tool will automatically try the default WSL distro. If that also fails,
try running fstrim manually first:
```bash
wsl -d docker-desktop-data -e fstrim -av
```

### Docker won't start after nuclear
→ Open Docker Desktop normally. It may need a moment to reinitialize WSL.
If it hangs, run: `wsl --shutdown` then restart Docker Desktop.

### VHDX path not found
→ Your Docker data may be in a different location. Find it with:
```powershell
(Get-ChildItem -Path "$env:LOCALAPPDATA\Docker" -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue).FullName
```
Or check Docker Desktop → Settings → Resources → Disk image location.

### EXE doesn't launch / crashes instantly
→ Build with `--debug` flag to see the error console:
```bash
python build_exe.py --debug
```

---

## File Reference

| File | Purpose |
|---|---|
| `docker_janitor_gui.py` | Main app — GUI + CLI in one file |
| `build_exe.py` | Builds a standalone Windows EXE |
| `docker_janitor_pro.py` | Advanced version with full tabbed GUI, export/import |
| `README.md` | This file |

---

## License

MIT — use freely, modify freely, no warranty.
