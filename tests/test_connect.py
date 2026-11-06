"""The device list of the connect dialog."""
import types

import pytest

from rhinorecorder.simulator import SIMULATED_SERIAL
from rhinorecorder.ui import connect_dialog


def test_find_headsets_asks_gtec_unicorn(monkeypatch):
    asked = []

    class Amplifier:
        @staticmethod
        def get_connected_devices(rescan=False):
            asked.append(rescan)
            return ["UN-2024.10.18", "UN-2026.08.26"]

    monkeypatch.setitem(__import__("sys").modules, "gtec_unicorn",
                        types.SimpleNamespace(Amplifier=Amplifier))
    assert connect_dialog.find_headsets(rescan=True) == [
        "UN-2024.10.18", "UN-2026.08.26"]
    assert asked == [True]


def test_dialog_lists_found_headsets_and_the_simulation(settings,
                                                        monkeypatch):
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(connect_dialog, "find_headsets",
                        lambda rescan=False: ["UN-2024.10.18"])
    settings.device.serial = "UN-2024.10.18"
    dialog = connect_dialog.ConnectDialog(settings)
    for _ in range(100):
        app.processEvents()
        if dialog.devices.count() == 2:
            break
        __import__("time").sleep(0.01)
    items = [dialog.devices.itemText(i) for i in range(dialog.devices.count())]
    assert items == ["UN-2024.10.18", connect_dialog.SIMULATED]
    assert dialog.current_choice() == connect_dialog.Choice("UN-2024.10.18",
                                                            False)
    dialog.devices.setCurrentText(connect_dialog.SIMULATED)
    assert dialog.current_choice() == connect_dialog.Choice(SIMULATED_SERIAL,
                                                            True)
    dialog.close()
