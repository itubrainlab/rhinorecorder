"""The Unicorn Recorder's channel order, and which channels a setting keeps.

The Unicorn Recorder writes its channels in this order, each block only
if it is included in the acquisition settings::

    EEG 1-8   microvolts
    ACC X-Z   g
    GYR X-Z   deg/s
    CNT       sample counter
    BAT       battery level in percent
    VALID     1 when no sample was lost before this one
    DT        milliseconds since the previous sample was received
    TRIG      trigger value (Unicorn Recorder's "STATUS" channel)

RhinoRecorder keeps the same order, so analysis scripts written for
Unicorn Recorder files read RhinoRecorder files unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

from gpype.common.constants import Constants

SAMPLING_RATE = 250
NUM_EEG = 8

SIGNAL = Constants.ChannelRoles.SIGNAL
AUXILIARY = Constants.ChannelRoles.AUXILIARY
TRIGGER = Constants.ChannelRoles.TRIGGER


@dataclass(frozen=True)
class Channel:
    label: str
    unit: str
    role: str
    #: The acquisition setting that includes it; None for always.
    group: str | None


CHANNELS: tuple[Channel, ...] = (
    *(Channel(f"EEG {i}", "uV", SIGNAL, None) for i in range(1, NUM_EEG + 1)),
    Channel("ACC X", "g", AUXILIARY, "accelerometer"),
    Channel("ACC Y", "g", AUXILIARY, "accelerometer"),
    Channel("ACC Z", "g", AUXILIARY, "accelerometer"),
    Channel("GYR X", "deg/s", AUXILIARY, "gyroscope"),
    Channel("GYR Y", "deg/s", AUXILIARY, "gyroscope"),
    Channel("GYR Z", "deg/s", AUXILIARY, "gyroscope"),
    Channel("CNT", "-", AUXILIARY, "counter"),
    Channel("BAT", "%", AUXILIARY, "battery"),
    Channel("VALID", "-", AUXILIARY, "validation"),
    Channel("DT", "ms", AUXILIARY, "timing"),
    Channel("TRIG", "-", TRIGGER, None),
)

LABELS = [c.label for c in CHANNELS]
INDEX = {c.label: i for i, c in enumerate(CHANNELS)}

EEG = list(range(NUM_EEG))
CNT = INDEX["CNT"]
BAT = INDEX["BAT"]
VALID = INDEX["VALID"]
DT = INDEX["DT"]
TRIGGER_CHANNEL = INDEX["TRIG"]

#: Columns of the gpype-rhino scan, as RhinoHybridBlack emits them with
#: accelerometer, gyroscope and aux all included: EEG, accel, gyro,
#: battery, counter, validation.
RHINO_COLUMNS = {
    **{f"EEG {i + 1}": i for i in range(NUM_EEG)},
    "ACC X": 8, "ACC Y": 9, "ACC Z": 10,
    "GYR X": 11, "GYR Y": 12, "GYR Z": 13,
    "BAT": 14, "CNT": 15, "VALID": 16,
}
RHINO_WIDTH = 17


def selected(groups: dict[str, bool]) -> list[int]:
    """Indices into CHANNELS that the acquisition settings include.

    Args:
        groups: Setting name (e.g. ``"accelerometer"``) to whether it is
            included. A group that is missing counts as included.
    """
    return [i for i, c in enumerate(CHANNELS)
            if c.group is None or groups.get(c.group, True)]
