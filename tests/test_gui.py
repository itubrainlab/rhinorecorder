"""The window on the simulated headset, without a display."""
import time

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rhinorecorder.recorder import IDLE, RUNNING  # noqa: E402
from rhinorecorder.simulator import SIMULATED_SERIAL  # noqa: E402


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
    from rhinorecorder.ui.connect_dialog import Choice
    from rhinorecorder.ui.main_window import MainWindow

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
    from rhinorecorder.ui.scope import trigger_colour

    colours = [trigger_colour(v).name() for v in range(1, 11)]
    assert len(set(colours)) == 10
    assert trigger_colour(3).name() == trigger_colour(3.0).name()


def test_trigger_row(app):
    import numpy as np

    from rhinorecorder.ui.scope import TRIGGER_ROW, Scope, trigger_colour

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


def test_power_spectrum(app, settings, monkeypatch):
    import numpy as np

    from rhinorecorder.ui.connect_dialog import Choice
    from rhinorecorder.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_save_settings", lambda self: None)
    window = MainWindow(settings, Choice(SIMULATED_SERIAL, "", "auto", True))
    window.show()
    try:
        assert window.spectrum_panel.isVisible()
        # Square by default, also after the window is resized ...
        for size in ((1500, 760), (1700, 900)):
            window.resize(*size)
            wait_for(app, lambda: abs(window.spectrum.width()
                                      - window.spectrum.height()) <= 2)
        assert window.spectrum.width() > 500
        assert [r.getRegion() for r in window.spectrum.band_regions] == [
            (0.5, 4.0), (4.0, 8.0), (8.0, 13.0), (13.0, 30.0), (30.0, 100.0)]
        # ... until the user drags the divider.
        window.splitter.splitterMoved.emit(700, 1)
        window.splitter.setSizes([1000, 300])
        window.resize(1300, 800)
        app.processEvents()
        assert window.splitter.sizes()[1] < 500
        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == RUNNING
                 and not window._busy)
        wait_for(app, lambda: window.recorder.graph.status.total > 300)
        window._update_status()
        freqs, db = window.spectrum.curve.getOriginalDataset()
        assert freqs[0] == 0 and freqs[-1] == 100
        assert np.isfinite(db).all()

        # Hidden, it is remembered in the settings, and shown again.
        window.spectrum_box.setChecked(False)
        assert not window.spectrum_panel.isVisible()
        assert settings.display.spectrum is False
        window.spectrum_box.setChecked(True)
        assert window.spectrum_panel.isVisible()

        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == IDLE
                 and not window._busy)
    finally:
        window.close()


def test_power_spectrum_follows_the_filter(app, settings, monkeypatch):
    import numpy as np

    from rhinorecorder.ui.connect_dialog import Choice
    from rhinorecorder.ui.main_window import MainWindow

    monkeypatch.setattr(MainWindow, "_save_settings", lambda self: None)
    settings.display.filter = "< 20 Hz"
    settings.display.notch = "None"
    window = MainWindow(settings, Choice(SIMULATED_SERIAL, "", "auto", True))
    window.show()
    try:
        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == RUNNING
                 and not window._busy)
        wait_for(app, lambda: window.recorder.graph.scope.total > 750)
        window._update_status()
        freqs, db = window.spectrum.curve.getOriginalDataset()
        passed = db[(freqs >= 5) & (freqs <= 15)].mean()
        stopped = db[freqs >= 60].mean()
        # A 4th-order lowpass at 20 Hz: tens of dB down above 60 Hz.
        assert stopped < passed - 20, (passed, stopped)

        # Raw: the whole band is back.
        assert not window.spectrum_source.is_raw()
        window.spectrum_source.raw.click()
        freqs, db = window.spectrum.curve.getOriginalDataset()
        assert db[freqs >= 60].mean() > passed - 20

        # The data viewer's switch is its own; raw, each channel is
        # centred on its row despite the electrode offsets.
        assert not window.scope_source.is_raw()
        window.scope_source.raw.click()
        for row, curve in enumerate(window.scope.curves):
            _, y = curve.getData()
            centre = window.scope.channels - row - 0.5
            assert abs(np.nanmedian(y) - centre) < 0.25

        window.play_button.click()
        wait_for(app, lambda: window.recorder.state == IDLE
                 and not window._busy)
    finally:
        window.close()
