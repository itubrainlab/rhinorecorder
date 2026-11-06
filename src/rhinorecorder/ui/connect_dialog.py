"""Choosing and opening a headset, the step Unicorn Suite does before it
starts Unicorn Recorder."""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout,
                               QLabel, QMessageBox, QProgressDialog,
                               QPushButton, QVBoxLayout)

from ..settings import Settings
from ..simulator import SIMULATED_SERIAL

SIMULATED = "Simulated device"
FAILED_TEXT = ("Could not connect to the Unicorn. Make sure that the device "
               "is turned on, in range and paired with this computer.")


@dataclass
class Choice:
    #: The headset's serial, e.g. UN-2024.08.41; empty for the first found.
    serial: str
    simulate: bool


def find_headsets(rescan: bool = False) -> list[str]:
    """Serials of the headsets gtec-unicorn can open.

    Windows lists the paired ones at once. Linux and macOS search the air
    for devices named UN-..., paired or not, which takes several seconds
    (the previous search's result is reused unless ``rescan``).

    Raises:
        RuntimeError: If gtec-unicorn cannot be loaded on this platform.
    """
    try:
        import gtec_unicorn
    except (ImportError, OSError) as error:
        raise RuntimeError(f"gtec-unicorn could not be loaded: {error}") \
            from error
    return [str(s) for s in
            gtec_unicorn.Amplifier.get_connected_devices(rescan=rescan)]


def probe(choice: Choice) -> None:
    """Open the headset and let it go again.

    Raises:
        Exception: Whatever gtec-unicorn raises if it cannot be opened.
    """
    if choice.simulate:
        return
    import gtec_unicorn
    gtec_unicorn.Amplifier(choice.serial or None).close()


class _Relay(QObject):
    found = Signal(object)
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
            "The headset's serial, e.g. UN-2024.08.41, as printed on it. "
            "Leave it empty for the first headset found.")
        self.status = QLabel()
        self.status.setObjectName("Note")
        self.refresh_button = QPushButton("Search again")
        self.refresh_button.clicked.connect(lambda: self._search(rescan=True))
        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("Primary")
        self.open_button.setDefault(True)
        self.open_button.clicked.connect(self._open)
        quit_button = QPushButton("Quit")
        quit_button.clicked.connect(self.reject)

        pair = ("Pair it in Settings → Bluetooth & devices first."
                if sys.platform == "win32" else
                "Switch it on; it is found over Bluetooth by its name.")
        intro = QLabel(f"Select the Unicorn Hybrid Black to open. {pair}")
        intro.setWordWrap(True)
        form = QFormLayout()
        device_row = QHBoxLayout()
        device_row.addWidget(self.devices, 1)
        device_row.addWidget(self.refresh_button)
        form.addRow("Device:", device_row)
        form.addRow("", self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(quit_button)
        buttons.addWidget(self.open_button)
        column = QVBoxLayout(self)
        column.addWidget(intro)
        column.addLayout(form)
        column.addLayout(buttons)

        self._relay = _Relay()
        self._relay.found.connect(self._found)
        self._relay.done.connect(self._probed)
        self._progress: QProgressDialog | None = None
        self._fill([])
        self._search(rescan=False)

    def _fill(self, serials: list[str]) -> None:
        current = self.devices.currentText() or self.settings.device.serial
        self.devices.clear()
        for serial in serials:
            self.devices.addItem(serial)
        self.devices.addItem(SIMULATED)
        if current:
            index = self.devices.findText(current)
            if index >= 0:
                self.devices.setCurrentIndex(index)
            else:
                self.devices.setEditText(current)

    def _search(self, rescan: bool) -> None:
        """Look for headsets in the background: on Linux and macOS a search
        takes several seconds."""
        self.refresh_button.setEnabled(False)
        self.status.setText("Searching for headsets...")

        def work():
            try:
                self._relay.found.emit(find_headsets(rescan))
            except Exception as error:  # noqa: BLE001
                self._relay.found.emit(error)
        threading.Thread(target=work, daemon=True).start()

    def _found(self, result) -> None:
        self.refresh_button.setEnabled(True)
        if isinstance(result, Exception):
            self.status.setText(f"Could not search: {result}")
            return
        self._fill(result)
        self.status.setText(
            f"Found {', '.join(result)}." if result else
            "No headset found. Is it switched on and in range?")

    def current_choice(self) -> Choice:
        text = self.devices.currentText().strip()
        if text == SIMULATED:
            return Choice(SIMULATED_SERIAL, True)
        return Choice(text, False)

    def _open(self) -> None:
        choice = self.current_choice()
        self.open_button.setEnabled(False)
        self._progress = QProgressDialog(
            f"Connecting to {choice.serial or 'the Unicorn'}...", None, 0, 0,
            self)
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
        self.accept()
