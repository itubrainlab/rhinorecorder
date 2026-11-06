"""The headset's g.Pype sources, real and simulated.

Both are g.Pype's own :class:`~gpype.HybridBlack`, which drives the
headset through g.tec's gtec-unicorn driver, with two additions:

- **Acquisition-time stamps.** g.Pype places every trigger on the EEG by
  comparing host-clock stamps. HybridBlack stamps a frame when its read
  returns, and records g.tec's measured Bluetooth delay (``DEVICE_DELAY_MS``,
  40 ms) without applying it, so triggers would land that much early
  against the EEG they happened during. These sources stamp each frame
  with when its last scan was acquired instead: the read's return, less
  the scans still waiting behind it in the driver (a scan early in a
  Bluetooth burst waits for the rest of it), less ``latency_ms``.
- **Raw EEG beside OSCAR.** g.Pype runs OSCAR inside a source's chain, so
  that every output gets OSCAR's EEG. These sources put
  :class:`~rhinorecorder.nodes.RawEegCopy` in front of OSCAR, so the raw
  EEG comes through it untouched and in the same rows: raw files, streams
  and views stay raw, and only the processed ones carry OSCAR, as in
  Unicorn Recorder.
"""
from __future__ import annotations

from typing import Optional

from gpype.backend.sources.hybrid_black import HybridBlack
from gpype.common._private import channels

from .nodes import RawEegCopy
from .simulator import SimulatedHybridBlack

#: g.tec's measured Bluetooth delay of the Unicorn Hybrid Black, in ms.
DEVICE_LATENCY_MS = float(getattr(HybridBlack, "DEVICE_DELAY_MS", 40))


class _AcquisitionStamped:
    """Stamps each frame with when its last scan was acquired."""

    def __init__(self, *args, latency_ms: Optional[float] = None, **kwargs):
        super().__init__(*args, **kwargs)
        latency_ms = DEVICE_LATENCY_MS if latency_ms is None else latency_ms
        if latency_ms < 0:
            raise ValueError(f"latency_ms must not be negative, got "
                             f"{latency_ms}.")
        self._latency_s = float(latency_ms) / 1000.0

    def cycle(self):
        # HybridBlack's reader has just put the frame it read, stamped with
        # the read's return, into _current_frame, and cycles. Every scan
        # still waiting in the driver was acquired after this frame's last
        # one, so that frame's last scan was acquired that many scan
        # periods before the newest one, which reached this computer no
        # later than now, latency_ms after it was acquired.
        frame, device = self._current_frame, self._device
        if frame is not None and device is not None:
            try:
                waiting = device.get_stream_status().available_scans
            except Exception:  # noqa: BLE001 - keep the arrival stamp
                waiting = None
            if waiting is not None:
                acquired = (channels.stamp_clock() - self._latency_s
                            - waiting / self.SAMPLING_RATE)
                frame[:, self._total_channels:] = channels.wrap_time(acquired)
        return super().cycle()


class _WithRawEeg:

    def middle_nodes(self) -> list:
        nodes = super().middle_nodes()
        # Without OSCAR there are no middle nodes, and the EEG is raw.
        return [RawEegCopy(name="raw_eeg"), *nodes] if nodes else nodes


class HeadsetSource(_WithRawEeg, _AcquisitionStamped, HybridBlack):
    """The headset, over g.tec's gtec-unicorn driver."""


class SimulatedSource(_WithRawEeg, _AcquisitionStamped, SimulatedHybridBlack):
    """The simulated headset."""
