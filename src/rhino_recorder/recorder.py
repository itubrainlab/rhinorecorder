"""The recording engine: builds the g.Pype pipeline, runs it, and opens
and closes recordings. Free of any user interface, so it can be driven
from tests and scripts as well as from the window.

The pipeline::

    RhinoHybridBlack ─┐                      ┌─ status tap (battery, loss, quality)
    UDPReceiver ──────┴─ Router ─ UnicornLayout ─┼─ Router (selected channels) ─ raw CSV / BDF / UDP / LSL
                                             └─ Filter ─ Notch ─┬─ scope tap
                                                                └─ Router ─ processed CSV / BDF / UDP / LSL

Only the parts the settings enable are built. With OSCAR on, g.Pype runs
it inside the source's chain, ahead of everything shown here.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import gpype as gp
from gpype.common.constants import Constants

from . import layout, presets
from .nodes import (BdfLogger, CsvLogger, EegFilter, GatedLogger,
                    LslSender, SweepTap, UdpCsvSender, UnicornLayout)
from .settings import Settings, trigger_bind_address

#: Samples per pipeline step. One, so DT is measured per sample.
FRAME_SIZE = 1
#: How far ahead of the newest sample a recording starts or ends, so
#: every logger is still short of that sample when it is told.
GATE_MARGIN = 25
#: Samples from the start until OSCAR's output has settled: its delay
#: (83 samples at 250 Hz) plus the time it takes to remove the electrode
#: offsets, overshooting as it does (measured: a 13 mV swing that fell to
#: 17 uV within 1.6 s). The filters start, and recordings begin, after.
OSCAR_WARMUP = 125 + 3 * layout.SAMPLING_RATE

IDLE, STARTING, RUNNING, STOPPING = "idle", "starting", "running", "stopping"


@dataclass
class Graph:
    """The nodes of one built pipeline that the recorder talks to."""

    pipeline: gp.Pipeline
    source: object
    bandpass: EegFilter
    notch: EegFilter
    scope: SweepTap
    status: SweepTap
    loggers: dict[str, GatedLogger] = field(default_factory=dict)
    sinks: list = field(default_factory=list)


def make_source(settings: Settings, simulate: bool, oscar: bool):
    """The headset's g.Pype source, real or simulated."""
    common = dict(include_accel=True, include_gyro=True, include_aux=True,
                  frame_size=FRAME_SIZE, enable_oscar=oscar, name="rhino")
    if simulate:
        from .simulator import SimulatedHybridBlack
        return SimulatedHybridBlack(**common)
    from gpype_rhino import RhinoHybridBlack
    return RhinoHybridBlack(serial=settings.device.serial or None,
                            port=settings.device.port or None,
                            transport=settings.device.transport or "auto",
                            **common)


def _selector(indices: list[int]):
    """A Router that passes the given layout channels, or None for all."""
    if indices == list(range(len(layout.CHANNELS))):
        return None
    return gp.Router(input_channels={Constants.Defaults.PORT_IN: indices})


