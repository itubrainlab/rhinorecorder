"""First-launch setup of Rhino Recorder.app.

    bootstrap.py <Resources> <library folder>

Installs the pinned libraries (requirements.txt: g.Pype, PySide6, ...)
from PyPI, then the bundled RhinoRecorder and gpype_rhino wheels, into
the library folder, and puts the prebuilt RhinoConnect helper where
gpype_rhino looks for it. A small window shows progress. The folder is
named after the build, so an updated app sets up a fresh one; older
ones are removed once the new one is complete.
"""
import os
import queue
import shutil
import subprocess
import sys
import threading
from pathlib import Path

RES = Path(sys.argv[1])
LIB = Path(sys.argv[2])
RUNTIME = LIB.parent
LOG = RUNTIME / "setup.log"
PYTHON = RES / "python" / "bin" / "python3"


def pip(log, *args) -> None:
    command = [str(PYTHON), "-I", "-m", "pip", "install",
               "--disable-pip-version-check", "--no-input",
               "--no-warn-script-location", "--target", str(LIB), *args]
    log.write(f"$ {' '.join(command)}\n")
    log.flush()
    process = subprocess.Popen(command, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        log.write(line)
        log.flush()
        yield line.strip()
    if process.wait() != 0:
        raise RuntimeError(f"pip failed (exit {process.returncode})")


def install(report) -> None:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(LIB, ignore_errors=True)
    with open(LOG, "w") as log:
        report("Downloading g.Pype and the libraries Rhino Recorder needs "
               "(first launch only)...")
        for line in pip(log, "-r", str(RES / "requirements.txt")):
            if line.startswith(("Collecting", "Downloading", "Installing")):
                report(line[:90])
        report("Installing Rhino Recorder...")
        wheels = sorted(str(p) for p in (RES / "wheels").glob("*.whl"))
        for line in pip(log, "--no-deps", *wheels):
            pass
    helper = RES / "RhinoConnect.app"
    if helper.exists():
        target = LIB / "gpype_rhino" / "macos" / "RhinoConnect.app"
        shutil.copytree(helper, target, symlinks=True, dirs_exist_ok=True)
    (LIB / ".complete").write_text("")
    for old in RUNTIME.iterdir():
        if old.is_dir() and old != LIB:
            shutil.rmtree(old, ignore_errors=True)


def main() -> int:
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError:  # no window: install quietly
        try:
            install(lambda text: None)
            return 0
        except Exception as error:  # noqa: BLE001
            print(f"Setup failed: {error}. See {LOG}", file=sys.stderr)
            return 1

    root = tk.Tk()
    root.title("Rhino Recorder")
    root.resizable(False, False)
    frame = ttk.Frame(root, padding=20)
    frame.pack()
    ttk.Label(frame, text="Setting up Rhino Recorder",
              font=("Helvetica", 15, "bold")).pack(anchor="w")
    status = tk.StringVar(value="Starting...")
    ttk.Label(frame, textvariable=status, width=70).pack(anchor="w",
                                                          pady=(8, 8))
    bar = ttk.Progressbar(frame, mode="indeterminate", length=480)
    bar.pack()
    bar.start(12)
    ttk.Label(frame, text="This needs an internet connection and takes a "
              "few minutes.\nIt happens once, and again after an update.",
              foreground="#666").pack(anchor="w", pady=(10, 0))
    root.update_idletasks()
    root.geometry(f"+{(root.winfo_screenwidth() - root.winfo_width()) // 2}"
                  f"+{root.winfo_screenheight() // 3}")

    events: queue.Queue = queue.Queue()
    result = {"ok": False}

    def work():
        try:
            install(lambda text: events.put(("status", text)))
            result["ok"] = True
        except Exception as error:  # noqa: BLE001
            events.put(("error", str(error)))
        events.put(("done", None))

    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == "status":
                    status.set(value)
                elif kind == "error":
                    messagebox.showerror(
                        "Rhino Recorder",
                        f"Setting up failed: {value}\n\nCheck the internet "
                        f"connection and open Rhino Recorder again. "
                        f"Details: {LOG}")
                elif kind == "done":
                    root.destroy()
                    return
        except queue.Empty:
            pass
        root.after(100, poll)

    threading.Thread(target=work, daemon=True).start()
    root.after(100, poll)
    root.mainloop()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    os.umask(0o022)
    sys.exit(main())
