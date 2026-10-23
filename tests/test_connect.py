"""The device list of the connect dialog."""
import gprhino

from rhinorecorder.ui import connect_dialog


def test_windows_lists_headsets_with_their_ports(monkeypatch):
    monkeypatch.setattr(connect_dialog.sys, "platform", "win32")
    monkeypatch.setattr(gprhino, "windows_bluetooth_ports", lambda: [
        ("COM5", "A4:6D:D4:17:BF:35", "UN-2024.10.18"),
        ("COM6", "78:5E:A2:BD:0D:5E", "WILLEN"),
        ("COM7", "", "")])
    monkeypatch.setattr(gprhino, "find_ports", lambda: ["COM5", "COM7", "COM9"])
    assert connect_dialog.paired_devices() == [
        ("UN-2024.10.18 (COM5)", "UN-2024.10.18", "COM5"),
        ("COM7", "", "COM7"),
        ("COM9", "", "COM9")]
