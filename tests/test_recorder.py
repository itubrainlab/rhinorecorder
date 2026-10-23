"""End to end on the simulated headset: the real gpype-rhino decoder, the
real g.Pype pipeline, real files and sockets."""
import os
import socket
import time

import numpy as np
import pytest

from rhinorecorder import layout
from rhinorecorder.recorder import IDLE, RUNNING, Recorder, recording_path

from .conftest import free_udp_port


def read_csv(path):
    with open(path) as f:
        lines = f.read().splitlines()
    comments = [line for line in lines if line.startswith("#")]
    header = lines[len(comments)].split(",")
    data = np.loadtxt(path, delimiter=",", comments="#",
                      skiprows=len(comments) + 1, ndmin=2)
    return comments, header, data


def send_triggers(port, values, gap=0.3):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        for value in values:
            tx.sendto(str(value).encode("ascii"), ("127.0.0.1", port))
            time.sleep(gap)


@pytest.fixture
def recorder(settings):
    r = Recorder(settings, simulate=True)
    errors = []
    r.on_error = errors.append
    yield r
    r.stop()
    assert errors == []


def test_record_writes_aligned_csv_and_bdf(recorder, settings):
    pyedflib = pytest.importorskip("pyedflib")
    recorder.start()
    assert recorder.state == RUNNING
    time.sleep(0.5)
    paths = recorder.start_recording()
    assert len(paths) == 4
    time.sleep(0.3)
    send_triggers(settings.network.trigger_in.port, [3, 7, 42])
    time.sleep(1.0)
    recorder.stop_recording()
    assert not recorder.recording

    csvs = sorted(p for p in paths if p.endswith(".csv"))
    tables = [read_csv(p) for p in csvs]
    for comments, header, data in tables:
        assert comments == []
        assert header == layout.LABELS
        assert np.all(np.diff(data[:, layout.CNT]) == 1) or \
            np.any(data[:, layout.VALID] == 0)
        assert list(data[data[:, layout.TRIGGER_CHANNEL] != 0, layout.TRIGGER_CHANNEL]) == \
            [3, 7, 42]
        assert data[:, layout.BAT].max() <= 100
        assert 2 < data[:, layout.DT].mean() < 6
    by_name = dict(zip(csvs, tables))
    raw = next(t for p, t in by_name.items() if "RawData" in p)[2]
    processed = next(t for p, t in by_name.items() if "RawData" not in p)[2]
    assert raw.shape == processed.shape
    np.testing.assert_array_equal(raw[:, layout.CNT],
                                  processed[:, layout.CNT])
    # Raw keeps the electrode offsets; the filter removes them.
    assert np.abs(raw[:, :8].mean(0)).max() > 1000
    assert np.abs(processed[:, :8].mean(0)).max() < 100

    raw_csv = next(p for p in csvs if "RawData" in p)
    raw_bdf = raw_csv[:-4] + ".bdf"
    reader = pyedflib.EdfReader(raw_bdf)
    try:
        assert reader.getSignalLabels() == layout.LABELS
        assert reader.getSampleFrequency(0) == layout.SAMPLING_RATE
        equipment = reader.equipment
        if isinstance(equipment, bytes):
            equipment = equipment.decode()
        assert equipment.strip() == "UN-SIMULATED"
        additional = reader.recording_additional
        if isinstance(additional, bytes):
            additional = additional.decode()
        assert "NON-COMMERCIAL" not in additional
        n = len(raw)
        eeg = reader.readSignal(0)[:n]
        assert np.abs(eeg - raw[:, 0]).max() < 0.1   # 24-bit, 0.09 uV/step
        np.testing.assert_array_equal(reader.readSignal(layout.CNT)[:n],
                                      raw[:, layout.CNT])
        onsets, _, texts = reader.readAnnotations()
        assert list(texts) == ["3", "7", "42"]
    finally:
        reader.close()


def test_oscar_cleans_only_the_processed_recording(settings):
    """With OSCAR on, the raw files are raw: OSCAR removes the electrodes'
    offsets from the processed EEG only, in the same rows."""
    settings.display.oscar = True
    recorder = Recorder(settings, simulate=True)
    errors = []
    recorder.on_error = errors.append
    try:
        recorder.start()
        paths = recorder.start_recording()
        time.sleep(5.5)              # recordings begin once OSCAR settles
        recorder.stop_recording()
    finally:
        recorder.stop()
    assert errors == []

    csvs = sorted(p for p in paths if p.endswith(".csv"))
    raw = next(read_csv(p) for p in csvs if "RawData" in p)
    processed = next(read_csv(p) for p in csvs if "RawData" not in p)
    for _, header, data in (raw, processed):
        assert header == layout.LABELS     # the raw copy is not a column
        assert len(data) > layout.SAMPLING_RATE
    raw, processed = raw[2], processed[2]
    np.testing.assert_array_equal(raw[:, layout.CNT],
                                  processed[:, layout.CNT])
    assert np.abs(raw[:, :8].mean(0)).min() > 1000
    assert np.abs(processed[:, :8].mean(0)).max() < 100


def test_record_button_starts_acquisition_too(recorder):
    recorder.start(record=True)
    assert recorder.running and recorder.recording
    time.sleep(0.5)
    recorder.stop()
    assert recorder.state == IDLE and not recorder.recording
    for path in recorder.recording_paths:
        assert os.path.getsize(path) > 0


def test_each_recording_gets_its_own_files(recorder):
    recorder.start()
    first = recorder.start_recording()
    time.sleep(0.3)
    recorder.stop_recording()
    second = recorder.start_recording()
    time.sleep(0.3)
    recorder.stop_recording()
    assert set(first).isdisjoint(second)
    assert all(os.path.exists(p) for p in first + second)


