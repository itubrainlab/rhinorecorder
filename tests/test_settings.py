import json

from rhinorecorder import layout
from rhinorecorder.settings import Settings


def test_round_trip(tmp_path):
    s = Settings()
    s.display.filter = "2 – 30 Hz"
    s.network.raw_lsl.enabled = True
    s.recording.raw_bdf.subject_id = "S01"
    s.acquisition.gyroscope = False
    path = tmp_path / "settings.json"
    s.save(path)
    assert Settings.load(path) == s


def test_bad_or_old_files_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    assert Settings.load(path) == Settings()
    path.write_text("not json")
    assert Settings.load(path) == Settings()
    path.write_text(json.dumps({
        "display": {"filter": "no such filter", "notch": 7},
        "network": {"trigger_in": {"port": "10000"}},
        "unknown": 1,
    }))
    loaded = Settings.load(path)
    assert loaded.display == Settings().display
    assert loaded.network.trigger_in.port == Settings().network.trigger_in.port


def test_trigger_port_must_differ_from_outputs():
    s = Settings()
    assert s.problems() == []
    s.network.processed_udp.enabled = True
    s.network.processed_udp.port = s.network.trigger_in.port
    assert any("must differ" in p for p in s.problems())
    s.network.trigger_in.enabled = False
    assert s.problems() == []


def test_lsl_streams_need_distinct_names():
    s = Settings()
    s.network.raw_lsl.enabled = s.network.processed_lsl.enabled = True
    s.network.raw_lsl.name = s.network.processed_lsl.name = "same"
    assert s.problems()


def test_selected_channels_follow_acquisition_settings():
    s = Settings()
    assert layout.selected(s.acquisition.groups()) == list(range(19))
    s.acquisition.accelerometer = False
    s.acquisition.timing = False
    labels = [layout.LABELS[i] for i in layout.selected(s.acquisition.groups())]
    assert "ACC X" not in labels and "DT" not in labels
    assert labels[:8] == [f"EEG {i}" for i in range(1, 9)]
    assert labels[-1] == "TRIG"


def test_default_ports():
    net = Settings().network
    assert (net.trigger_in.port, net.processed_udp.port,
            net.raw_udp.port) == (10000, 10001, 10002)


def test_old_default_trigger_port_is_migrated(tmp_path):
    path = tmp_path / "settings.json"
    old = Settings().to_dict()
    del old["version"]
    old["network"]["trigger_in"]["port"] = 11000
    path.write_text(json.dumps(old))
    assert Settings.load(path).network.trigger_in.port == 10000
    # A port chosen in a current file is kept.
    current = Settings()
    current.network.trigger_in.port = 11000
    current.save(path)
    assert Settings.load(path).network.trigger_in.port == 11000


def test_trigger_bind_address():
    from rhinorecorder.settings import trigger_bind_address as bind
    assert bind("127.0.0.1", 1000, "darwin") == "0.0.0.0"
    assert bind("127.0.0.1", 5000, "darwin") == "127.0.0.1"
    assert bind("192.168.1.5", 1000, "darwin") == "192.168.1.5"
    assert bind("127.0.0.1", 1000, "win32") == "127.0.0.1"
    assert bind("127.0.0.1", 1000, "linux") == "127.0.0.1"


def test_display_defaults_and_migration(tmp_path):
    assert Settings().display.oscar is True
    assert Settings().display.filter == "0.1 – 30 Hz"
    path = tmp_path / "settings.json"
    old = Settings().to_dict()
    old["version"] = 1
    old["display"].update(filter="1 – 30 Hz", oscar=False)
    path.write_text(json.dumps(old))
    loaded = Settings.load(path).display
    assert (loaded.filter, loaded.oscar) == ("0.1 – 30 Hz", True)
    # A display the user changed is kept.
    old["display"].update(filter="2 – 30 Hz", oscar=False)
    path.write_text(json.dumps(old))
    loaded = Settings.load(path).display
    assert (loaded.filter, loaded.oscar) == ("2 – 30 Hz", False)


def test_old_default_ports_are_migrated(tmp_path):
    path = tmp_path / "settings.json"
    old = Settings().to_dict()
    old["version"] = 2
    old["network"]["trigger_in"]["port"] = 1000
    old["network"]["processed_udp"]["port"] = 1001
    old["network"]["raw_udp"]["port"] = 5555          # chosen by the user
    path.write_text(json.dumps(old))
    net = Settings.load(path).network
    assert (net.trigger_in.port, net.processed_udp.port,
            net.raw_udp.port) == (10000, 10001, 5555)
