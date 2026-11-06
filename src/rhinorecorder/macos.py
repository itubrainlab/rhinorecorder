"""Running with Bluetooth access on macOS.

gtec-unicorn talks to Bluetooth from inside the Python process, and macOS
lets a process do that only if the app it belongs to declares why, with
an ``NSBluetoothAlwaysUsageDescription`` in its Info.plist; otherwise
macOS ends the process the moment it asks. Rhino Recorder.app declares
it. A Rhino Recorder started from a terminal belongs to the terminal app,
which usually does not (Terminal.app does not), so it relaunches itself
inside a small app bundle that does: :func:`relaunch_with_bluetooth`.
"""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path

#: Set in the environment of a process that already belongs to an app
#: declaring Bluetooth use: Rhino Recorder.app, or the bundle below.
BUNDLED_ENV = "RHINORECORDER_BUNDLED"

BUNDLE = (Path.home() / "Library" / "Caches" / "RhinoRecorder"
          / "Rhino Recorder.app")

_INFO = {
    "CFBundleName": "Rhino Recorder",
    "CFBundleDisplayName": "Rhino Recorder",
    "CFBundleIdentifier": "dk.itu.brainlab.RhinoRecorder.terminal",
    "CFBundleExecutable": "rhino-recorder",
    "CFBundlePackageType": "APPL",
    "LSUIElement": False,
    "NSHighResolutionCapable": True,
    "NSBluetoothAlwaysUsageDescription":
        "Rhino Recorder reads the Unicorn EEG headset over Bluetooth.",
    "NSLocalNetworkUsageDescription":
        "Rhino Recorder receives triggers and streams data over UDP and LSL.",
}


def needs_relaunch() -> bool:
    return sys.platform == "darwin" and not os.environ.get(BUNDLED_ENV)


def _write_bundle(python: str) -> None:
    """Create or update the bundle, running ``python -m rhinorecorder``."""
    executable = BUNDLE / "Contents" / "MacOS" / "rhino-recorder"
    script = ("#!/bin/sh\n"
              f"export {BUNDLED_ENV}=1\n"
              f'exec "{python}" -m rhinorecorder "$@"\n')
    info = plistlib.dumps(_INFO)
    plist = BUNDLE / "Contents" / "Info.plist"
    if (executable.exists() and executable.read_text() == script
            and plist.exists() and plist.read_bytes() == info):
        return
    executable.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(info)
    executable.write_text(script)
    executable.chmod(0o755)
    subprocess.run(["codesign", "--force", "--sign", "-", str(BUNDLE)],
                   capture_output=True, check=False)


def relaunch_with_bluetooth(argv: list[str]) -> int:
    """Run Rhino Recorder again inside the bundle and wait for it.

    Its output comes to this terminal where there is one.

    Returns:
        The exit status of ``open``.
    """
    _write_bundle(sys.executable)
    command = ["open", "-W", "-n", str(BUNDLE)]
    for stream, name in ((sys.stdout, "--stdout"), (sys.stderr, "--stderr")):
        try:
            command += [name, os.ttyname(stream.fileno())]
        except (OSError, ValueError, AttributeError):
            pass
    if argv:
        command += ["--args", *argv]
    return subprocess.call(command)
