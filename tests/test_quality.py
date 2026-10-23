import numpy as np

from rhino_recorder import quality
from rhino_recorder.layout import SAMPLING_RATE


def test_good_flat_and_noisy_channels():
    rng = np.random.default_rng(0)
    n = 10 * SAMPLING_RATE
    t = np.arange(n) / SAMPLING_RATE
    eeg = np.empty((n, 8))
    # Alpha with each electrode's own phase, as real EEG has.
    phases = rng.uniform(0, 2 * np.pi, 8)
    eeg[:] = 20000 + 10 * np.sin(2 * np.pi * 10 * t[:, None] + phases)
    eeg += rng.normal(0, 2, eeg.shape)
    eeg[:, 3] = -5000                          # flat: no signal
    eeg[:, 6] += rng.normal(0, 200, n)          # loose electrode
    q = quality.SignalQuality()
    q.update(eeg[:SAMPLING_RATE])
    assert q.verdicts() == [quality.UNKNOWN] * 8
    for start in range(SAMPLING_RATE, n, 25):
        q.update(eeg[start:start + 25])
    verdicts = q.verdicts()
    assert verdicts[3] == quality.BAD
    assert verdicts[6] == quality.BAD
    assert [v for i, v in enumerate(verdicts) if i not in (3, 6)] == \
        [quality.GOOD] * 6


def test_floating_electrode_is_bad():
    """An electrode off the skin drifts by tens of mV, all far below the
    band, so only the raw swing gives it away (measured on a Unicorn
    lying on a desk: 137 mV in 10 s, 3 uV after the 1-30 Hz filter)."""
    rng = np.random.default_rng(1)
    n = 10 * SAMPLING_RATE
    t = np.arange(n) / SAMPLING_RATE
    phases = rng.uniform(0, 2 * np.pi, 8)
    eeg = 20000 + 10 * np.sin(2 * np.pi * 10 * t[:, None] + phases) \
        + rng.normal(0, 2, (n, 8))
    eeg[:, 2] = 2000 + 13700 * t + rng.normal(0, 2, n)
    q = quality.SignalQuality()
    for start in range(0, n, 25):
        q.update(eeg[start:start + 25])
    verdicts = q.verdicts()
    assert verdicts[2] == quality.BAD
    assert verdicts.count(quality.GOOD) == 7


def test_channels_that_only_share_common_noise_are_bad():
    """Floating inputs pick up the same noise: measured on the desk, every
    channel correlated 1.00 with the others; worn, never above 0.88."""
    rng = np.random.default_rng(2)
    n = 10 * SAMPLING_RATE
    t = np.arange(n) / SAMPLING_RATE
    common = 5 * np.sin(2 * np.pi * 7 * t) + rng.normal(0, 2, n)
    floating = 90000 + common[:, None] + rng.normal(0, 0.05, (n, 8))
    q = quality.SignalQuality()
    for start in range(0, n, 25):
        q.update(floating[start:start + 25])
    assert q.verdicts() == [quality.BAD] * 8

    # Worn: shared background plus each electrode's own activity.
    worn = 120000 + 0.5 * common[:, None] + rng.normal(0, 6, (n, 8))
    q = quality.SignalQuality()
    for start in range(0, n, 25):
        q.update(worn[start:start + 25])
    assert q.verdicts() == [quality.GOOD] * 8
