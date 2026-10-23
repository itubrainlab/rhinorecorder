"""RhinoRecorder's own g.Pype nodes.

- :class:`UnicornLayout` puts the headset's channels into Unicorn
  Recorder's order and adds the DT and TRIG channels.
- :class:`EegFilter` filters the EEG channels with a filter that can be
  swapped while the pipeline runs, so the Filter and Notch boxes work
  without restarting acquisition.
- :class:`CsvLogger` and :class:`BdfLogger` write files only between
  :meth:`~GatedLogger.begin` and :meth:`~GatedLogger.end`, so recording
  can start and stop while acquisition keeps running.
- :class:`UdpCsvSender` streams samples as comma-separated text, which
  is what Unicorn Recorder's UDP output sends.
- :class:`SweepTap` keeps the latest samples for the user interface.

- :class:`LslSender` publishes a Lab Streaming Layer stream.

Files and streams carry the channels and their description only.
"""
from __future__ import annotations

import os
import socket
import warnings
import threading
import time
from datetime import datetime
from typing import Optional

import gpype as gp
import numpy as np
from gpype.common.constants import Constants
from scipy.signal import sosfilt, sosfilt_zi

from . import layout

PORT_IN = Constants.Defaults.PORT_IN
PORT_OUT = Constants.Defaults.PORT_OUT
Keys = Constants.Keys

#: Per-channel keys a node must drop when it changes which channels exist.
_PER_CHANNEL_KEYS = (Keys.CHANNEL_GAINS, Keys.CHANNEL_OFFSETS,
                     Keys.CHANNEL_CLIPPING, Keys.CHANNEL_FILTERS)


def describe(context: dict, indices: list[int]) -> None:
    """Describe the layout channels at ``indices`` in a port context."""
    context[Keys.CHANNEL_COUNT] = len(indices)
    context[Keys.CHANNEL_LABELS] = [layout.CHANNELS[i].label for i in indices]
    context[Keys.CHANNEL_UNITS] = [layout.CHANNELS[i].unit for i in indices]
    context[Keys.CHANNEL_ROLES] = [layout.CHANNELS[i].role for i in indices]
    for key in _PER_CHANNEL_KEYS:
        context.pop(key, None)


class RawEegCopy(gp.IONode):
    """Copies of the EEG channels, added as auxiliary channels after the
    scan (ahead of the arrival stamp g.Pype's Sync reads).

    g.Pype runs OSCAR inside the source's chain, so everything downstream
    gets OSCAR's EEG. Placed in front of OSCAR (see
    :mod:`rhinorecorder.sources`), the copies pass through OSCAR
    untouched, as auxiliary channels do, and delayed together with its
    output: the raw EEG and OSCAR's leave the source in the same rows.
    """

    def setup(self, data, port_context_in):
        roles = list(port_context_in[PORT_IN][Keys.CHANNEL_ROLES])
        self._eeg = [i for i, role in enumerate(roles)
                     if role == layout.SIGNAL]
        stamp = Constants.ChannelRoles.TIMESTAMP
        self._at = roles.index(stamp) if stamp in roles else len(roles)
        out = super().setup(data, port_context_in)
        copies = len(self._eeg)
        for context in out.values():
            for key in (Keys.CHANNEL_ROLES, Keys.CHANNEL_LABELS,
                        Keys.CHANNEL_UNITS):
                values = context.get(key)
                if values is None or len(values) != len(roles):
                    continue
                values = list(values)
                added = {Keys.CHANNEL_ROLES: layout.AUXILIARY,
                         Keys.CHANNEL_UNITS: "uV"}.get(key)
                context[key] = (values[:self._at]
                                + [added or f"RAW {i + 1}"
                                   for i in range(copies)]
                                + values[self._at:])
            context[Keys.CHANNEL_COUNT] = len(roles) + copies
            for key in _PER_CHANNEL_KEYS:
                context.pop(key, None)
        return out

    def step(self, data):
        block = data[PORT_IN]
        return {PORT_OUT: np.concatenate(
            [block[:, :self._at], block[:, self._eeg], block[:, self._at:]],
            axis=1)}


