"""Check a built package on the simulated headset, without a display.

    <package python> -I smoke_test.py <library folder> <expected version>

Run with the package's own Python against the library folder its first
launch set up, so it checks what users get: the bundled Python, the
libraries installed from PyPI (g.Pype, Qt, OSCAR) and the bundled wheels.
It opens the main window, then records from the simulated headset with
OSCAR on and reads the files back.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, sys.argv[1])
EXPECTED = sys.argv[2]
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import gprhino  # noqa: E402
import gpype  # noqa: E402
import numpy as np  # noqa: E402
import rhinorecorder  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rhinorecorder import layout  # noqa: E402
from rhinorecorder.recorder import RUNNING, Recorder  # noqa: E402
from rhinorecorder.settings import Settings  # noqa: E402
from rhinorecorder.simulator import SIMULATED_SERIAL  # noqa: E402
from rhinorecorder.ui.connect_dialog import Choice  # noqa: E402
from rhinorecorder.ui.main_window import MainWindow  # noqa: E402

print(f"Rhino Recorder {rhinorecorder.__version__}, gpype-rhino "
      f"{gprhino.__version__}, g.Pype {gpype.__version__}, Python "
      f"{sys.version.split()[0]} on {sys.platform}", flush=True)
assert rhinorecorder.__version__ == EXPECTED, rhinorecorder.__version__


def wait_for(condition, timeout=30.0, app=None):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        if app is not None:
            app.processEvents()
        time.sleep(0.05)


folder = tempfile.mkdtemp()
settings = Settings()
for logger in settings.recording.loggers().values():
    logger.folder = folder

app = QApplication([])
window = MainWindow(settings, Choice(SIMULATED_SERIAL, "", "auto", True))
window._save_settings = lambda: None
window.show()
app.processEvents()
window.close()
print("main window: ok", flush=True)

recorder = Recorder(settings, simulate=True)
errors = []
recorder.on_error = errors.append
recorder.start()
wait_for(lambda: recorder.state == RUNNING or errors)
assert not errors, errors
time.sleep(4.5)  # OSCAR settles at sample 875
paths = recorder.start_recording()
time.sleep(3)
recorder.stop_recording()
recorder.stop()
assert not errors, errors

names = sorted(os.path.basename(p) for p in paths)
assert len(paths) == 4, names
for path in paths:
    assert os.path.getsize(path) > 0, path
for path in (p for p in paths if p.endswith(".csv")):
    data = np.loadtxt(path, delimiter=",", skiprows=1, ndmin=2)
    assert data.shape[1] == len(layout.LABELS), data.shape
    assert len(data) > 2 * layout.SAMPLING_RATE, len(data)
    print(f"{os.path.basename(path)}: {len(data)} scans", flush=True)
print("recording: ok")
print("PASS")
