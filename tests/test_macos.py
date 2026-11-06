"""Relaunching inside an app bundle that declares Bluetooth use (macOS)."""
import plistlib

from rhinorecorder import macos


def test_bundle_declares_bluetooth_and_runs_this_python(tmp_path,
                                                        monkeypatch):
    monkeypatch.setattr(macos, "BUNDLE", tmp_path / "Rhino Recorder.app")
    monkeypatch.setattr(macos.subprocess, "run", lambda *a, **k: None)
    macos._write_bundle("/some/python")
    info = plistlib.loads(
        (macos.BUNDLE / "Contents" / "Info.plist").read_bytes())
    assert info["NSBluetoothAlwaysUsageDescription"]
    script = (macos.BUNDLE / "Contents" / "MacOS"
              / info["CFBundleExecutable"]).read_text()
    assert f"export {macos.BUNDLED_ENV}=1" in script
    assert '"/some/python" -m rhinorecorder "$@"' in script


def test_relaunch_only_on_macos_outside_a_bundle(monkeypatch):
    monkeypatch.setattr(macos.sys, "platform", "darwin")
    monkeypatch.delenv(macos.BUNDLED_ENV, raising=False)
    assert macos.needs_relaunch()
    monkeypatch.setenv(macos.BUNDLED_ENV, "1")
    assert not macos.needs_relaunch()
    monkeypatch.setattr(macos.sys, "platform", "linux")
    monkeypatch.delenv(macos.BUNDLED_ENV, raising=False)
    assert not macos.needs_relaunch()
