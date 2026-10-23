Rhino Recorder for Windows
==========================

Acquire, view, record and stream EEG from the g.tec Unicorn Hybrid Black.

Needs
-----
- 64-bit Windows 10 or 11.
- An internet connection the first time: Rhino Recorder then downloads
  g.Pype and the libraries it needs from PyPI (several hundred MB).

Install
-------
Unpack the zip, then double-click install.cmd.

This copies Rhino Recorder to %LOCALAPPDATA%\RhinoRecorder, adds it to
the Start menu with its icon, and sets it up. No administrator rights are
needed. To run it without installing, double-click "Rhino Recorder.cmd"
in this folder.

Remove it with uninstall.cmd (settings and recordings are kept).

The headset
-----------
Pair it in Settings -> Bluetooth & devices. Windows gives it a serial
(COM) port, and Rhino Recorder's device dialog lists the headset with
it, e.g. "UN-2024.10.18 (COM5)". If it is not listed, find the port
under "More Bluetooth settings" (Windows 11: Settings -> Bluetooth &
devices -> Devices -> More Bluetooth settings), on the COM Ports tab, as
the Outgoing port for the headset, and enter it (e.g. COM5) as the
serial port.

Triggers
--------
The trigger input listens on 127.0.0.1, port 10000 by default; send
triggers there. The first time Rhino Recorder streams over LSL, Windows
may ask whether Python may use the network: allow it on private
networks for other computers to receive the stream.

Licence
-------
Rhino Recorder is MIT licensed (LICENSE). g.Pype, which the first launch
installs from PyPI, is under the g.tec Non-Commercial License: free for
private and educational use with a g.tec amplifier; commercial use needs
a licence from g.tec. This package does not contain g.Pype.
