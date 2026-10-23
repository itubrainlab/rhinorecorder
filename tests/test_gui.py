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


def test_trigger_colours_are_stable_and_distinct():
    from rhino_recorder.ui.scope import trigger_colour

    colours = [trigger_colour(v).name() for v in range(1, 11)]
    assert len(set(colours)) == 10
    assert trigger_colour(3).name() == trigger_colour(3.0).name()


def test_trigger_row(app):
    import numpy as np

    from rhino_recorder.ui.scope import TRIGGER_ROW, Scope, trigger_colour

    scope = Scope()
    scope.resize(1000, 600)
    scope.show_triggers(np.array([1.0, 2.0, 2.01, 5.0]),
                        np.array([3, 7, 99, 3]))
    # One tick and marker item per value, in that value's colour.
    assert set(scope._trigger_items) == {3, 7, 99}
    ticks, _ = scope._trigger_items[3]
    assert ticks.opts["pen"].color().rgb() == trigger_colour(3).rgb()
    xs, ys = ticks.getData()
    assert list(xs[::3]) == [1.0, 5.0]
    assert list(ys[:2]) == [0.0, float(scope.channels)]
    # A label per trigger; the two close ones on different lines.
    labels = [label for label in scope._trigger_labels if label.isVisible()]
    assert [label.toPlainText() for label in labels] == ["3", "7", "99", "3"]
    heights = [label.pos().y() for label in labels]
    assert heights[1] != heights[2]
    assert all(-TRIGGER_ROW < h < 0 for h in heights)
    # Clearing hides them all.
    scope.show_triggers([], [])
    assert not any(label.isVisible() for label in scope._trigger_labels)
    cleared = scope._trigger_items[3][0].getData()[0]
    assert cleared is None or len(cleared) == 0
