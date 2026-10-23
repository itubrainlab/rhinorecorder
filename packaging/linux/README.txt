Rhino Recorder for Linux
========================

Acquire, view, record and stream EEG from the g.tec Unicorn Hybrid Black.

Needs
-----
- An x86_64 PC with glibc 2.34 or newer (Ubuntu 22.04, Debian 12,
  Fedora 35 or later). g.Pype has no build for ARM Linux.
- An internet connection the first time: Rhino Recorder then downloads
  g.Pype and the libraries it needs from PyPI (several hundred MB).
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
Pair it in the system's Bluetooth settings, then bind it to a serial
port and give that port in Rhino Recorder's device dialog:

    sudo rfcomm bind 0 <headset Bluetooth address>     -> /dev/rfcomm0

To use the port without root, add yourself to the dialout group and log
in again:  sudo usermod -aG dialout $USER

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
a licence from g.tec. This package does not contain g.Pype.
