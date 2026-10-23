"""A simulated Unicorn Hybrid Black, for trying RhinoRecorder without a
headset.

It is simulated at the byte level: :class:`SimulatedLink` stands in for
the Bluetooth serial channel, answers the start and stop commands, and
delivers 45-byte frames at 250 Hz in bursts, as the radio does. Everything
above it -- gpype_rhino's decoder, its loss detection, the g.Pype source --
is the real code.

The signal: alpha (10 Hz) waxing and waning over background noise, a
large DC offset per electrode as on real dry electrodes, 50 Hz line
noise, a blink on the frontal channels now and then, gravity on the
accelerometer, a slowly draining battery, and a lost frame every so
often. Electrode 8 is noisy, so the signal quality scope has something
to show.
"""
from __future__ import annotations

import struct
import threading
import time
from typing import Optional

import numpy as np
from gpype_rhino import RhinoHybridBlack, protocol
from gpype_rhino.protocol import RhinoDevice

SIMULATED_SERIAL = "UN-SIMULATED"

#: Fraction of frames the simulated radio loses.
LOSS_RATE = 1 / 4000


def encode(counter: int, eeg_uv: np.ndarray, accel_g: np.ndarray,
           gyro_dps: np.ndarray, battery: int) -> bytes:
    """One frame, as the headset sends it."""
    counts = np.clip(np.round(eeg_uv / protocol.EEG_UV_PER_COUNT),
                     -(1 << 23), (1 << 23) - 1).astype(np.int64)
    body = bytearray(protocol.HEADER)
    body.append(battery & 0x0F)
    for value in counts:
        body += int(value & 0xFFFFFF).to_bytes(3, "big")
    motion = np.concatenate((accel_g / protocol.ACCEL_G_PER_COUNT,
                             gyro_dps / protocol.GYRO_DPS_PER_COUNT))
    body += struct.pack("<6h", *np.clip(np.round(motion), -32768, 32767)
                        .astype(int))
    body += struct.pack("<I", counter & 0xFFFFFFFF)
    body += protocol.FOOTER
    return bytes(body)


class SignalModel:
    """Synthetic EEG and motion, one scan at a time."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = np.random.default_rng(seed)
        self.offsets = self.rng.uniform(-30000, 30000, protocol.NUM_EEG)
        self.alpha_phase = self.rng.uniform(0, 2 * np.pi, protocol.NUM_EEG)
        self.alpha_gain = np.array([0.5, 0.7, 0.8, 0.7, 1.0, 1.2, 1.4, 1.2])
        self.noise_sd = np.full(protocol.NUM_EEG, 3.0)
        self.noise_sd[7] = 90.0
        self.drift = np.zeros(protocol.NUM_EEG)
        self.blink_left = 0

    def scan(self, n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = n / protocol.SAMPLING_RATE
        envelope = 6 + 5 * np.sin(2 * np.pi * 0.1 * t)
        eeg = (self.offsets
               + envelope * self.alpha_gain
               * np.sin(2 * np.pi * 10 * t + self.alpha_phase)
               + 15 * np.sin(2 * np.pi * 50 * t)
               + self.rng.normal(0, self.noise_sd))
        self.drift = 0.999 * self.drift + self.rng.normal(0, 0.5,
                                                          protocol.NUM_EEG)
        eeg += self.drift
        if self.blink_left == 0 and self.rng.random() < 1 / 1500:
            self.blink_left = 100
        if self.blink_left:
            phase = (100 - self.blink_left) / 100
            eeg[:3] += 120 * np.sin(np.pi * phase) * np.array([1, 0.6, 0.6])
            self.blink_left -= 1
        accel = np.array([0.02, -0.05, 1.0]) + self.rng.normal(0, 0.003, 3)
        gyro = self.rng.normal(0, 0.4, 3)
        return eeg, accel, gyro


class SimulatedLink:
    """Stands in for gpype_rhino's SerialLink and BridgeLink."""

    def __init__(self, seed: Optional[int] = None):
        self.model = SignalModel(seed)
        self.battery = 15
        self._pending = bytearray()
        self._ready = threading.Condition()
        self._streaming = False
        self._thread: Optional[threading.Thread] = None
        self._counter = 0

    # -- the link interface gpype_rhino uses -------------------------------

    def open(self, timeout: float) -> None:
        pass

    def close(self) -> None:
        self._stream(False)

    def write(self, data: bytes) -> None:
        if data == protocol.CMD_START:
            self._feed(b"\x00\x00\x00")
            self._stream(True)
        elif data == protocol.CMD_STOP:
            self._stream(False)

    def read(self, size: int, timeout: float) -> bytes:
        with self._ready:
            self._ready.wait_for(lambda: len(self._pending) >= size, timeout)
            data = bytes(self._pending[:size])
            del self._pending[:size]
            return data

    def read_some(self, timeout: float) -> bytes:
        with self._ready:
            self._ready.wait_for(lambda: self._pending, timeout)
            data = bytes(self._pending)
            self._pending.clear()
            return data

    def drain(self) -> None:
        with self._ready:
            self._pending.clear()

    # -- the simulated headset ---------------------------------------------

    def _feed(self, data: bytes) -> None:
        with self._ready:
            self._pending += data
            self._ready.notify_all()

    def _stream(self, on: bool) -> None:
        if on and not self._streaming:
            self._streaming = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        elif not on and self._streaming:
            self._streaming = False
            thread, self._thread = self._thread, None
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=1)

    def _run(self) -> None:
        start = time.perf_counter()
        sent = 0
        rng = self.model.rng
        while self._streaming:
            due = int((time.perf_counter() - start) * protocol.SAMPLING_RATE)
            frames = []
            while sent < due:
                eeg, accel, gyro = self.model.scan(self._counter)
                if self._counter % (protocol.SAMPLING_RATE * 120) == 0 \
                        and self._counter and self.battery > 1:
                    self.battery -= 1
                if rng.random() >= LOSS_RATE:
                    frames.append(encode(self._counter, eeg, accel, gyro,
                                         self.battery))
                self._counter += 1
                sent += 1
            if frames:
                self._feed(b"".join(frames))
            # Bluetooth delivers in bursts of a few frames.
            time.sleep(rng.uniform(0.008, 0.03))


def simulated_device(serial: str = SIMULATED_SERIAL,
                     seed: Optional[int] = None) -> RhinoDevice:
    """A gpype_rhino RhinoDevice whose link is simulated."""
    device = RhinoDevice(serial, port="simulated", transport="serial")
    device._link = SimulatedLink(seed)
    return device


class SimulatedHybridBlack(RhinoHybridBlack):
    """RhinoHybridBlack on a simulated headset."""

    def __init__(self, *args, seed: Optional[int] = None, **kwargs):
        kwargs.setdefault("serial", SIMULATED_SERIAL)
        super().__init__(*args, **kwargs)
        self._seed = seed

    def start(self) -> None:
        if self._device is None:
            device = simulated_device(self._serial or SIMULATED_SERIAL,
                                      self._seed)
            device.start()
            self._device = device
        super().start()
