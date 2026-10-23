#!/bin/sh
# Install Rhino Recorder for the current user: copies this folder to
# ~/.local/share/RhinoRecorder/app, adds a menu entry with its icon and a
# rhino-recorder command in ~/.local/bin, then sets it up (downloads
# g.Pype and the libraries from PyPI). No administrator rights needed.
set -eu

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/RhinoRecorder/app"
BIN="$HOME/.local/bin"

case "$(uname -m)" in
    x86_64|amd64) ;;
    *) echo "Rhino Recorder needs an x86_64 PC (g.Pype has no build for $(uname -m))." >&2
       exit 1 ;;
esac
glibc="$(ldd --version 2>/dev/null | head -1 | grep -o '[0-9]\+\.[0-9]\+$' || true)"
if [ -n "$glibc" ] && [ "$(printf '%s\n2.34\n' "$glibc" | sort -V | head -1)" != "2.34" ]; then
    echo "Rhino Recorder needs glibc 2.34 or newer (this system has $glibc)," >&2
    echo "e.g. Ubuntu 22.04, Debian 12, Fedora 35 or later." >&2
    exit 1
fi

if [ "$HERE" != "$APP" ]; then
    echo "Copying Rhino Recorder to $APP"
    rm -rf "$APP"
    mkdir -p "$APP"
    cp -a "$HERE/." "$APP/"
fi

mkdir -p "$BIN" "$DATA/applications" \
    "$DATA/icons/hicolor/scalable/apps" "$DATA/icons/hicolor/256x256/apps"
ln -sf "$APP/rhino-recorder" "$BIN/rhino-recorder"
cp "$APP/rhino-recorder.svg" "$DATA/icons/hicolor/scalable/apps/rhino-recorder.svg"
cp "$APP/rhino-recorder.png" "$DATA/icons/hicolor/256x256/apps/rhino-recorder.png"
cat > "$DATA/applications/rhino-recorder.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Rhino Recorder
GenericName=EEG Recorder
Comment=Acquire, view, record and stream EEG from the Unicorn Hybrid Black
Exec="$APP/rhino-recorder" %U
Icon=rhino-recorder
Terminal=false
Categories=Science;Education;MedicalSoftware;
StartupWMClass=rhino-recorder
EOF
update-desktop-database "$DATA/applications" >/dev/null 2>&1 || true
gtk-update-icon-cache -q "$DATA/icons/hicolor" >/dev/null 2>&1 || true

echo "Setting up (downloads g.Pype and the libraries; a few minutes)..."
build="$(cat "$APP/build-id")"
"$APP/python/bin/python3" -I "$APP/bootstrap.py" "$APP" \
    "$DATA/RhinoRecorder/runtime/$build"

echo
echo "Rhino Recorder is installed: open it from your applications menu, or"
echo "run rhino-recorder (add ~/.local/bin to PATH if the shell cannot find it)."