def test_excluded_signals_are_left_out_of_files(recorder, settings):
    acq = settings.acquisition
    acq.accelerometer = acq.gyroscope = acq.timing = False
    settings.recording.raw_bdf.enabled = False
    settings.recording.processed_bdf.enabled = False
    recorder.start(record=True)
    time.sleep(0.5)
    recorder.stop()
    for path in recorder.recording_paths:
        _, header, data = read_csv(path)
        assert header == [f"EEG {i}" for i in range(1, 9)] + \
            ["CNT", "BAT", "VALID", "TRIG"]
        assert data.shape[1] == 12


def test_udp_output_sends_one_csv_line_per_sample(recorder, settings):
    port = free_udp_port()
    settings.network.processed_udp.enabled = True
    settings.network.processed_udp.port = port
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx:
        rx.bind(("127.0.0.1", port))
        rx.settimeout(5)
        recorder.start()
        lines = [rx.recv(2048) for _ in range(50)]
    for line in lines:
        assert line.endswith(b"\n")
        values = line.decode("ascii").strip().split(",")
        assert len(values) == len(layout.CHANNELS)
        assert all(len(v.split(".")[1]) == 3 for v in values)
    counters = [float(line.split(b",")[layout.CNT]) for line in lines]
    assert np.all(np.diff(counters) >= 1)


def test_lsl_output(recorder, settings):
    pylsl = pytest.importorskip("pylsl")
    settings.network.raw_lsl.enabled = True
    settings.network.raw_lsl.name = f"RhinoTest{os.getpid()}"
    recorder.start()
    streams = pylsl.resolve_byprop("name", settings.network.raw_lsl.name,
                                   timeout=5)
    assert streams
    inlet = pylsl.StreamInlet(streams[0])
    info = inlet.info()
    assert info.channel_count() == len(layout.CHANNELS)
    assert info.nominal_srate() == layout.SAMPLING_RATE
    assert info.type() == "EEG"
    channel = info.desc().child("channels").child("channel")
    labels = []
    while not channel.empty():
        labels.append(channel.child_value("label"))
        channel = channel.next_sibling()
    assert labels == layout.LABELS
    assert info.desc().child("licence").empty()
    assert info.desc().child("device").child_value("serial") == \
        "UN-SIMULATED"
    chunk, stamps = inlet.pull_chunk(timeout=3, max_samples=50)
    deadline = time.monotonic() + 5
    while not chunk and time.monotonic() < deadline:
        chunk, stamps = inlet.pull_chunk(timeout=1, max_samples=50)
    assert chunk and len(chunk[0]) == len(layout.CHANNELS)
    inlet.close_stream()


def test_filter_can_change_while_running(recorder):
    recorder.set_filter("None")
    recorder.set_notch("None")
    recorder.start()
    time.sleep(1.0)
    buffer, total = recorder.graph.scope.sweep()
    unfiltered = recorder.graph.scope.latest(100)[:, :8]
    assert np.abs(unfiltered.mean(0)).max() > 1000      # DC offsets shown
    recorder.set_filter("1 – 30 Hz")
    recorder.set_notch("50 Hz")
    time.sleep(2.0)
    filtered = recorder.graph.scope.latest(100)[:, :8]
    assert np.abs(filtered.mean(0)).max() < 100


def test_bad_settings_refuse_to_start(recorder, settings):
    settings.network.raw_udp.enabled = True
    settings.network.raw_udp.port = settings.network.trigger_in.port
    with pytest.raises(ValueError, match="must differ"):
        recorder.start()
    assert recorder.state == IDLE


def test_recording_path_never_overwrites(tmp_path):
    from datetime import datetime
    stamp = datetime(2026, 1, 2, 3, 4, 5)
    first = recording_path(str(tmp_path), "Rec", stamp, ".csv")
    assert first.endswith("Rec_20260102_030405.csv")
    open(first, "w").close()
    second = recording_path(str(tmp_path), "Rec", stamp, ".csv")
    assert second.endswith("Rec_20260102_030405_2.csv")


def test_cut_short_bdf_can_be_repaired(recorder, settings):
    pyedflib = pytest.importorskip("pyedflib")
    from rhinorecorder.nodes import repair_bdf

    settings.recording.raw_csv.enabled = False
    settings.recording.processed_csv.enabled = False
    settings.recording.processed_bdf.enabled = False
    recorder.start(record=True)
    time.sleep(2.5)
    recorder.stop()
    path = recorder.recording_paths[0]
    with pyedflib.EdfReader(path) as reader:
        expected = reader.datarecords_in_file
    # What a killed program leaves: no record count in the header.
    with open(path, "r+b") as f:
        f.seek(236)
        f.write(b"-1      ")
    with pytest.raises(OSError):
        pyedflib.EdfReader(path)
    assert repair_bdf(path) == expected
    with pyedflib.EdfReader(path) as reader:
        assert reader.datarecords_in_file == expected


def test_processed_eeg_starts_settled_with_oscar(recorder, settings):
    """OSCAR fills its delay with zeros and then overshoots while it
    removes the electrode offsets; recorded from the start, the first
    processed rows held 70 mV and more (measured on a real headset)."""
    settings.display.oscar = True
    settings.recording.raw_csv.enabled = False
    settings.recording.raw_bdf.enabled = False
    settings.recording.processed_bdf.enabled = False
    recorder.start(record=True)
    time.sleep(5.0)
    recorder.stop()
    _, header, data = read_csv(recorder.recording_paths[0])
    assert len(data) > 250
    assert np.abs(data[:, :8]).max() < 500
