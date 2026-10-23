import numpy as np
import pytest
from scipy import signal

from rhinorecorder import presets
from rhinorecorder.layout import SAMPLING_RATE


def gain_db(sos, f):
    _, h = signal.sosfreqz(sos, worN=[f], fs=SAMPLING_RATE)
    return 20 * np.log10(abs(h[0]))


def test_every_filter_preset_designs():
    for name in presets.FILTERS:
        sos = presets.filter_sos(name)
        assert (sos is None) == (name == presets.NONE)


@pytest.mark.parametrize("name, passes, stops", [
    ("1 – 30 Hz", [10], [0.05, 80]),
    ("0.1 – 50 Hz", [1, 40], [0.005, 110]),
    ("> 2 Hz", [20], [0.2]),
    ("< 20 Hz", [5], [60]),
])
def test_filter_response(name, passes, stops):
    sos = presets.filter_sos(name)
    for f in passes:
        assert gain_db(sos, f) > -1
    for f in stops:
        assert gain_db(sos, f) < -20


def test_cascading_notch_removes_harmonics_below_nyquist():
    assert presets.notch_frequencies("Cascading 50 Hz") == [50, 100]
    assert presets.notch_frequencies("Cascading 50 & 60 Hz") == [50, 60,
                                                                 100, 120]
    assert presets.notch_frequencies("60 Hz") == [60]
    assert presets.notch_frequencies(presets.NONE) == []


def test_notch_response():
    sos = presets.notch_sos("Cascading 50 Hz")
    assert gain_db(sos, 50) < -30
    assert gain_db(sos, 100) < -30
    assert gain_db(sos, 10) > -0.5
    assert presets.notch_sos(presets.NONE) is None


def test_defaults_exist():
    assert presets.DEFAULT_FILTER in presets.FILTERS
    assert presets.DEFAULT_NOTCH in presets.NOTCHES
    assert presets.DEFAULT_SCALING in presets.SCALINGS
