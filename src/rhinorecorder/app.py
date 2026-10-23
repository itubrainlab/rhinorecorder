"""Start Rhino Recorder.

    rhino-recorder                      choose a headset, then record
    rhino-recorder --device UN-2024.08.41
    rhino-recorder --port /dev/rfcomm0  (Linux)
    rhino-recorder --simulate           no headset needed
"""
from __future__ import annotations

import argparse
import sys

from . import __version__


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rhino-recorder",
        description="Acquire, view, record and stream EEG from the g.tec "
                    "Unicorn Hybrid Black.")
    parser.add_argument("--device", metavar="NAME",
                        help="the headset's Bluetooth name, e.g. "
                             "UN-2024.08.41; skips the device dialog")
    parser.add_argument("--port", help="the headset's serial port, e.g. "
                                       "/dev/rfcomm0 or COM5")
    parser.add_argument("--transport", choices=["auto", "serial", "bridge"],
                        default=None)
    parser.add_argument("--simulate", action="store_true",
                        help="use a simulated headset")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    from PySide6.QtWidgets import QApplication

    from .settings import APP_NAME, Settings
    from .ui import theme
    from .ui.connect_dialog import Choice, ConnectDialog
    from .ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    # Matches the installed rhino-recorder.desktop, for the taskbar icon
    # on Linux desktops.
    app.setDesktopFileName("rhino-recorder")
    app.setApplicationDisplayName("Rhino Recorder")
    theme.apply(app)

    settings = Settings.load()
    choice = None
    if args.simulate:
        from .simulator import SIMULATED_SERIAL
        choice = Choice(SIMULATED_SERIAL, "", "auto", True)
    elif args.device or args.port:
        choice = Choice(args.device or "", args.port or "",
                        args.transport or settings.device.transport, False)
        settings.device.serial = choice.serial
        settings.device.port = choice.port
        settings.device.transport = choice.transport

    # The device dialog comes back after every disconnect, as Unicorn
    # Suite does, until the user quits it.
    while True:
        if choice is None:
            dialog = ConnectDialog(settings)
            if dialog.exec() != ConnectDialog.DialogCode.Accepted:
                break
            choice = dialog.choice
        window = MainWindow(settings, choice)
        reconnect = []
        window.disconnected.connect(lambda: reconnect.append(True))
        window.show()
        app.exec()
        if not reconnect:
            break
        choice = None
    settings.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
