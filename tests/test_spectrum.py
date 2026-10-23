import numpy as np

from rhinorecorder import spectrum
from rhinorecorder.layout import SAMPLING_RATE


def test_average_psd_finds_the_rhythm_and_averages_the_electrodes():
    fs = SAMPLING_RATE
    t = np.arange(int(spectrum.WINDOW_S * fs)) / fs
    rng = np.random.default_rng(0)
    # A 10 Hz rhythm on every electrode, drift and an offset as raw EEG
    # has, and 50 Hz mains on one electrode only.
    eeg = (20 * np.sin(2 * np.pi * 10 * t)[:, None]
           + 3000 + 50 * t[:, None] + rng.normal(0, 1, (len(t), 8)))
    eeg[:, 0] += 40 * np.sin(2 * np.pi * 50 * t)
    freqs, psd = spectrum.average_psd(eeg)

    assert freqs[0] == 0 and freqs[-1] == spectrum.MAX_FREQUENCY
    assert np.allclose(np.diff(freqs), 1 / spectrum.SEGMENT_S)
    assert freqs[np.argmax(psd)] == 10
    # The mains line is in the average, at an eighth of its power.
    _, alone = spectrum.average_psd(eeg[:, :1])
    at_50 = np.flatnonzero(freqs == 50)[0]
    assert psd[at_50] > 100 * np.median(psd)
    assert np.isclose(psd[at_50], alone[at_50] / 8, rtol=0.05)
    # The offset and drift stay out of the lowest bins.
    assert psd[0] < psd[np.flatnonzero(freqs == 10)[0]] / 1000


def test_decibels():
    assert list(spectrum.decibels(np.array([1.0, 10.0, 100.0]))) == [0, 10, 20]
    assert np.isfinite(spectrum.decibels(np.zeros(3))).all()


def test_average_psd_waits_for_a_whole_segment():
    freqs, psd = spectrum.average_psd(np.zeros((100, 8)))
    assert len(freqs) == len(psd) == 0


def test_max_frequency_stays_below_nyquist():
    freqs, _ = spectrum.average_psd(np.zeros((1200, 8)), fs=150.0)
    assert freqs[-1] == 75.0