def build(settings: Settings, simulate: bool = False) -> Graph:
    """Build, but do not start, the pipeline the settings describe."""
    display = settings.display
    net = settings.network
    p = gp.Pipeline()
    source = make_source(settings, simulate, display.oscar)
    arranged = UnicornLayout(name="layout")
    if net.trigger_in.enabled:
        trigger = gp.UDPReceiver(
            ip=trigger_bind_address(net.trigger_in.ip, net.trigger_in.port),
            port=net.trigger_in.port, name="trigger")
        merge = gp.Router(input_channels=[gp.Router.ALL, gp.Router.ALL],
                          name="merge")
        p.connect(source, merge["in1"])
        p.connect(trigger, merge["in2"])
        p.connect(merge, arranged)
    else:
        p.connect(source, arranged)

    status = SweepTap(seconds=10, name="status")
    p.connect(arranged, status)

    settle = OSCAR_WARMUP if display.oscar else 0
    bandpass = EegFilter(presets.filter_sos(display.filter), settle=settle,
                         name="filter")
    notch = EegFilter(presets.notch_sos(display.notch), settle=settle,
                      name="notch")
    p.connect(arranged, bandpass)
    p.connect(bandpass, notch)
    scope = SweepTap(seconds=10, name="scope")
    p.connect(notch, scope)

    graph = Graph(p, source, bandpass, notch, scope, status)
    channels = layout.selected(settings.acquisition.groups())
    rec = settings.recording
    for kind, upstream in (("raw", arranged), ("processed", notch)):
        sinks = []
        for fmt, cls in (("csv", CsvLogger), ("bdf", BdfLogger)):
            cfg = rec.loggers()[f"{kind}_{fmt}"]
            if cfg.enabled:
                logger = cls(subject_id=cfg.subject_id,
                             recording_id=cfg.recording_id,
                             name=f"{kind}_{fmt}")
                graph.loggers[f"{kind}_{fmt}"] = logger
                sinks.append(logger)
        udp = getattr(net, f"{kind}_udp")
        if udp.enabled:
            sinks.append(UdpCsvSender(ip=udp.ip, port=udp.port,
                                      name=f"{kind}_udp"))
        lsl = getattr(net, f"{kind}_lsl")
        if lsl.enabled:
            sinks.append(LslSender(stream_name=lsl.name,
                                   serial=source.device_serial,
                                   name=f"{kind}_lsl"))
        if not sinks:
            continue
        select = _selector(channels)
        if select is not None:
            p.connect(upstream, select)
            upstream = select
        for sink in sinks:
            p.connect(upstream, sink)
        graph.sinks += sinks
    return graph


def recording_path(folder: str, prefix: str, stamp: datetime,
                   extension: str) -> str:
    """``folder/prefix_YYYYMMDD_HHMMSS.ext``, as Unicorn Recorder names
    files, with ``_2``, ``_3`` ... added if that file exists."""
    base = os.path.join(os.path.expanduser(folder),
                        f"{prefix}_{stamp:%Y%m%d_%H%M%S}")
    path, n = base + extension, 1
    while os.path.exists(path):
        n += 1
        path = f"{base}_{n}{extension}"
    return path


