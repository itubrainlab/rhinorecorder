#!/bin/sh
# Remove Rhino Recorder for the current user. Settings
# (~/.config/RhinoRecorder) and recordings (~/Documents/RhinoRecorder)
# are kept.
set -eu
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -f "$HOME/.local/bin/rhino-recorder" \
    "$DATA/applications/rhino-recorder.desktop" \
    "$DATA/icons/hicolor/scalable/apps/rhino-recorder.svg" \
    "$DATA/icons/hicolor/256x256/apps/rhino-recorder.png"
rm -rf "$DATA/RhinoRecorder"
update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
echo "Rhino Recorder is removed. Settings and recordings are kept."
