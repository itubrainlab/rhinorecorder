"""The window on the simulated headset, without a display."""
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rhino_recorder.recorder import IDLE, RUNNING  # noqa: E402
from rhino_recorder.simulator import SIMULATED_SERIAL  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_for(app, condition, timeout=10.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise TimeoutError
        app.processEvents()
        time.sleep(0.02)


def test_play_record_stop(app, settings, monkeypatch):
    from rhino_recorder.ui.connect_dialog import Choice
    from rhino_recorder.ui.main_window import MainWindow

    from PySide6.QtWidgets import QMessageBox

    # A modal box would wait forever without a display.
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: 0)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: 0)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: 0)
    monkeypatch.setattr(MainWindow, "_save_settings", lambda self: None)
    window = MainWindow(settings, Choice(SIMULATED_SERIAL, "", "auto", True))
    window.show()
    try:
        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == RUNNING
                 and not window._busy)
        assert not window.settings_button.isEnabled()
        wait_for(app, lambda: window.recorder.graph.scope.total > 250)
        window._update_scope()
        window._update_status()
        assert window.scope.cursor.isVisible()

        window.record_button.click()
        wait_for(app, lambda: window.recorder.recording and not window._busy)
        app.processEvents()
        window._update_status()
        assert "recording" in window.status_left.text()

        window.filter.setCurrentText("2 – 30 Hz")
        assert settings.display.filter == "2 – 30 Hz"

        # OSCAR cannot be switched while recording.
        assert not window.oscar.isEnabled()

        window.record_button.click()
        wait_for(app, lambda: not window.recorder.recording
                 and not window._busy)
        app.processEvents()

        # Switching OSCAR while acquiring restarts acquisition with it.
        assert window.oscar.isEnabled()
        window.oscar.setChecked(True)
        assert not window.oscar.isEnabled()        # disabled while restarting
        wait_for(app, lambda: window.recorder.state == RUNNING
                 and not window._busy)
        assert window.recorder.graph.source._oscar_node is not None
        window.oscar.setChecked(False)
        wait_for(app, lambda: window.recorder.state == RUNNING
                 and not window._busy)
        assert window.recorder.graph.source._oscar_node is None
        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == IDLE
                 and not window._busy)
        assert window.settings_button.isEnabled()

        window.settings_button.click()
        assert window.stack.currentIndex() == 1
        window.settings_button.click()
        assert window.stack.currentIndex() == 0
    finally:
        window.close()