class UnicornLayout(gp.IONode):
    """gpype-rhino's scan, plus an optional trigger channel, in Unicorn
    Recorder's channel order (see :mod:`rhinorecorder.layout`).

    With ``raw``, the EEG comes from the raw copy the source adds when
    OSCAR runs (:class:`RawEegCopy`), and otherwise from the scan's EEG,
    which is OSCAR's output when it runs.

    DT is the time between this sample's arrival and the previous one's,
    in milliseconds; with a frame size of 1 that is per sample, as in
    Unicorn Recorder. TRIG carries a trigger value on the sample where
    it arrived and zero elsewhere.
    """

    def __init__(self, raw: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.raw = raw
        #: Source column of each layout channel the scan fills; set up
        #: once the source's channels are known.
        self._columns: Optional[np.ndarray] = None
        self._targets = np.array(
            [i for i, c in enumerate(layout.CHANNELS)
             if c.label in layout.RHINO_COLUMNS])
        self._trigger: Optional[int] = None
        self._last_arrival: Optional[float] = None
        self._last_trigger = 0.0

    def setup(self, data, port_context_in):
        context = port_context_in[PORT_IN]
        roles = list(context.get(Keys.CHANNEL_ROLES) or [])
        width = int(context[Keys.CHANNEL_COUNT])
        if width < layout.RHINO_WIDTH:
            raise ValueError(
                f"UnicornLayout needs the headset's {layout.RHINO_WIDTH} "
                f"channels (EEG, accelerometer, gyroscope and aux); got "
                f"{width}.")
        self._trigger = (roles.index(layout.TRIGGER)
                         if layout.TRIGGER in roles else None)
        scan = width - (self._trigger is not None)
        self._columns = np.array(
            [layout.RHINO_COLUMNS[c.label] for c in layout.CHANNELS
             if c.label in layout.RHINO_COLUMNS])
        if self.raw and scan >= layout.RHINO_RAW_EEG[-1] + 1:
            self._columns[layout.EEG] = layout.RHINO_RAW_EEG
        self._last_arrival = None
        self._last_trigger = 0.0
        out = super().setup(data, port_context_in)
        for ctx in out.values():
            describe(ctx, list(range(len(layout.CHANNELS))))
        return out

    def step(self, data):
        block = data[PORT_IN]
        n = block.shape[0]
        out = np.zeros((n, len(layout.CHANNELS)), dtype=block.dtype)
        out[:, self._targets] = block[:, self._columns]

        now = time.perf_counter()
        if self._last_arrival is not None:
            out[0, layout.DT] = (now - self._last_arrival) * 1000.0
        self._last_arrival = now

        if self._trigger is not None:
            trigger = block[:, self._trigger]
            previous = np.concatenate(([self._last_trigger], trigger[:-1]))
            onset = (trigger != 0) & (trigger != previous)
            out[:, layout.TRIGGER_CHANNEL] = np.where(onset, trigger, 0)
            self._last_trigger = float(trigger[-1])
        return {PORT_OUT: out}


class EegFilter(gp.IONode):
    """An IIR filter on the EEG (signal) channels that can be replaced
    while the pipeline runs. The other channels pass through untouched.

    Args:
        sos: Second-order sections, or None to pass the EEG through.
        settle: Samples to pass through unfiltered at the start, while
            the input itself is still settling (OSCAR's start-up); the
            filter starts from the steady state of the sample after.
    """

    def __init__(self, sos: Optional[np.ndarray] = None, settle: int = 0,
                 **kwargs):
        super().__init__(**kwargs)
        self._settle = int(settle)
        self._seen = 0
        self._lock = threading.Lock()
        self._pending = (sos,)
        self._sos: Optional[np.ndarray] = None
        self._z: Optional[np.ndarray] = None
        self._signal: list[int] = []
        self._primed = False

    def set_sos(self, sos: Optional[np.ndarray]) -> None:
        """Use these sections from the next frame on."""
        with self._lock:
            self._pending = (sos,)

    def setup(self, data, port_context_in):
        context = port_context_in[PORT_IN]
        roles = context.get(Keys.CHANNEL_ROLES)
        width = int(context[Keys.CHANNEL_COUNT])
        if roles:
            self._signal = [i for i, r in enumerate(roles)
                            if r == layout.SIGNAL]
        else:
            self._signal = list(range(width))
        with self._lock:
            if self._pending is None:
                self._pending = (self._sos,)
        self._primed = False
        self._seen = 0
        return super().setup(data, port_context_in)

    def step(self, data):
        block = data[PORT_IN]
        with self._lock:
            pending, self._pending = self._pending, None
        x = block[:, self._signal].astype(np.float64)
        seen = self._seen
        self._seen += block.shape[0]
        if pending is not None:
            self._sos = pending[0]
            self._primed = False
        if self._sos is None:
            return {PORT_OUT: block}
        first = 0
        if not self._primed:
            # Unfiltered while the input settles.
            skip = max(self._settle - seen, 0)
            if skip >= block.shape[0]:
                return {PORT_OUT: block}
            x[:skip] = 0
            # Start from the steady state for the level the signal has, so
            # starting or swapping filters does not ring. Not from zeros:
            # OSCAR fills its delay with them, and a highpass started at
            # zero rings for many seconds when the electrode offsets,
            # hundreds of millivolts, arrive.
            live = np.flatnonzero(np.any(x != 0, axis=1))
            if len(live) == 0:
                return {PORT_OUT: block}
            first = int(live[0])
            zi = sosfilt_zi(self._sos)
            self._z = zi[:, :, None] * x[first][None, None, :]
            self._primed = True
        out = block.copy()
        y, self._z = sosfilt(self._sos, x[first:], axis=0, zi=self._z)
        out[first:, self._signal] = y
        return {PORT_OUT: out}


class _Described(gp.Sink):
    """A sink that remembers what its input's channels are."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.labels: list[str] = []
        self.units: list[str] = []
        self.roles: list[str] = []
        self.sampling_rate = float(layout.SAMPLING_RATE)
        self.device_serial = ""

    def setup(self, data, port_context_in):
        context = port_context_in[PORT_IN]
        width = int(context[Keys.CHANNEL_COUNT])
        self.labels = list(context.get(Keys.CHANNEL_LABELS)
                           or [f"Ch{i + 1}" for i in range(width)])
        self.units = [u or "" for u in (context.get(Keys.CHANNEL_UNITS)
                                        or [""] * width)]
        self.roles = list(context.get(Keys.CHANNEL_ROLES)
                          or [layout.SIGNAL] * width)
        self.sampling_rate = float(context.get(Keys.SAMPLING_RATE)
                                   or layout.SAMPLING_RATE)
        self.device_serial = str(context.get(Keys.DEVICE_SERIAL) or "")
        return super().setup(data, port_context_in)

    @property
    def marked(self) -> bool:
        """Whether g.Pype asked this run's output to carry its mark."""
        return bool(self._marked)


class GatedLogger(_Described):
    """A file sink that writes only while a recording is open.

    Every logger in a pipeline sees the same samples, so each counts them
    and a recording starts and ends at a sample index rather than at a
    moment: files from different loggers then cover exactly the same
    samples, whichever thread each logger runs on.
    """

    extension = ""

    def __init__(self, subject_id: str = "", recording_id: str = "",
                 **kwargs):
        super().__init__(**kwargs)
        self.subject_id = subject_id
        self.recording_id = recording_id
        self._lock = threading.Lock()
        self._open = False
        self._start_at = 0
        self._end_at: Optional[int] = None
        self._seen = 0
        self.path: Optional[str] = None
        self.samples_written = 0

    @property
    def recording(self) -> bool:
        """Whether a file is open (it may not have reached its end yet)."""
        return self._open

    @property
    def seen(self) -> int:
        """Samples this logger has been handed since the pipeline started."""
        return self._seen

    def setup(self, data, port_context_in):
        self._seen = 0
        return super().setup(data, port_context_in)

    def begin(self, path: str, start_at: int = 0) -> None:
        """Open ``path`` and write into it every sample from index
        ``start_at`` on (see :attr:`seen`)."""
        with self._lock:
            if self._open:
                self._close()
            os.makedirs(os.path.dirname(os.path.abspath(path)),
                        exist_ok=True)
            self.path = path
            self.samples_written = 0
            self._start_at = start_at
            self._end_at = None
            self._open_file(path)
            self._open = True

    def end(self, end_at: Optional[int] = None) -> None:
        """Close the file once sample ``end_at`` is reached, or now if it
        is None or already past."""
        with self._lock:
            if not self._open:
                return
            if end_at is None or end_at <= self._seen:
                self._close()
            else:
                self._end_at = end_at

    def _close(self) -> None:
        self._open = False
        self._end_at = None
        self._close_file()

    def step(self, data):
        block = data[PORT_IN]
        with self._lock:
            first = self._seen
            self._seen += block.shape[0]
            if self._open:
                lo = max(self._start_at - first, 0)
                hi = block.shape[0]
                if self._end_at is not None:
                    hi = min(self._end_at - first, hi)
                if hi > lo:
                    self._write(block[lo:hi])
                    self.samples_written += hi - lo
                if self._end_at is not None and self._seen >= self._end_at:
                    self._close()
        return None

    def stop(self):
        self.end()
        super().stop()

    def _open_file(self, path: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def _write(self, block: np.ndarray) -> None:  # pragma: no cover
        raise NotImplementedError

    def _close_file(self) -> None:  # pragma: no cover
        raise NotImplementedError


def _three_decimals(block: np.ndarray) -> np.ndarray:
    """Rounded to three decimals, without the "-0.000" a tiny negative
    value would otherwise print as."""
    return np.round(block, 3) + 0.0


class CsvLogger(GatedLogger):
    """Unicorn Recorder's CSV format: one row per sample, one column per
    channel, three decimals, after a header row naming the channels."""

    extension = ".csv"

    def _open_file(self, path):
        self._file = open(path, "w", newline="")
        self._file.write(",".join(self.labels) + "\n")

    def _write(self, block):
        np.savetxt(self._file, _three_decimals(block), fmt="%.3f",
                   delimiter=",")

    def _close_file(self):
        self._file.close()
        self._file = None


#: Physical range of each channel in a BDF file. EEG spans the headset's
#: whole 24-bit range, so the raw counts survive exactly.
_BDF_RANGE = {
    "uV": (-750000.0, 750000.0),
    "g": (-8.0, 8.0),
    "deg/s": (-1000.0, 1000.0),
    "%": (0.0, 100.0),
    "ms": (0.0, 60000.0),
}
_BDF_DIGITAL = (-8388608, 8388607)


def _bdf_range(label: str, unit: str) -> tuple[float, float]:
    if label == "VALID":
        return (0.0, 1.0)
    if label in ("CNT", "TRIG"):
        # One digital step per count: the counter fits for 18 hours.
        return (0.0, float(_BDF_DIGITAL[1] - _BDF_DIGITAL[0]))
    return _BDF_RANGE.get(unit, (-750000.0, 750000.0))


def _header_number(value: float):
    """A whole number as an int, so the 8-character EDF header field
    does not lose its last digit to a trailing ".0"."""
    return int(value) if float(value).is_integer() else value


def repair_bdf(path: str) -> int:
    """Write the number of data records into a BDF/EDF header that lacks
    it, and return that number.

    The count is written when a file is closed, so a recording whose
    program was killed has -1 there, and most readers refuse it. The
    samples themselves are all on disk; the count follows from the file
    size. A trailing, incomplete record is left out.
    """
    with open(path, "r+b") as f:
        header = f.read(256)
        signals = int(header[252:256].decode("ascii").strip())
        f.seek(256 + signals * 216)
        per_record = sum(int(f.read(8).decode("ascii").strip())
                         for _ in range(signals))
        bytes_per_sample = 3 if header[:1] == b"\xff" else 2
        f.seek(0, os.SEEK_END)
        data = f.tell() - 256 * (signals + 1)
        records = data // (per_record * bytes_per_sample)
        f.seek(236)
        f.write(f"{records:<8d}".encode("ascii"))
    return records


class BdfLogger(GatedLogger):
    """BDF+ (24-bit EDF+) with one-second data records. Every TRIG
    onset is also written as an annotation. A last, partial data record
    is padded by repeating the last sample."""

    extension = ".bdf"

    #: Annotation signals reserved; each holds a few annotations per
    #: one-second record. TRIG keeps every trigger regardless.
    ANNOTATION_SIGNALS = 8

    def _open_file(self, path):
        try:
            import pyedflib
        except ImportError as error:
            raise RuntimeError(
                "BDF logging needs pyedflib (pip install pyedflib). On "
                "Windows with Python 3.13 or later it has to be built, "
                "which needs the Microsoft C++ Build Tools; Python 3.12 "
                "avoids that. Or turn the BDF loggers off in the "
                "Recording settings.") from error

        n = len(self.labels)
        rate = self.sampling_rate
        self._ranges = np.array([_bdf_range(lab, unit) for lab, unit
                                 in zip(self.labels, self.units)])
        # pyedflib warns about spaces in header fields, which the user's
        # subject and recording identifications may well contain.
        warnings.filterwarnings("ignore", "Invalid char", UserWarning,
                                "pyedflib")
        writer = pyedflib.EdfWriter(path, n,
                                    file_type=pyedflib.FILETYPE_BDFPLUS)
        writer.set_number_of_annotation_signals(self.ANNOTATION_SIGNALS)
        writer.setSignalHeaders([{
            "label": self.labels[i][:16],
            "dimension": self.units[i] if self.units[i] != "-" else "",
            "sample_frequency": rate,
            "physical_min": _header_number(self._ranges[i, 0]),
            "physical_max": _header_number(self._ranges[i, 1]),
            "digital_min": _BDF_DIGITAL[0],
            "digital_max": _BDF_DIGITAL[1],
            "transducer": "",
            "prefilter": "",
        } for i in range(n)])
        writer.setStartdatetime(datetime.now())
        if self.subject_id:
            writer.setPatientCode(self.subject_id)
        if self.device_serial:
            writer.setEquipment(self.device_serial)
        if self.recording_id:
            writer.setRecordingAdditional(self.recording_id)
        self._writer = writer
        self._record = int(round(rate * writer.record_duration))
        self._buffer = np.empty((0, n))
        self._status = (self.labels.index("TRIG")
                        if "TRIG" in self.labels else None)

    def _write(self, block):
        if self._status is not None:
            for row in np.flatnonzero(block[:, self._status]):
                onset = (self.samples_written + row) / self.sampling_rate
                value = block[row, self._status]
                self._writer.writeAnnotation(onset, -1, f"{value:g}")
        block = np.clip(block, self._ranges[:, 0], self._ranges[:, 1])
        self._buffer = np.vstack((self._buffer, block))
        while self._buffer.shape[0] >= self._record:
            self._flush(self._buffer[:self._record])
            self._buffer = self._buffer[self._record:]

    def _flush(self, record):
        self._writer.writeSamples(
            [np.ascontiguousarray(record[:, i])
             for i in range(record.shape[1])])

    def _close_file(self):
        if len(self._buffer):
            pad = np.repeat(self._buffer[-1:],
                            self._record - len(self._buffer), axis=0)
            self._flush(np.vstack((self._buffer, pad)))
        self._buffer = np.empty((0, len(self.labels)))
        self._writer.close()
        self._writer = None


class UdpCsvSender(_Described):
    """Each sample as one datagram of comma-separated values with three
    decimals, ending in a newline, as Unicorn Recorder sends them."""

    def __init__(self, ip: str = "127.0.0.1", port: int = 10001, **kwargs):
        super().__init__(**kwargs)
        self._target = (ip, int(port))
        self._socket: Optional[socket.socket] = None
        self.errors = 0

    def start(self):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        super().start()

    def stop(self):
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        super().stop()

    def step(self, data):
        if self._socket is None:
            return None
        for row in _three_decimals(data[PORT_IN]):
            line = ",".join(f"{v:.3f}" for v in row) + "\n"
            try:
                self._socket.sendto(line.encode("ascii"), self._target)
            except OSError:
                # Nobody listening is not an error for a datagram.
                self.errors += 1
        return None


#: LSL channel types by channel role (the XDF convention).
_LSL_TYPES = {layout.SIGNAL: "EEG", layout.TRIGGER: "Markers",
              layout.AUXILIARY: "AUX"}


class LslSender(_Described):
    """A Lab Streaming Layer stream of type EEG at the sampling rate, with
    each channel's label, type and unit, and the headset's serial number,
    in the stream description."""

    def __init__(self, stream_name: str = "RhinoRecorderLSLStream",
                 serial=None, **kwargs):
        """
        Args:
            stream_name: The stream's name and source ID.
            serial: A callable returning the headset's serial number, for
                when the port context does not carry it.
        """
        super().__init__(**kwargs)
        self.stream_name = stream_name
        self._serial = serial
        self._outlet = None

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        import pylsl

        if not self.device_serial and self._serial is not None:
            try:
                self.device_serial = str(self._serial() or "")
            except Exception:  # noqa: BLE001
                pass

        info = pylsl.StreamInfo(self.stream_name, "EEG", len(self.labels),
                                self.sampling_rate, pylsl.cf_double64,
                                self.stream_name)
        described = info.desc().append_child("channels")
        for label, unit, role in zip(self.labels, self.units, self.roles):
            channel = described.append_child("channel")
            channel.append_child_value("label", label)
            channel.append_child_value("type", _LSL_TYPES.get(role, "Misc"))
            channel.append_child_value("unit", "" if unit == "-" else unit)
        if self.device_serial:
            info.desc().append_child("device").append_child_value(
                "serial", self.device_serial)
        # The description must be complete before the outlet copies it.
        self._outlet = pylsl.StreamOutlet(info)
        return out

    def step(self, data):
        if self._outlet is not None:
            block = data[PORT_IN]
            if block.shape[0] == 1:
                self._outlet.push_sample(block[0].tolist())
            else:
                self._outlet.push_chunk(block.tolist())
        return None

    def stop(self):
        self._outlet = None
        super().stop()


class SweepTap(_Described):
    """The last ``seconds`` of samples, laid out for a sweeping display:
    sample *k* lives in slot ``k % capacity``."""

    def __init__(self, seconds: float = 10.0, **kwargs):
        super().__init__(**kwargs)
        self.seconds = float(seconds)
        self._lock = threading.Lock()
        self.capacity = int(self.seconds * layout.SAMPLING_RATE)
        self._buffer = np.zeros((self.capacity, len(layout.CHANNELS)))
        self.total = 0

    def setup(self, data, port_context_in):
        out = super().setup(data, port_context_in)
        with self._lock:
            self.capacity = int(self.seconds * self.sampling_rate)
            self._buffer = np.zeros((self.capacity, len(self.labels)))
            self.total = 0
        return out

    def step(self, data):
        block = data[PORT_IN]
        with self._lock:
            n = block.shape[0]
            slots = (self.total + np.arange(n)) % self.capacity
            self._buffer[slots] = block
            self.total += n
        return None

    def sweep(self) -> tuple[np.ndarray, int]:
        """A copy of the buffer and the number of samples seen so far."""
        with self._lock:
            return self._buffer.copy(), self.total

    def latest(self, n: int) -> np.ndarray:
        """The last ``n`` samples (fewer at the start), oldest first."""
        with self._lock:
            n = min(n, self.total, self.capacity)
            if n == 0:
                return np.empty((0, self._buffer.shape[1]))
            slots = (self.total - n + np.arange(n)) % self.capacity
            return self._buffer[slots].copy()
