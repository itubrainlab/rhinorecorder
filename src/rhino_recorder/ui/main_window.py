"""The main window: a toolbar with the acquisition and processing
controls and the status icons, the data viewer and signal quality scope,
and the settings view."""
from __future__ import annotations

import threading
import time
from collections import deque
from importlib import resources

from PySide6.QtCore import QObject, QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                               QPushButton, QStackedWidget,
                               QTextBrowser, QToolButton, QVBoxLayout,
                               QWidget)

from .. import layout, presets, quality
from ..power import KeepAwake
from ..recorder import IDLE, RUNNING, STARTING, STOPPING, Recorder
from ..settings import Settings
from . import icons, theme
from .connect_dialog import Choice
from .scope import Scope
from .settings_view import SettingsView

SCOPE_INTERVAL_MS = 40

OSCAR_TIP = ("OSCAR removes motion, cable, blink and other artifacts. "
             "g.Pype runs it at the source, so it applies to raw and "
             "processed outputs alike and delays the data by about a third "
             "of a second. Switching it restarts acquisition.")
STATUS_INTERVAL_MS = 500


class _Bridge(QObject):
    """Carries recorder events from worker threads to the GUI thread."""
    state = Signal(str)
    error = Signal(str)
    recording = Signal(bool)
    task_failed = Signal(str, str)
    task_done = Signal()


