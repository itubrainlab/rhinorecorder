#!/bin/bash
# Build "Rhino Recorder.app" and a DMG for macOS.
#
#     packaging/macos/build_app.sh
#
# Needs: macOS with the Xcode command line tools (swiftc, codesign),
# uv, git, and the project's .venv (pip install -e ".[test]"), which
# provides the tested library versions and PySide6 for the icon.
#
# The app carries its own Python (a relocatable python-build-standalone
# build, as uv installs them), RhinoRecorder, gpype-rhino and a prebuilt
# RhinoConnect helper. It does not carry g.Pype: the g.tec Non-Commercial
# License forbids redistributing g.Pype as a standalone executable or
# other bundled artefact. The app installs g.Pype and the other pinned
# libraries from PyPI on first launch (see bootstrap.py).
#
# Environment:
#   PYTHON_HOME   the Python to bundle (default: uv's CPython 3.12)
#   OUT           output folder (default: dist/)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$ROOT/dist}"
DEV_PY="$ROOT/.venv/bin/python"
GPYPE_RHINO_URL="https://github.com/itubrainlab/gpype-rhino"

[ -x "$DEV_PY" ] || { echo "Run pip install -e '.[test]' into .venv first." >&2; exit 1; }
PYTHON_HOME="${PYTHON_HOME:-$(dirname "$(dirname "$(readlink -f "$(uv python find 3.12)")")")}"
[ -x "$PYTHON_HOME/bin/python3" ] || { echo "No Python at $PYTHON_HOME" >&2; exit 1; }
ARCH="$(file -b "$(readlink -f "$PYTHON_HOME/bin/python3")" | grep -o 'arm64\|x86_64' | head -1)"

VERSION="$("$DEV_PY" -c 'import rhino_recorder; print(rhino_recorder.__version__)')"
COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$ROOT" diff --quiet HEAD -- src pyproject.toml packaging || COMMIT="$COMMIT-dirty"
BUILD_ID="$VERSION-$COMMIT-$ARCH"
# gpype-rhino at the commit the project's .venv was tested with.
GPYPE_RHINO_COMMIT="$("$DEV_PY" - <<'PY'
import json, glob
path = glob.glob(__import__("sysconfig").get_paths()["purelib"]
                 + "/gpype_rhino-*.dist-info/direct_url.json")
print(json.load(open(path[0]))["vcs_info"]["commit_id"] if path else "main")
PY
)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APP="$OUT/Rhino Recorder.app"
RES="$APP/Contents/Resources"
echo "Building Rhino Recorder $BUILD_ID (gpype-rhino $GPYPE_RHINO_COMMIT)"

# -- wheels -------------------------------------------------------------------
mkdir -p "$WORK/wheels"
uv build --quiet --wheel --out-dir "$WORK/wheels" "$ROOT"
git clone --quiet "$GPYPE_RHINO_URL" "$WORK/gpype-rhino"
git -C "$WORK/gpype-rhino" checkout --quiet "$GPYPE_RHINO_COMMIT"
uv build --quiet --wheel --out-dir "$WORK/wheels" "$WORK/gpype-rhino"

# -- pinned requirements, at the versions the tests ran with -----------------
"$DEV_PY" - "$ROOT/pyproject.toml" "$WORK/gpype-rhino/pyproject.toml" \
    > "$WORK/requirements.in" <<'PY'
import sys, tomllib
for path in sys.argv[1:]:
    for dep in tomllib.load(open(path, "rb"))["project"]["dependencies"]:
        if not dep.replace("-", "_").startswith("gpype_rhino"):
            print(dep)
PY
uv pip freeze --python "$DEV_PY" --exclude-editable | grep -v '^gpype-rhino' \
    > "$WORK/constraints.txt"
uv pip compile --quiet --python-version 3.12 \
    --python-platform "$([ "$ARCH" = arm64 ] && echo aarch64 || echo x86_64)-apple-darwin" \
    --constraint "$WORK/constraints.txt" --no-header --no-annotate \
    "$WORK/requirements.in" -o "$WORK/requirements.txt"

# -- the bundle ---------------------------------------------------------------
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/wheels"
cp -R "$PYTHON_HOME" "$RES/python"
rm -rf "$RES/python/include" "$RES/python/share" \
    "$RES/python/lib/python3.12/idlelib" "$RES/python/lib/python3.12/turtledemo"
"$RES/python/bin/python3" -I -m compileall -q -j 0 "$RES/python/lib" >/dev/null || true
cp "$WORK"/wheels/*.whl "$RES/wheels/"
cp "$WORK/requirements.txt" "$RES/requirements.txt"
cp "$HERE/../bootstrap.py" "$RES/bootstrap.py"
cp "$ROOT/LICENSE" "$RES/LICENSE"
echo "$BUILD_ID" > "$RES/build-id"
sh "$WORK/gpype-rhino/src/gprhino/macos/build.sh" "$RES" >/dev/null
"$DEV_PY" "$HERE/make_icns.py" "$ROOT/src/rhino_recorder/resources/rhino_recorder.svg" \
    "$RES/RhinoRecorder.icns" >/dev/null
install -m 755 "$HERE/launcher.sh" "$APP/Contents/MacOS/RhinoRecorder"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Rhino Recorder</string>
    <key>CFBundleDisplayName</key><string>Rhino Recorder</string>
    <key>CFBundleIdentifier</key><string>dk.itu.brainlab.RhinoRecorder</string>
    <key>CFBundleExecutable</key><string>RhinoRecorder</string>
    <key>CFBundleIconFile</key><string>RhinoRecorder</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$BUILD_ID</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>LSApplicationCategoryType</key><string>public.app-category.education</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSBluetoothAlwaysUsageDescription</key>
    <string>Rhino Recorder reads the Unicorn EEG headset over Bluetooth.</string>
    <key>NSLocalNetworkUsageDescription</key>
    <string>Rhino Recorder receives triggers and streams data over UDP and LSL.</string>
</dict>
</plist>
PLIST

# Ad-hoc signature: enough to run here; distributing to other Macs without
# Gatekeeper warnings needs a Developer ID signature and notarization.
codesign --force --deep --sign - "$APP" >/dev/null

# -- disk image -----------------------------------------------------------------
STAGE="$WORK/dmg"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="$OUT/RhinoRecorder-$VERSION-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -quiet -volname "Rhino Recorder" -srcfolder "$STAGE" -ov \
    -format UDZO "$DMG"

echo "Built:"
du -sh "$APP" "$DMG"
