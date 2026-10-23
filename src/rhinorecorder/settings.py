"""Everything the settings pages edit, with Unicorn Recorder's defaults,
saved as JSON in the user's configuration directory."""
from __future__ import annotations

import dataclasses
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import presets

APP_NAME = "RhinoRecorder"

#: Unicorn Recorder listens for triggers on port 1000, and so does
#: Rhino Recorder (see trigger_bind_address for macOS and Linux).
DEFAULT_TRIGGER_PORT = 1000
#: The default trigger port of settings files written before version 1.
_OLD_TRIGGER_PORT = 11000
#: The default filter and OSCAR of settings files before version 2.
_OLD_DISPLAY = ("1 – 30 Hz", False)
#: Bumped when a settings file needs migrating on load.
SETTINGS_VERSION = 2

_LOOPBACK = ("127.0.0.1", "localhost")


def trigger_bind_address(ip: str, port: int,
                         platform: str = sys.platform) -> str:
    """The address the trigger input listens on.

    macOS lets ordinary programs listen on ports below 1024 only on all
    interfaces (0.0.0.0), not on 127.0.0.1. So there a loopback address
    with such a port listens on all interfaces instead, which still
    receives what is sent to 127.0.0.1, but is also reachable from the
    network. Linux needs root for those ports either way.
    """
    if platform == "darwin" and port < 1024 and ip.strip() in _LOOPBACK:
        return "0.0.0.0"
    return ip