def _tool(icon, tip: str, size: int = 26) -> QToolButton:
    button = QToolButton()
    button.setIcon(icon)
    button.setIconSize(QSize(size, size))
    button.setToolTip(tip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _combo(items, current: str) -> QComboBox:
    combo = QComboBox()
    combo.addItems(list(items))
    combo.setCurrentText(current)
    combo.setMinimumWidth(110)
    return combo


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedSize(1, 26)
    return line


def _panel(title: str, content: QWidget) -> QGroupBox:
    """Content in a titled group box, as g.Pype widgets are shown."""
    box = QGroupBox(title)
    column = QVBoxLayout(box)
    column.setContentsMargins(8, 8, 8, 8)
    column.addWidget(content)
    return box


class MainWindow(QMainWindow):
    """Emits ``disconnected`` after the user has let go of the headset."""

    disconnected = Signal()

    def __init__(self, settings: Settings, choice: Choice):
        super().__init__()
        self.settings = settings
        self.choice = choice
        if not choice.simulate:
            # The window acquires from the headset it was opened for.
            settings.device.serial = choice.serial
            settings.device.port = choice.port
            settings.device.transport = choice.transport
        self.recorder = Recorder(settings, simulate=choice.simulate)
        self.quality = quality.SignalQuality()
        self._quality_seen = 0
        self._busy = False
        self._recording_since: float | None = None
        self._closing = False
        #: (time, samples lost so far), for the last few seconds.
        self._losses: deque = deque()
        self._awake = KeepAwake()

        bridge = self._bridge = _Bridge()
        bridge.state.connect(self._on_state)
        bridge.error.connect(self._on_error)
        bridge.recording.connect(self._on_recording)
        bridge.task_failed.connect(self._on_task_failed)
        bridge.task_done.connect(self._on_task_done)
        self.recorder.on_state = bridge.state.emit
        self.recorder.on_error = bridge.error.emit
        self.recorder.on_recording = bridge.recording.emit

        self.setWindowTitle("Rhino Recorder")
        self.resize(1100, 720)
        central = QWidget()
        column = QVBoxLayout(central)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._toolbar())
        self.stack = QStackedWidget()
        self.stack.addWidget(self._acquisition_view())
        self.settings_view = SettingsView(settings, self._device_info())
        self.settings_view.network_changed.connect(self._refresh_network)
        self.stack.addWidget(self.settings_view)
        column.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.status_left = QLabel()
        self.status_right = QLabel()
        self.statusBar().addWidget(self.status_left, 1)
        self.statusBar().addPermanentWidget(self.status_right)

        self.scope_timer = QTimer(self)
        self.scope_timer.timeout.connect(self._update_scope)
        self.scope_timer.start(SCOPE_INTERVAL_MS)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start(STATUS_INTERVAL_MS)
        self._refresh_network()
        self._update_controls()
        self._update_status()

    # -- layout ----------------------------------------------------------------

    def _toolbar(self) -> QWidget:
        """One bar, as g.Pype applications have: acquisition controls,
        processing controls, then the status icons."""
        bar = QFrame()
        bar.setObjectName("Toolbar")
        bar.setFixedHeight(48)
        row = QHBoxLayout(bar)
        row.setContentsMargins(12, 4, 12, 4)
        row.setSpacing(4)
        brand = QLabel("Rhino")
        brand.setObjectName("Brand")
        sub = QLabel("Recorder")
        sub.setObjectName("BrandSub")
        row.addWidget(brand)
        row.addWidget(sub)
        row.addSpacing(10)
        row.addWidget(_divider())
        row.addSpacing(6)

        self.play_button = _tool(icons.play(), "Start acquisition", 18)
        self.play_button.clicked.connect(self._toggle_acquisition)
        self.record_button = _tool(icons.record(), "Start recording", 18)
        self.record_button.clicked.connect(self._toggle_recording)
        self.settings_button = _tool(icons.gear(), "Settings", 18)
        self.settings_button.setCheckable(True)
        self.settings_button.clicked.connect(self._toggle_settings)
        for button in (self.play_button, self.record_button,
                       self.settings_button):
            row.addWidget(button)
        row.addSpacing(6)
        row.addWidget(_divider())
        row.addSpacing(6)

        self.display_controls = QWidget()
        controls = QHBoxLayout(self.display_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        display = self.settings.display
        self.scaling = _combo(presets.SCALINGS, display.scaling)
        self.scaling.currentTextChanged.connect(self._on_scaling)
        self.filter = _combo(presets.FILTERS, display.filter)
        self.filter.currentTextChanged.connect(self.recorder.set_filter)
        self.notch = _combo(presets.NOTCHES, display.notch)
        self.notch.currentTextChanged.connect(self.recorder.set_notch)
        self.oscar = QCheckBox("OSCAR")
        self.oscar.setChecked(display.oscar)
        self.oscar.setToolTip(OSCAR_TIP)
        self.oscar.toggled.connect(self._on_oscar)
        for text, widget in (("Scaling", self.scaling),
                             ("Filter", self.filter),
                             ("Notch", self.notch)):
            controls.addWidget(QLabel(text))
            controls.addWidget(widget)
            controls.addSpacing(10)
        controls.addWidget(self.oscar)
        row.addWidget(self.display_controls)
        row.addStretch(1)

        self.wifi_icon = _tool(icons.wifi(theme.ICON_DISABLED),
                               "Wireless data loss", 22)
        self.network_icon = _tool(icons.network(theme.ICON_DISABLED),
                                  "Network interfaces", 22)
        self.battery_icon = _tool(icons.battery(None, theme.ICON_DISABLED),
                                  "Battery level", 24)
        self.network_icon.clicked.connect(
            lambda: self._show_settings_page(2))
        self.link_button = _tool(icons.link(), "Disconnect", 22)
        self.link_button.clicked.connect(self._disconnect)
        self.help_button = _tool(icons.question(), "User manual", 18)
        self.help_button.clicked.connect(self._show_help)
        for widget in (self.wifi_icon, self.network_icon, self.battery_icon):
            row.addWidget(widget)
        row.addSpacing(6)
        row.addWidget(_divider())
        row.addSpacing(6)
        row.addWidget(self.link_button)
        row.addWidget(self.help_button)
        return bar

    def _acquisition_view(self) -> QWidget:
        """The data viewer, with each channel's signal quality beside it,
        in a g.Pype panel."""
        view = QWidget()
        row = QHBoxLayout(view)
        row.setContentsMargins(10, 4, 10, 10)
        self.scope = Scope()
        self.scope.set_scale(presets.SCALINGS[self.settings.display.scaling])
        row.addWidget(_panel("Data Viewer", self.scope), 1)
        return view

    def _device_info(self) -> dict:
        try:
            import gpype
            gpype_version = gpype.__version__
        except Exception:  # noqa: BLE001
            gpype_version = "?"
        try:
            import gprhino
            driver = f"gpype-rhino {gprhino.__version__}"
        except Exception:  # noqa: BLE001
            driver = "gpype-rhino"
        if self.choice.simulate:
            connection = "simulated"
        else:
            parts = [self.choice.transport]
            if self.choice.port:
                parts.append(self.choice.port)
            connection = ", ".join(parts)
        return {"serial": self.choice.serial, "connection": connection,
                "driver": driver, "gpype": gpype_version}

    # -- actions ---------------------------------------------------------------

    def _run(self, what: str, work) -> None:
        """Run blocking recorder work off the GUI thread."""
        if self._busy:
            return
        self._busy = True
        self._update_controls()

        def task():
            try:
                work()
            except Exception as error:  # noqa: BLE001
                self._bridge.task_failed.emit(what, str(error))
            finally:
                # Cleared on the GUI thread, together with the buttons.
                self._bridge.task_done.emit()
        threading.Thread(target=task, daemon=True).start()

    def _on_task_done(self) -> None:
        self._busy = False
        self._on_state(self.recorder.state)

    def _toggle_acquisition(self) -> None:
        if self.recorder.state == IDLE:
            if self._leave_settings():
                self._run("start acquisition", self.recorder.start)
        else:
            self._run("stop acquisition", self.recorder.stop)

    def _toggle_recording(self) -> None:
        recorder = self.recorder
        if recorder.state == IDLE:
            if self._leave_settings():
                self._run("start recording",
                          lambda: recorder.start(record=True))
        elif recorder.recording:
            self._run("stop recording", recorder.stop_recording)
        elif recorder.state == RUNNING:
            self._run("start recording", recorder.start_recording)

    def _toggle_settings(self) -> None:
        if self.stack.currentIndex() == 0:
            self.stack.setCurrentIndex(1)
        elif not self._leave_settings():
            self.settings_button.setChecked(True)
        self._update_controls()

    def _show_settings_page(self, index: int) -> None:
        if self.recorder.state != IDLE:
            return
        self.settings_view.show_page(index)
        self.stack.setCurrentIndex(1)
        self._update_controls()

    def _leave_settings(self) -> bool:
        """Back to the data viewer, if the settings are usable."""
        if self.stack.currentIndex() == 0:
            return True
        problems = self.settings.problems()
        if problems:
            QMessageBox.warning(self, "Settings", "\n".join(problems))
            return False
        self._save_settings()
        self.stack.setCurrentIndex(0)
        self._refresh_network()
        self._update_controls()
        return True

    def _on_scaling(self, name: str) -> None:
        self.settings.display.scaling = name
        self.scope.set_scale(presets.SCALINGS[name])

    def _on_oscar(self, on: bool) -> None:
        if on == self.settings.display.oscar:
            return
        recorder = self.recorder
        # Switching OSCAR restarts acquisition, which cannot happen while
        # recording or while acquisition is already starting or stopping.
        # The box is disabled then; this guards a click that raced it.
        if (recorder.recording or self._busy
                or recorder.state in (STARTING, STOPPING)):
            self._sync_oscar()
            return
        self.settings.display.oscar = on
        if recorder.state == RUNNING:
            def restart():
                recorder.stop()
                recorder.start()
            self._run("restart acquisition", restart)

    def _disconnect(self) -> None:
        if self.recorder.recording:
            answer = QMessageBox.question(
                self, "Disconnect", "A recording is running. Stop it and "
                "disconnect?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._closing = True
        self._shutdown()
        self.disconnected.emit()
        self.close()

    def _show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Rhino Recorder user manual")
        dialog.resize(760, 640)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        try:
            text = resources.files("rhino_recorder").joinpath(
                "MANUAL.md").read_text(encoding="utf-8")
        except (OSError, FileNotFoundError):
            text = "# Rhino Recorder\n\nThe manual was not installed."
        browser.setMarkdown(text)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        column = QVBoxLayout(dialog)
        column.addWidget(browser)
        column.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    # -- recorder events ---------------------------------------------------------

    def _on_state(self, state: str) -> None:
        if state == IDLE:
            self._awake.release()
        else:
            self._awake.hold()
        if state == RUNNING:
            self.settings_view.refresh_device(
                serial=self.recorder.device_serial)
        if state == STARTING:
            self._losses.clear()
            self.quality.reset()
            self._quality_seen = 0
            self.scope.clear()
        if state == IDLE:
            self._recording_since = None
        self._update_controls()
        self._update_status()

    def _on_recording(self, on: bool) -> None:
        self._recording_since = time.monotonic() if on else None
        self._update_controls()
        self._update_status()

    def _on_error(self, message: str) -> None:
        if self._closing:
            return
        QMessageBox.critical(self, "Acquisition stopped", message)

    def _on_task_failed(self, what: str, message: str) -> None:
        if self._closing:
            return
        box = QMessageBox(QMessageBox.Icon.Critical, "Rhino Recorder",
                          f"Could not {what}.", QMessageBox.StandardButton.Ok,
                          self)
        box.setInformativeText(message)
        box.exec()

    # -- periodic updates ----------------------------------------------------------

    def _update_controls(self) -> None:
        state = self.recorder.state
        busy = self._busy or state in (STARTING, STOPPING)
        idle = state == IDLE and not busy
        running = state == RUNNING
        recording = self.recorder.recording
        in_settings = self.stack.currentIndex() == 1

        self.play_button.setIcon(icons.play() if state == IDLE
                                 else icons.stop())
        self.play_button.setToolTip("Start acquisition" if state == IDLE
                                    else "Stop acquisition")
        self.play_button.setEnabled(not busy)
        self.record_button.setIcon(icons.record(theme.RECORDING if recording
                                                else theme.ICON))
        self.record_button.setToolTip("Stop recording" if recording
                                      else "Start recording")
        self.record_button.setEnabled(not busy and (idle or running))
        self.settings_button.setEnabled(idle)
        self.settings_button.setChecked(in_settings)
        self.display_controls.setVisible(not in_settings)
        self.link_button.setEnabled(not busy)
        self.oscar.setEnabled(not busy and not recording)
        self.oscar.setToolTip(OSCAR_TIP + ("\n\nStop recording to switch "
                                           "OSCAR." if recording else ""))
        self._sync_oscar()

    def _sync_oscar(self) -> None:
        """Show the OSCAR setting in the box without acting on it."""
        self.oscar.blockSignals(True)
        self.oscar.setChecked(self.settings.display.oscar)
        self.oscar.blockSignals(False)

    def _refresh_network(self) -> None:
        on = self.settings.network.any_enabled()
        self.network_icon.setIcon(icons.network(
            theme.ICON_ACTIVE if on else theme.ICON_DISABLED))
        net = self.settings.network
        lines = [f"{name}: {'on' if s.enabled else 'off'}"
                 for name, s in (("Trigger UDP input", net.trigger_in),
                                 ("Raw UDP output", net.raw_udp),
                                 ("Raw LSL output", net.raw_lsl),
                                 ("Processed UDP output", net.processed_udp),
                                 ("Processed LSL output", net.processed_lsl))]
        self.network_icon.setToolTip("Network interfaces\n" + "\n".join(lines))

    def _update_scope(self) -> None:
        graph = self.recorder.graph
        if graph is None or self.stack.currentIndex() != 0:
            return
        buffer, total = graph.scope.sweep()
        self.scope.show_sweep(buffer, total, layout.EEG, layout.TRIGGER_CHANNEL)

    def _update_status(self) -> None:
        recorder = self.recorder
        graph = recorder.graph
        serial = (recorder.device_serial or self.choice.serial
                  or "Unicorn")
        if graph is None:
            self.wifi_icon.setIcon(icons.wifi(theme.ICON_DISABLED))
            self.wifi_icon.setToolTip("Wireless data loss: not acquiring")
            self.battery_icon.setIcon(icons.battery(None,
                                                    theme.ICON_DISABLED))
            self.battery_icon.setToolTip("Battery level: not acquiring")
            self.scope.set_quality([quality.UNKNOWN] * layout.NUM_EEG)
            text = {IDLE: f"{serial}: ready",
                    STARTING: f"Connecting to {serial}...",
                    STOPPING: "Stopping..."}.get(recorder.state, "")
            self.status_left.setText(text)
            self.status_right.setText("")
            return

        tap = graph.status
        recent = tap.latest(1)
        lost = recorder.lost_scans
        now = time.monotonic()
        self._losses.append((now, lost))
        while self._losses and self._losses[0][0] < now - 3:
            self._losses.popleft()
        if len(recent):
            losing = lost > self._losses[0][1]
            self.wifi_icon.setIcon(icons.wifi(theme.WARNING if losing
                                              else theme.ICON_ACTIVE))
            self.wifi_icon.setToolTip(
                "Wireless data loss: "
                + ("samples are being lost" if losing else "none recently")
                + f"\n{lost} samples lost since acquisition started")
            level = float(recent[-1, layout.BAT])
            self.battery_icon.setIcon(icons.battery(level))
            self.battery_icon.setToolTip(f"Battery level: {level:.0f} %")

        new = tap.total - self._quality_seen
        if new > 0:
            fresh = tap.latest(new)
            self.quality.update(fresh[:, layout.EEG])
            self._quality_seen = tap.total
        self.scope.set_quality(self.quality.verdicts(),
                               self.quality.deviation())

        if recorder.recording and self._recording_since is not None:
            elapsed = int(time.monotonic() - self._recording_since)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            files = len(recorder.recording_paths)
            self.status_left.setText(
                f"{serial}: recording {h:02d}:{m:02d}:{s:02d} "
                f"({files} file{'s' if files != 1 else ''})")
            self.status_left.setToolTip("\n".join(recorder.recording_paths))
        else:
            seconds = tap.total / layout.SAMPLING_RATE
            oscar = getattr(graph.source, "_oscar_node", None) is not None
            self.status_left.setText(f"{serial}: acquiring, "
                                     f"{seconds:.0f} s"
                                     + (", OSCAR on" if oscar else ""))
            self.status_left.setToolTip("")
        self.status_right.setText("Non-commercial use (g.Pype)"
                                  if recorder.marked else "")

    # -- shutdown --------------------------------------------------------------------

    def _save_settings(self) -> None:
        try:
            self.settings.save()
        except OSError:
            pass

    def _shutdown(self) -> None:
        self.scope_timer.stop()
        self.status_timer.stop()
        try:
            self.recorder.stop()
        except Exception:  # noqa: BLE001
            pass
        self._awake.release()
        self._save_settings()

    def closeEvent(self, event):
        if not self._closing:
            if self.recorder.recording:
                answer = QMessageBox.question(
                    self, "Quit", "A recording is running. Stop it and "
                    "quit?")
                if answer != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
            self._closing = True
            self._shutdown()
        super().closeEvent(event)
