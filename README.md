# Rhino Recorder

<img src="docs/icon.png" alt="A rhino pretending to be a unicorn" width="96" align="right">

Acquire, view, record and stream EEG from the g.tec **Unicorn Hybrid
Black** on Windows, macOS and Linux. Rhino Recorder works like g.tec's
[Unicorn Recorder](https://github.com/unicorn-bi/Unicorn-Recorder-Hybrid-Black),
but runs on [g.Pype](https://gpype.gtec.at) with the licence-free
[gpype-rhino](https://github.com/itubrainlab/gpype-rhino) Bluetooth
driver instead of g.tec's Windows-only Unicorn driver.

![Rhino Recorder](docs/screenshot.png)

## Download

Get the package for your system from the
[latest release](https://github.com/itubrainlab/rhinorecorder/releases/latest):

| System | Package | Install |
|---|---|---|
| Windows 10 or 11, 64-bit | `RhinoRecorder-<version>-windows-x86_64.zip` | Unpack it and double-click `install.cmd`; open Rhino Recorder from the Start menu. |
| macOS 12 or later, Apple Silicon | `RhinoRecorder-<version>-arm64.dmg` | Drag **Rhino Recorder** to Applications. The first time, right-click it and choose **Open** (the app is not notarized). |
| Linux x86_64, glibc 2.34+ (Ubuntu 22.04, Debian 12, Fedora 35 or later) | `RhinoRecorder-<version>-linux-x86_64.tar.gz` | Unpack it and run `./install.sh`; open Rhino Recorder from the applications menu or run `rhino-recorder`. |

None needs administrator rights. **The first launch needs an internet
connection:** the packages contain their own Python, Rhino Recorder and
gpype-rhino, but not g.Pype, which g.tec's licence does not allow to be
bundled. So the first launch downloads g.Pype and the other libraries
from PyPI (several hundred MB, a few minutes), at the versions the
release was tested with; later launches start directly. To remove Rhino
Recorder, run `uninstall.cmd` (Windows) or `./uninstall.sh` (Linux),
which keep your settings and recordings. On macOS, delete the app, and
`~/Library/Application Support/RhinoRecorder/runtime` for the libraries.

## Connecting the headset

Pair the headset with the computer first, then start Rhino Recorder and
choose it in the device list.

- **Windows**: pair it in Settings → Bluetooth & devices. The device list
  shows it with its COM port, e.g. `UN-2024.10.18 (COM5)`.
- **macOS**: pair it in the Bluetooth settings. macOS asks once for
  Bluetooth access.
- **Linux**: pair it in the Bluetooth settings, or with `bluetoothctl`
  (`scan on`, `pair <address>`, `trust <address>`). The device list
  shows it by name.

**Simulated device**, at the bottom of the list, runs without a headset.

## What it does

- **Data viewer**: the eight EEG channels over a 10-second sweep, with
  each channel's signal quality beside it and a TRIG row marking every
  trigger in its own colour. **Scaling**, **Filter** (bandpass, highpass,
  lowpass) and **Notch** (50/60 Hz, cascading) offer Unicorn Recorder's
  predefined choices.
- **Power spectrum** beside the viewer: 0–100 Hz, averaged across the
  electrodes, with the δ, θ, α, β and γ bands shaded. It can be hidden.
- **Filtered | Raw** switch on each view: the EEG after the filter, notch
  and OSCAR, or as acquired.
- **OSCAR** artifact removal (motion, cables, blinks) on the processed
  EEG; raw recordings and streams stay raw.
- **Recording** to four loggers, raw and processed, each as CSV and as
  BDF+, with Unicorn Recorder's 19 channels in the same order (EEG 1–8,
  ACC, GYR, CNT, BAT, VALID, DT, TRIG).
- **Network**: a UDP trigger input into the TRIG channel; raw and
  processed outputs over UDP and LSL.
- **Status**: wireless data loss, network interfaces and battery.

The user manual is in the app (the **?** button) and in
[src/rhinorecorder/MANUAL.md](src/rhinorecorder/MANUAL.md).
[examples/](examples) has Python equivalents of Unicorn Recorder's
examples: a UDP trigger sender, a UDP receiver, an LSL receiver, and a
CSV/BDF reader in place of the MATLAB import script.

### Differences from Unicorn Recorder

| | Unicorn Recorder | Rhino Recorder |
|---|---|---|
| Platforms | Windows | Windows, macOS, Linux |
| Driver | g.tec Unicorn driver | gpype-rhino (Bluetooth) |
| Test signal input, digital outputs, firmware version | yes | no: gpype-rhino does not implement these commands |
| Power spectrum, raw view | no | yes |
| OSCAR | processed outputs | processed outputs and filtered views; switching it restarts acquisition |
| Default ports | trigger 1000, UDP outputs 1001 and 1002 | trigger 10000, UDP outputs 10001 and 10002: no administrator rights needed |
| File and stream names | `UnicornRecorder…` | `RhinoRecorder…` (configurable) |
| CSV | values only | a header row with the channel names |
| Without a headset | none | a simulated headset |

## Running from source

Rhino Recorder needs Python 3.10 or later (3.12 recommended: on Windows,
pyedflib has no wheels for 3.13 and later) and git. In a clone of this
repository:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[test]"
rhino-recorder
```

This installs g.Pype (with its GUI, LSL and file-format extras) from PyPI
and gpype-rhino from GitHub. On macOS, gpype-rhino builds its
RhinoConnect Bluetooth helper on first use, which needs the Xcode
command line tools (`xcode-select --install`). On Linux, Qt needs the
usual desktop libraries (on Debian/Ubuntu, `libxcb-cursor0` among them).

| Option | |
|---|---|
| `--device NAME` | open this headset, e.g. `UN-2024.08.41`, without the device list |
| `--port PORT` | its serial port, e.g. `COM5`, where the name does not find it |
| `--simulate` | use the simulated headset |
| `--version` | print the version |

### Tests

The tests need no headset: they run against the simulated one, through
the real driver, pipeline, files and sockets.

```bash
pytest
```

### How it works

```text
                              ┌─ UnicornLayout (raw) ─┬─ status tap (quality, raw views)
HeadsetSource ─┐              │                       └─ raw CSV / BDF / UDP / LSL
UDPReceiver ───┴─ Router ─────┤
                              └─ UnicornLayout ─ Filter ─ Notch ─┬─ scope tap (filtered views)
                                                                 └─ processed CSV / BDF / UDP / LSL
```

g.Pype runs OSCAR inside the source, so every output would get OSCAR's
EEG. Rhino Recorder's source copies the raw EEG in front of OSCAR; the
copy rides through OSCAR untouched and in the same rows, and the raw
layout takes its EEG from it.

- `recorder.py` builds and runs the pipeline, with no UI code, so it can
  be scripted and tested.
- `sources.py` holds the headset's sources, real and simulated, with the
  raw EEG copy.
- `nodes.py` holds Rhino Recorder's g.Pype nodes: the raw EEG copy, the
  Unicorn channel layout, filters that can be swapped while running,
  loggers that start and stop at a shared sample, the UDP and LSL
  outputs, and buffers for the display.
- `spectrum.py` computes the power spectrum (Welch's estimate, averaged
  across the electrodes).
- `simulator.py` simulates the headset at the byte level, so the
  simulated device runs the real gpype-rhino decoder.
- `ui/` is the PySide6/pyqtgraph interface.

### Packages and releases

`packaging/` builds the three packages; each runs on macOS (and the Linux
and Windows ones on Linux) and needs uv, git and the project's `.venv`:

```bash
packaging/macos/build_app.sh          # dist/RhinoRecorder-<version>-<arch>.dmg (macOS only)
packaging/linux/build_linux.sh        # dist/RhinoRecorder-<version>-linux-x86_64.tar.gz
packaging/windows/build_windows.sh    # dist/RhinoRecorder-<version>-windows-x86_64.zip
```

Each package pins the library versions installed in the `.venv`, which
its first launch then installs. The macOS app is built for the
architecture of the Python it bundles (set `PYTHON_HOME` to an x86_64
CPython 3.12 for Intel Macs) and signed ad hoc only.

The [Build packages](.github/workflows/build.yml) workflow builds all
three on GitHub Actions, installs each on its own platform and runs
[packaging/smoke_test.py](packaging/smoke_test.py) with the package's
own Python. To release:

1. write the notes in `docs/releases/v<version>.md`;
2. set `__version__` in `src/rhinorecorder/__init__.py` and commit;
3. push a `v<version>` tag.

The workflow publishes the release, with the three packages and
`SHA256SUMS`, once all of them pass. It checks the packages on the
simulated headset only, so try a release candidate with a real headset
first.

## Licence

Rhino Recorder is MIT licensed; see [LICENSE](LICENSE).

It runs on g.Pype, which is under the **g.tec Non-Commercial License
(GNCL)**: free for private and educational use (academic research,
teaching) with a g.tec amplifier, which the Unicorn Hybrid Black is. Read
the GNCL before you use Rhino Recorder. In particular:

- Commercial use needs a commercial g.Pype licence from g.tec.
- The GNCL forbids redistributing g.Pype as a standalone executable or
  other bundled artefact. That is why the packages install g.Pype from
  PyPI on first launch instead of containing it.
- Without a g.Pype licence, g.Pype marks its own output as
  non-commercial. Rhino Recorder writes its files and streams with its
  own nodes, which carry no such mark; the status bar shows when g.Pype
  runs unlicensed. That does not change what the GNCL allows.
