"""The settings view: Acquisition, Recording, Network and Device pages,
each editing the shared :class:`~rhino_recorder.settings.Settings` in
place."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QScrollArea, QSpinBox,
                               QTabWidget, QVBoxLayout, QWidget)

from .. import __version__
from ..settings import Settings

PAGES = ("Acquisition", "Recording", "Network", "Device")

DRIVER_NOTE = ("gpype_rhino talks to the headset's Bluetooth serial "
               "channel directly. It does not implement the commands for "
               "the test signal, the digital outputs or the firmware "
               "version, so those are not available here.")


def _group(column: QVBoxLayout, title: str) -> QFormLayout:
    """A titled g.Pype group box added to ``column``; returns its form."""
    box = QGroupBox(title)
    form = _form()
    form.setContentsMargins(10, 10, 10, 10)
    box.setLayout(form)
    column.addWidget(box)
    return form


def _check(obj, attr: str, changed=None) -> QCheckBox:
    box = QCheckBox()
    box.setChecked(getattr(obj, attr))

    def apply(state):
        setattr(obj, attr, box.isChecked())
        if changed:
            changed()
    box.toggled.connect(apply)
    return box


def _text(obj, attr: str, width: int | None = None) -> QLineEdit:
    edit = QLineEdit(getattr(obj, attr))
    if width:
        edit.setFixedWidth(width)
    edit.textChanged.connect(lambda text: setattr(obj, attr, text))
    return edit


def _port(obj, attr: str) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(1, 65535)
    spin.setValue(getattr(obj, attr))
    spin.setFixedWidth(140)
    spin.valueChanged.connect(lambda value: setattr(obj, attr, value))
    return spin


def _folder(obj, attr: str, parent: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    edit = _text(obj, attr)
    browse = QPushButton("...")

    def choose():
        folder = QFileDialog.getExistingDirectory(parent, "Folder path",
                                                  edit.text())
        if folder:
            edit.setText(folder)
    browse.clicked.connect(choose)
    layout.addWidget(edit, 1)
    layout.addWidget(browse)
    return row


def _page() -> tuple[QScrollArea, QVBoxLayout]:
    content = QWidget()
    column = QVBoxLayout(content)
    column.setContentsMargins(12, 12, 12, 12)
    column.setSpacing(4)
    column.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll, column


class _Form(QFormLayout):
    """A form whose label column has the same width on every page, so
    the fields of consecutive sections line up."""

    LABEL_WIDTH = 230

    def __init__(self):
        super().__init__()
        self.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self.setHorizontalSpacing(12)

    def addRow(self, text, field):  # noqa: N802 - Qt's name
        label = QLabel(text)
        label.setFixedWidth(self.LABEL_WIDTH)
        super().addRow(label, field)


def _form() -> QFormLayout:
    return _Form()


class SettingsView(QWidget):
    """Emits ``network_changed`` when a network output is switched, so
    the status icon can follow."""

    network_changed = Signal()

    def __init__(self, settings: Settings, device_info: dict, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.device_info = device_info
        self.tabs = QTabWidget()
        for title, page in zip(PAGES, (self._acquisition(),
                                       self._recording(), self._network(),
                                       self._device())):
            self.tabs.addTab(page, title)
        column = QVBoxLayout(self)
        column.setContentsMargins(10, 8, 10, 10)
        column.addWidget(self.tabs)

    def show_page(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)

    def _acquisition(self) -> QWidget:
        acq = self.settings.acquisition
        scroll, column = _page()
        form = _group(column, "Electrode input source")
        source = QComboBox()
        source.addItems(["electrode", "test signal"])
        source.setFixedWidth(200)
        model = source.model()
        if isinstance(model, QStandardItemModel):
            test = model.item(1)
            test.setEnabled(False)
            test.setToolTip(DRIVER_NOTE)
        source.setToolTip("The test signal is not available over "
                          "gpype_rhino.")
        form.addRow("Input source:", source)
        form = _group(column, 
            "Include or exclude signals from data acquisition")
        for text, attr in (("Accelerometer", "accelerometer"),
                           ("Gyroscope", "gyroscope"),
                           ("Battery Level", "battery"),
                           ("Counter", "counter"),
                           ("Validation Indicator", "validation"),
                           ("Timing", "timing")):
            form.addRow(text, _check(acq, attr))
        note = QLabel("Included signals are written to files and network "
                      "streams. EEG and the TRIGGER channel are "
                      "always included.")
        note.setWordWrap(True)
        note.setObjectName("Note")
        column.addWidget(note)
        return scroll

    def _recording(self) -> QWidget:
        rec = self.settings.recording
        scroll, column = _page()
        for title, logger, bdf in (
                ("Raw Data CSV Logger Settings", rec.raw_csv, False),
                ("Raw Data BDF Logger Settings", rec.raw_bdf, True),
                ("Processed Data CSV Logger Settings", rec.processed_csv,
                 False),
                ("Processed Data BDF Logger Settings", rec.processed_bdf,
                 True)):
            form = _group(column, title)
            form.addRow("Enabled", _check(logger, "enabled"))
            form.addRow("Folder path", _folder(logger, "folder", self))
            form.addRow("File prefix", _text(logger, "prefix"))
            if bdf:
                form.addRow("Local subject identification",
                            _text(logger, "subject_id"))
                form.addRow("Local recording identification",
                            _text(logger, "recording_id"))
        return scroll

    def _network(self) -> QWidget:
        net = self.settings.network
        changed = self.network_changed.emit
        scroll, column = _page()
        for title, endpoint in (
                ("Trigger UDP Input Settings", net.trigger_in),
                ("Raw Data UDP Output Settings", net.raw_udp),
                ("Raw Data LSL Output Settings", net.raw_lsl),
                ("Processed Data UDP Output Settings", net.processed_udp),
                ("Processed Data LSL Output Settings", net.processed_lsl)):
            form = _group(column, title)
            form.addRow("Enabled", _check(endpoint, "enabled", changed))
            if hasattr(endpoint, "ip"):
                form.addRow("IP", _text(endpoint, "ip", 240))
                form.addRow("Port", _port(endpoint, "port"))
            else:
                form.addRow("Streamname", _text(endpoint, "name", 300))
        note = QLabel("The port used for the Trigger UDP Input must differ "
                      "from the ports used for data outputs. On macOS, a "
                      "trigger port below 1024 on 127.0.0.1 listens on all "
                      "network interfaces, the only way macOS allows it; "
                      "on Linux such a port needs administrator rights.")
        note.setWordWrap(True)
        note.setObjectName("Note")
        column.addWidget(note)
        return scroll

    def _device(self) -> QWidget:
        scroll, column = _page()
        form = _group(column, "Device Information")
        self._info_labels = {}
        for key in ("Serial number", "Device", "Connection",
                    "Firmware version", "Driver version", "g.Pype version",
                    "RhinoRecorder version"):
            label = QLabel()
            label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            self._info_labels[key] = label
            form.addRow(f"{key}:", label)
        self.refresh_device()
        form = _group(column, "Digital outputs")
        for i in range(8):
            toggle = QCheckBox("OFF")
            toggle.setEnabled(False)
            form.addRow(f"Digital Out {i}:", toggle)
        note = QLabel(DRIVER_NOTE)
        note.setWordWrap(True)
        note.setObjectName("Note")
        column.addWidget(note)
        return scroll

    def refresh_device(self, **updates) -> None:
        self.device_info.update(updates)
        info = self.device_info
        values = {
            "Serial number": info.get("serial") or "(first paired headset)",
            "Device": "Unicorn Hybrid Black",
            "Connection": info.get("connection", ""),
            "Firmware version": "not reported by gpype_rhino",
            "Driver version": info.get("driver", ""),
            "g.Pype version": info.get("gpype", ""),
            "RhinoRecorder version": __version__,
        }
        for key, value in values.items():
            self._info_labels[key].setText(value)
