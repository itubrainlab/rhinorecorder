# Rhino Recorder user manual

Rhino Recorder acquires, shows, records and streams data from the g.tec
**Unicorn Hybrid Black**. It works like g.tec's Unicorn Recorder, on
Windows, macOS and Linux, and is built on [g.Pype](https://gpype.gtec.at)
with the licence-free [gpype-rhino](https://github.com/itubrainlab/gpype-rhino)
Bluetooth driver.

## Opening a device

Pair the headset in the system's Bluetooth settings first. On Linux, also
bind it to a serial port (`sudo rfcomm bind 0 <address>`).

When Rhino Recorder starts, it lists the paired headsets it can find.
Choose one, or type its name (for example `UN-2024.08.41`), and press
**Open**. On Linux, enter its serial port (`/dev/rfcomm0`); on Windows,
its COM port if it is not listed. **Simulated device** runs without a
headset.

Rhino Recorder connects once to check that the headset answers. If it
does not, make sure it is switched on, in range and paired.

On macOS the connection goes through a small helper app, RhinoConnect,
which gpype-rhino builds the first time (it needs the Xcode command line
tools). macOS asks once for Bluetooth access.

## Toolbar

- **Play / Stop** starts or stops data acquisition. Stop also ends a
  running recording.
- **Record** starts or stops recording. If acquisition is not running,
  it starts both.
- **Settings** (gear) opens the settings, as tabs. Settings can only be changed
  while acquisition is stopped.
- **?** opens this manual.

The toolbar also holds the processing controls (see *Processing and
display*) and the status icons.

## Status icons

- **Wireless data loss** turns orange while samples are being lost in
  transmission. Its tooltip counts the samples lost since acquisition
  started. Keep 2.4 GHz traffic low near the headset.
- **Network interfaces** is blue while at least one network input or
  output is enabled, grey otherwise.
- **Battery level** shows the headset's battery.
- **Disconnect** (link) stops everything and returns to the device list.

## Processing and display

- **Scaling** sets the displayed amplitude range of the EEG channels.
- **OSCAR** (on by default) removes motion, cable, blink and other
  artifacts. g.Pype runs
  OSCAR right at the source, so with OSCAR on, *all* outputs, raw ones
  included, carry OSCAR-processed EEG, delayed by about 0.33 s. Switching
  OSCAR restarts acquisition, so the box is disabled while recording; the
  status bar says "OSCAR on" while it runs. OSCAR also removes the
  electrodes' DC offsets, and needs about two seconds to settle after
  acquisition starts, so a recording begins 3 s after the start at the
  earliest. OSCAR has no settings of its
  own. In tests on a Unicorn Hybrid Black it removed most movement and
  cable artifacts but left many blinks on the frontal channel.
- **Filter** (default 0.1–30 Hz): 0.1–30, 0.1–50, 0.5–30, 0.5–50, 1–30,
  1–50, 2–30 or 2–50 Hz bandpass; >0.1, >0.5, >1 or >2 Hz highpass; <20 or <50 Hz lowpass; or
  none. Filters are 4th-order Butterworth IIR filters.
- **Notch**: 50 Hz, 60 Hz, 50 & 60 Hz, or cascading versions that also
  remove every harmonic below 125 Hz; or none.

Filter and notch apply to the EEG channels of the display and of the
processed outputs, and can be changed while recording.

## Data viewer

Shows the eight EEG channels over 10 seconds, sweeping from left to right.
The blue line is the newest sample.

Below the channels, the **TRIG** row shows every trigger as a marker with
its value, and a tick in the same colour crosses all channels at that
moment. Each trigger value has its own colour, the same every time, so
recurring events are easy to spot. Labels of triggers close together are
staggered on two lines. Two triggers within one sample (4 ms) cannot be
told apart: only the first is kept.

## Signal quality

The **Quality** column to the right of the traces has one indicator per
channel, on that channel's row: green while its signal varies as EEG
does, red while it is flat, too noisy (loose electrode, movement,
mains) or drifting, grey while it settles in the first seconds after the
start. It judges the raw EEG filtered to 1–30 Hz over the last two
seconds. An electrode without skin contact can look quiet after that
filter, so a channel is also bad when its raw signal swings by more than
10 mV in that time, or when it only follows what all channels share. Hover
over the viewer to see each channel's verdict and how much it varies, in
microvolts.

## Acquisition settings

Choose which signals besides EEG are acquired and written to files and
streams: Accelerometer, Gyroscope, Battery Level, Counter, Validation
Indicator, Timing. The channel order is:

| Ch. | Name | Content |
|---|---|---|
| 1–8 | EEG 1–8 | EEG in microvolts |
| 9–11 | ACC X, Y, Z | Accelerometer in g |
| 12–14 | GYR X, Y, Z | Gyroscope in deg/s |
| 15 | CNT | Sample counter |
| 16 | BAT | Battery level in percent |
| 17 | VALID | 1 if no sample was lost before this one, else 0 |
| 18 | DT | Milliseconds between this sample's arrival and the previous one's |
| 19 | TRIG | Trigger value, 0 when there is none (Unicorn Recorder calls this channel STATUS) |

Channels that are excluded are left out and the others move up. The test
signal input source is not available: gpype-rhino does not implement the
command that switches the headset to it.

## Recording settings

Four loggers, each with its own switch, folder and file prefix:

- **Raw Data CSV Logger** and **Raw Data BDF Logger** record the signal as
  acquired, unfiltered. Default prefix `RhinoRawDataRecorder`.
- **Processed Data CSV Logger** and **Processed Data BDF Logger** record
  the filtered EEG. Default prefix `RhinoRecorder`.

Files are named `<prefix>_<YYYYMMDD>_<HHMMSS>.csv` or `.bdf`; the default
folder is `Documents/RhinoRecorder`. All loggers start and stop at the
same sample, so their files line up row for row.

**CSV**: one row per sample, one column per channel, three decimals,
after a header row with the channel names. Read it with
`pandas.read_csv(path)` or the `read_recording.py` example.

**BDF**: BDF+ (24-bit EDF+), readable by EDFbrowser, MNE-Python,
pyedflib and others. EEG keeps the headset's full 24-bit resolution.
Every trigger is also stored as an annotation. *Local subject
identification* and *Local recording identification* go into the BDF+
header. A BDF file whose recording was cut short (the program was killed
or crashed) lacks its record count in the header, and most readers refuse
it; `rhinorecorder.nodes.repair_bdf(path)` restores it, and the
`read_recording.py` example does so on its own. The CSV files are always
complete up to the last sample written.

## Network settings

- **Trigger UDP Input** receives triggers from another program, such as a
  stimulus presentation tool. Send the trigger value as ASCII text in a
  UDP datagram, e.g. in Python:
  `socket.socket(socket.AF_INET, socket.SOCK_DGRAM).sendto(b"1", ("127.0.0.1", 10000))`.
  It appears in the TRIG channel on the sample at which it arrived. The
  default is 127.0.0.1, port 10000. (Unicorn Recorder uses 1000; ports
  below 1024 need administrator rights on Linux, and on macOS can only be
  used on all network interfaces, so a port below 1024 on 127.0.0.1 also
  listens to other computers on your network there.)
- **Raw / Processed Data UDP Output** sends each sample as one datagram of
  comma-separated values with three decimals, ending in a newline
  (default ports 10002 and 10001).
- **Raw / Processed Data LSL Output** publishes a Lab Streaming Layer
  stream (type `EEG`, 250 Hz, channel labels and units in its
  description; default names `RhinoRecorderRawDataLSLStream` and
  `RhinoRecorderLSLStream`).

The trigger input port must differ from the output ports.

## Device settings

Shows the headset's name, the connection and the software versions. The
firmware version and the digital outputs are not available: gpype-rhino
does not implement those commands.

## Using Rhino Recorder in an experiment

A stimulus program sends a trigger over UDP at each event; Rhino Recorder
writes it into the TRIG channel beside the EEG, records both to CSV or
BDF for offline analysis, and streams both over UDP or LSL for online
processing.

## Licence

Rhino Recorder is MIT licensed. g.Pype, which it runs on, is under the
g.tec Non-Commercial License: free for private and educational use (for
example academic research and teaching) with g.tec amplifiers, which the
Unicorn Hybrid Black is. The status bar shows when g.Pype runs without
a licence, in non-commercial use. Commercial use
needs a licence from g.tec.
