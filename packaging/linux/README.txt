Rhino Recorder for Linux
========================

Acquire, view, record and stream EEG from the g.tec Unicorn Hybrid Black.

Needs
-----
- An x86_64 PC with glibc 2.34 or newer (Ubuntu 22.04, Debian 12,
  Fedora 35 or later). g.Pype has no build for ARM Linux.
- An internet connection the first time: Rhino Recorder then downloads
  g.Pype, g.tec's gtec-unicorn driver and the other libraries it needs
  from PyPI (several hundred MB).
- Qt's usual desktop libraries. On Debian or Ubuntu, if the window does
  not open:  sudo apt install libxcb-cursor0 libegl1

Install
-------
    ./install.sh

This copies Rhino Recorder to ~/.local/share/RhinoRecorder, adds it to
the applications menu with its icon, adds a rhino-recorder command to
~/.local/bin, and sets it up. No administrator rights are needed. To
run it without installing, start ./rhino-recorder from this folder.

Remove it with ./uninstall.sh (settings and recordings are kept).

The headset
-----------
Switch it on. Rhino Recorder's device dialog finds the headsets in range
by a Bluetooth search of a few seconds and lists them by serial, e.g.
UN-2024.10.18; g.tec's gtec-unicorn driver connects to it directly, with
no rfcomm bind. (Pairing it first, in the Bluetooth settings or with
bluetoothctl, does no harm.)

Triggers
--------
The trigger input listens on 127.0.0.1, port 10000 by default; send
triggers there. Linux reserves ports below 1024 for root, so keep any
port you choose in Settings -> Network at 1024 or above.

Licence
-------
Rhino Recorder is MIT licensed (LICENSE). g.Pype, which the first launch
installs from PyPI, is under the g.tec Non-Commercial License: free for
private and educational use with a g.tec amplifier; commercial use needs
a licence from g.tec. The headset's driver, gtec-unicorn, also
installed from PyPI, is under an earlier version of that licence, to be
used only as part of g.Pype. This package contains neither.