class Recorder:
    """Acquisition and recording for one headset.

    :meth:`start` and :meth:`stop` block (connecting can take many
    seconds), so a user interface calls them off its main thread. The
    ``on_*`` callbacks may be called from any thread.
    """

    def __init__(self, settings: Settings, simulate: bool = False):
        self.settings = settings
        self.simulate = simulate
        self.graph: Optional[Graph] = None
        self.state = IDLE
        self.recording_paths: list[str] = []
        self._lock = threading.RLock()
        self.on_state: Callable[[str], None] = lambda state: None
        self.on_error: Callable[[str], None] = lambda message: None
        self.on_recording: Callable[[bool], None] = lambda on: None

    # -- acquisition -------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.state == RUNNING

    @property
    def recording(self) -> bool:
        graph = self.graph
        return bool(graph and any(lg.recording
                                  for lg in graph.loggers.values()))

    def _set_state(self, state: str) -> None:
        self.state = state
        self.on_state(state)

    def start(self, record: bool = False) -> None:
        """Connect to the headset and start acquiring; with ``record``,
        start recording as well.

        Raises:
            ValueError: If the settings are not usable.
            ConnectionError, OSError, RuntimeError: If the headset, a
                port or an output could not be opened.
        """
        with self._lock:
            if self.state != IDLE:
                return
            problems = self.settings.problems()
            if problems:
                raise ValueError("\n".join(problems))
            self._set_state(STARTING)
            graph = None
            try:
                graph = build(self.settings, self.simulate)
                graph.pipeline.add_error_handler(self._failed)
                graph.pipeline.start()
            except BaseException:
                if graph is not None:
                    try:
                        graph.pipeline.stop()
                    except Exception:  # noqa: BLE001
                        pass
                self._set_state(IDLE)
                raise
            self.graph = graph
            self._set_state(RUNNING)
            if record:
                self.start_recording()

    def stop(self) -> None:
        """Stop recording and acquisition, and release the headset."""
        with self._lock:
            graph = self.graph
            if graph is None:
                return
            self._set_state(STOPPING)
            self.stop_recording()
            try:
                graph.pipeline.stop()
            finally:
                self.graph = None
                self._set_state(IDLE)

    def _failed(self, entry) -> None:
        """The pipeline stopped on an error (on ioiocore's monitor thread)."""
        try:
            message = str(entry["message"])
        except Exception:  # noqa: BLE001
            message = str(entry)
        threading.Thread(target=self._fail, args=(message,),
                         daemon=True).start()

    def _fail(self, message: str) -> None:
        try:
            self.stop()
        except Exception:  # noqa: BLE001
            pass
        self.on_error(message)

    # -- recording -----------------------------------------------------------

    def start_recording(self) -> list[str]:
        """Open a file for every enabled logger; returns their paths."""
        with self._lock:
            graph = self.graph
            if graph is None or self.recording:
                return self.recording_paths
            stamp = datetime.now()
            loggers = graph.loggers
            # OSCAR fills its delay with zeros, then needs to settle.
            oscar = getattr(graph.source, "_oscar_node", None) is not None
            first = OSCAR_WARMUP if oscar else 0
            start_at = max([first] + [lg.seen for lg in loggers.values()]) \
                + GATE_MARGIN
            serial = self.device_serial
            paths = []
            try:
                for key, logger in loggers.items():
                    cfg = self.settings.recording.loggers()[key]
                    path = recording_path(cfg.folder, cfg.prefix, stamp,
                                          logger.extension)
                    logger.device_serial = serial
                    logger.begin(path, start_at)
                    paths.append(path)
            except BaseException:
                for logger in loggers.values():
                    logger.end()
                raise
            self.recording_paths = paths
        if paths:
            self.on_recording(True)
        return paths

    def stop_recording(self, timeout: float = 2.0) -> None:
        """Close every recording at the same sample, and wait (up to
        ``timeout``) for the files to be complete."""
        with self._lock:
            graph = self.graph
            was = self.recording
            if graph is not None and was:
                loggers = list(graph.loggers.values())
                end_at = max(lg.seen for lg in loggers) + GATE_MARGIN
                for logger in loggers:
                    logger.end(end_at)
                deadline = time.monotonic() + timeout
                while (any(lg.recording for lg in loggers)
                       and time.monotonic() < deadline
                       and self.state == RUNNING):
                    time.sleep(0.01)
                for logger in loggers:
                    logger.end()
        if was:
            self.on_recording(False)

    # -- live settings -------------------------------------------------------

    def set_filter(self, name: str) -> None:
        self.settings.display.filter = name
        graph = self.graph
        if graph is not None:
            graph.bandpass.set_sos(presets.filter_sos(name))

    def set_notch(self, name: str) -> None:
        self.settings.display.notch = name
        graph = self.graph
        if graph is not None:
            graph.notch.set_sos(presets.notch_sos(name))

    # -- status ----------------------------------------------------------------

    @property
    def device_serial(self) -> str:
        graph = self.graph
        if graph is not None:
            try:
                return graph.source.device_serial()
            except Exception:  # noqa: BLE001
                pass
        return self.settings.device.serial

    @property
    def lost_scans(self) -> int:
        """Samples lost in transmission since acquisition started."""
        graph = self.graph
        device = getattr(graph.source, "_device", None) if graph else None
        return int(getattr(device, "lost_scans", 0) or 0)

    @property
    def marked(self) -> bool:
        """Whether g.Pype marks this run's output non-commercial."""
        graph = self.graph
        return bool(graph and any(getattr(s, "_marked", False)
                                  for s in graph.sinks + [graph.scope]))