def config_dir() -> Path:
    """Where the settings file lives on this platform."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME


def default_folder() -> str:
    """The default recording folder: ``~/Documents/RhinoRecorder``."""
    return str(Path.home() / "Documents" / APP_NAME)


@dataclass
class Acquisition:
    #: "electrode" or "test signal". gpype-rhino cannot switch the
    #: headset to its test signal, so only "electrode" is offered.
    input_source: str = "electrode"
    accelerometer: bool = True
    gyroscope: bool = True
    battery: bool = True
    counter: bool = True
    validation: bool = True
    timing: bool = True

    def groups(self) -> dict[str, bool]:
        return {"accelerometer": self.accelerometer,
                "gyroscope": self.gyroscope, "battery": self.battery,
                "counter": self.counter, "validation": self.validation,
                "timing": self.timing}


@dataclass
class Logger:
    enabled: bool = True
    folder: str = field(default_factory=default_folder)
    prefix: str = "RhinoRecorder"
    #: BDF only: the subject and recording fields of the BDF+ header.
    subject_id: str = ""
    recording_id: str = ""


@dataclass
class Recording:
    raw_csv: Logger = field(
        default_factory=lambda: Logger(prefix="RhinoRawDataRecorder"))
    raw_bdf: Logger = field(
        default_factory=lambda: Logger(prefix="RhinoRawDataRecorder"))
    processed_csv: Logger = field(default_factory=Logger)
    processed_bdf: Logger = field(default_factory=Logger)

    def loggers(self) -> dict[str, Logger]:
        return {"raw_csv": self.raw_csv, "raw_bdf": self.raw_bdf,
                "processed_csv": self.processed_csv,
                "processed_bdf": self.processed_bdf}


@dataclass
class UdpEndpoint:
    enabled: bool = False
    ip: str = "127.0.0.1"
    port: int = 1001


@dataclass
class LslStream:
    enabled: bool = False
    name: str = "RhinoRecorderLSLStream"


@dataclass
class Network:
    trigger_in: UdpEndpoint = field(default_factory=lambda: UdpEndpoint(
        enabled=True, port=DEFAULT_TRIGGER_PORT))
    raw_udp: UdpEndpoint = field(
        default_factory=lambda: UdpEndpoint(port=1002))
    raw_lsl: LslStream = field(default_factory=lambda: LslStream(
        name="RhinoRecorderRawDataLSLStream"))
    processed_udp: UdpEndpoint = field(
        default_factory=lambda: UdpEndpoint(port=1001))
    processed_lsl: LslStream = field(default_factory=LslStream)

    def any_output(self) -> bool:
        return any(s.enabled for s in (self.raw_udp, self.raw_lsl,
                                       self.processed_udp,
                                       self.processed_lsl))

    def any_enabled(self) -> bool:
        return self.trigger_in.enabled or self.any_output()


@dataclass
class Display:
    scaling: str = presets.DEFAULT_SCALING
    filter: str = presets.DEFAULT_FILTER
    notch: str = presets.DEFAULT_NOTCH
    oscar: bool = True


@dataclass
class Device:
    #: The headset's Bluetooth name, e.g. UN-2024.08.41.
    serial: str = ""
    #: Its serial port, where the name cannot find it (Linux).
    port: str = ""
    #: "auto", "serial" or "bridge"; see gprhino.RhinoDevice.
    transport: str = "auto"


@dataclass
class Settings:
    version: int = SETTINGS_VERSION
    acquisition: Acquisition = field(default_factory=Acquisition)
    recording: Recording = field(default_factory=Recording)
    network: Network = field(default_factory=Network)
    display: Display = field(default_factory=Display)
    device: Device = field(default_factory=Device)

    def problems(self) -> list[str]:
        """What stops these settings from being used; empty if nothing."""
        found = []
        net = self.network
        if net.trigger_in.enabled:
            for name, out in (("Raw Data UDP Output", net.raw_udp),
                              ("Processed Data UDP Output",
                               net.processed_udp)):
                if out.enabled and out.port == net.trigger_in.port:
                    found.append(f"The Trigger UDP Input port must differ "
                                 f"from the {name} port.")
        for name, endpoint in (("Trigger UDP Input", net.trigger_in),
                               ("Raw Data UDP Output", net.raw_udp),
                               ("Processed Data UDP Output",
                                net.processed_udp)):
            if endpoint.enabled and not 0 < endpoint.port < 65536:
                found.append(f"The {name} port must be 1-65535.")
        for name, stream in (("Raw Data LSL Output", net.raw_lsl),
                             ("Processed Data LSL Output",
                              net.processed_lsl)):
            if stream.enabled and not stream.name.strip():
                found.append(f"The {name} needs a stream name.")
        if (net.raw_lsl.enabled and net.processed_lsl.enabled
                and net.raw_lsl.name == net.processed_lsl.name):
            found.append("The raw and processed LSL streams need "
                         "different names.")
        for name, logger in self.recording.loggers().items():
            if logger.enabled and not logger.prefix.strip():
                found.append(f"The {name.replace('_', ' ')} logger needs "
                             f"a file prefix.")
        return found

    # -- persistence -------------------------------------------------------

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        settings = _build(cls, data)
        version = data.get("version", 0) if isinstance(data, dict) else 0
        if version < 1 and \
                settings.network.trigger_in.port == _OLD_TRIGGER_PORT:
            # Version 0 defaulted to 11000 on macOS and Linux.
            settings.network.trigger_in.port = DEFAULT_TRIGGER_PORT
        display = settings.display
        if version < 2 and (display.filter, display.oscar) == _OLD_DISPLAY:
            # Before version 2: 1-30 Hz without OSCAR, left at default.
            display.filter = presets.DEFAULT_FILTER
            display.oscar = True
        settings.version = SETTINGS_VERSION
        return settings

    def save(self, path: Path | None = None) -> None:
        path = path or config_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        tmp.replace(path)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """The saved settings, or the defaults if there are none or they
        cannot be read."""
        path = path or config_dir() / "settings.json"
        try:
            return cls.from_dict(json.loads(path.read_text()))
        except (OSError, ValueError, TypeError):
            return cls()


def _build(kind, data, default=None):
    """Rebuild a dataclass from a dict, keeping ``default``'s value for
    anything the dict lacks or gets wrong, so an old settings file still
    loads."""
    default = default if default is not None else kind()
    if not isinstance(data, dict):
        return default
    values = {}
    for f in dataclasses.fields(kind):
        current = getattr(default, f.name)
        value = data.get(f.name, current)
        if dataclasses.is_dataclass(current):
            value = _build(type(current), value, current)
        elif type(value) is not type(current):
            # bool is an int, and "1000" is not a port: types must match.
            value = current
        values[f.name] = value
    result = kind(**values)
    # Presets renamed or removed since the file was written fall back.
    if isinstance(result, Display):
        if result.filter not in presets.FILTERS:
            result.filter = presets.DEFAULT_FILTER
        if result.notch not in presets.NOTCHES:
            result.notch = presets.DEFAULT_NOTCH
        if result.scaling not in presets.SCALINGS:
            result.scaling = presets.DEFAULT_SCALING
    return result
