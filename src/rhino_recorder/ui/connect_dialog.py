"""Choosing and opening a headset, the step Unicorn Suite does before it
starts Unicorn Recorder."""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressDialog,
                               QPushButton, QVBoxLayout)

from ..settings import Settings
from ..simulator import SIMULATED_SERIAL

SIMULATED = "Simulated device"
FAILED_TEXT = ("Could not connect to the Unicorn. Make sure that the device "
               "is turned on, in range and paired with this computer.")


@dataclass
class Choice:
    serial: str
    port: str
    transport: str
    simulate: bool


def paired_devices() -> list[tuple[str, str, str]]:
    """(label, serial, port) of every paired headset found."""
    try:
        from gprhino import find_ports
        ports = find_ports()
    except Exception:  # noqa: BLE001
        return []
    found = []
    for port in ports:
        name = port.rsplit("/", 1)[-1]
        for prefix in ("cu.", "tty."):
            if name.startswith(prefix):
                name = name[len(prefix):]
        if sys.platform == "darwin":
            # The macOS bridge finds the headset by name; dots optional.
            found.append((name, name, ""))
        else:
            found.append((port, "", port))
    return found


def probe(choice: Choice) -> None:
    """Connect to the headset and let it go again.

    Raises:
        ConnectionError: If it does not answer.
    """
    if choice.simulate:
        return
    from gprhino import RhinoDevice
    device = RhinoDevice(choice.serial or None, port=choice.port or None,
                         transport=choice.transport or "auto")
    device.start()
    device.stop()


class _Relay(QObject):
    done = Signal(object)


class ConnectDialog(QDialog):

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.choice: Choice | None = None
        self.setWindowTitle("Rhino Recorder")
        self.setMinimumWidth(460)

        self.devices = QComboBox()
        self.devices.setEditable(True)
        self.devices.setToolTip(
            "The headset's Bluetooth name, e.g. UN-2024.08.41. Leave it "
            "empty for the first paired headset.")
        self.port = QLineEdit(settings.device.port)
        self.port.setPlaceholderText(
            "/dev/rfcomm0" if sys.platform.startswith("linux") else
            "COM5" if sys.platform == "win32" else "not needed on macOS")
        self.transport = QComboBox()
        self.transport.addItems(["auto", "serial", "bridge"])
        self.transport.setCurrentText(settings.device.transport or "auto")
        self._refresh()

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("Primary")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self._open)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.reject)

        intro = QLabel("Select the Unicorn Hybrid Black to open. Pair it in "
                       "the system's Bluetooth settings first"
                       + (", and bind it with rfcomm." if
                          sys.platform.startswith("linux") else "."))
        intro.setWordWrap(True)
        form = QFormLayout()
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices, 1)
        device_row.addWidget(refresh)
        form.addRow("Device:", device_row)
        form.addRow("Serial port:", self.port)
        form.addRow("Transport:", self.transport)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(quit_button)
        buttons.addWidget(self.open_button)
        column = QVBoxLayout(self)
        column.addWidget(intro)
        column.addLayout(form)
        column.addLayout(buttons)

        self._relay = _Relay()
        self._relay.done.connect(self._probed)
        self._progress: QProgressDialog | None = None

    def _refresh(self) -> None:
        current = self.devices.currentText() or self.settings.device.serial
        self.devices.clear()
        for label, serial, port in paired_devices():
            self.devices.addItem(label, (serial, port))
        self.devices.addItem(SIMULATED, (SIMULATED_SERIAL, ""))
        if current:
            index = self.devices.findText(current)
            if index >= 0:
                self.devices.setCurrentIndex(index)
            else:
                self.devices.setEditText(current)

    def current_choice(self) -> Choice:
        text = self.devices.currentText().strip()
        index = self.devices.findText(text)
        serial, port = (self.devices.itemData(index) if index >= 0
                        else (text, ""))
        if text == SIMULATED:
            return Choice(SIMULATED_SERIAL, "", "auto", True)
        port = self.port.text().strip() or port
        return Choice(serial, port, self.transport.currentText(), False)

    def _open(self) -> None:
        choice = self.current_choice()
        self.open_button.setEnabled(False)
        self._progress = QProgressDialog(
            f"Connecting to {choice.serial or choice.port or 'the Unicorn'}"
            f"...", None, 0, 0, self)
        self._progress.setWindowTitle("Rhino Recorder")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.show()

        def work():
            try:
                probe(choice)
                self._relay.done.emit((choice, None))
            except Exception as error:  # noqa: BLE001
                self._relay.done.emit((choice, error))
        threading.Thread(target=work, daemon=True).start()

    def _probed(self, result) -> None:
        choice, error = result
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        self.open_button.setEnabled(True)
        if error is not None:
            box = QMessageBox(QMessageBox.Icon.Critical, "Connection failed",
                              FAILED_TEXT, QMessageBox.StandardButton.Ok,
                              self)
            box.setInformativeText(str(error))
            box.exec()
            return
        self.choice = choice
        if not choice.simulate:
            self.settings.device.serial = choice.serial
            self.settings.device.port = choice.port
            self.settings.device.transport = choice.transport
        self.accept()
