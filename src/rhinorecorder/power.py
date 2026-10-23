"""Keeping the computer awake while acquiring: a system that goes to sleep
drops the Bluetooth link and ends the recording."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from typing import Optional


class KeepAwake:
    """Holds off system sleep between :meth:`hold` and :meth:`release`.
    Where the platform offers no way, it does nothing."""

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._held = False

    def hold(self) -> None:
        if self._held:
            return
        self._held = True
        try:
            if sys.platform == "win32":
                import ctypes
                # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
            elif sys.platform == "darwin" and shutil.which("caffeinate"):
                self._process = subprocess.Popen(
                    ["caffeinate", "-i", "-w", str(os.getpid())])
            elif shutil.which("systemd-inhibit"):
                self._process = subprocess.Popen(
                    ["systemd-inhibit", "--what=sleep:idle",
                     "--who=Rhino Recorder", "--why=Recording EEG",
                     "sleep", "infinity"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:  # noqa: BLE001 - best effort only
            pass

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            if self._process is not None:
                self._process.terminate()
                self._process.wait(timeout=2)
        except Exception:  # noqa: BLE001
            pass
        self._process = None
