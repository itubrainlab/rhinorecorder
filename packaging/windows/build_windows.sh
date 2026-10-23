#!/bin/bash
# Build the Windows x86_64 package: dist/RhinoRecorder-<version>-windows-x86_64.zip
#
#     packaging/windows/build_windows.sh
#
# Runs on macOS or Linux; it only downloads and arranges files. Needs uv,
# git and the project's .venv (pip install -e ".[test]"), which provides
# the tested library versions and PySide6 for the icon.
#
# The package carries its own Python (python-build-standalone's Windows
# build, which uv downloads), RhinoRecorder and gpype-rhino. It does not
# carry g.Pype: the g.tec Non-Commercial License forbids redistributing
# g.Pype as a standalone executable or other bundled artefact. The first
# launch installs g.Pype and the other pinned libraries from PyPI (see
# ../bootstrap.py).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${OUT:-$ROOT/dist}"
DEV_PY="$ROOT/.venv/bin/python"
GPYPE_RHINO_URL="https://github.com/itubrainlab/gpype-rhino"
PLATFORM="x86_64-pc-windows-msvc"

[ -x "$DEV_PY" ] || { echo "Run pip install -e '.[test]' into .venv first." >&2; exit 1; }

VERSION="$("$DEV_PY" -c 'import rhinorecorder; print(rhinorecorder.__version__)')"
COMMIT="$(git -C "$ROOT" rev-parse --short HEAD)"
git -C "$ROOT" diff --quiet HEAD -- src pyproject.toml packaging || COMMIT="$COMMIT-dirty"
BUILD_ID="$VERSION-$COMMIT-windows-x86_64"
GPYPE_RHINO_COMMIT="$("$DEV_PY" - <<'PY'
import json, glob, sysconfig
path = glob.glob(sysconfig.get_paths()["purelib"]
                 + "/gpype_rhino-*.dist-info/direct_url.json")
print(json.load(open(path[0]))["vcs_info"]["commit_id"] if path else "main")
PY
)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
NAME="RhinoRecorder-$VERSION-windows-x86_64"
DIR="$WORK/$NAME"
echo "Building Rhino Recorder $BUILD_ID (gpype-rhino $GPYPE_RHINO_COMMIT)"

# -- Python -------------------------------------------------------------------
uv python install --quiet --install-dir "$WORK/py" cpython-3.12-windows-x86_64-none
PYTHON_HOME="$(find "$WORK/py" -maxdepth 1 -type d -name 'cpython-3.12.*-windows-x86_64-none' | head -1)"
[ -n "$PYTHON_HOME" ] || { echo "uv did not install a Windows CPython 3.12" >&2; exit 1; }

# -- wheels (pure Python, so built here for any platform) ---------------------
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
uv pip compile --quiet --python-version 3.12 --python-platform "$PLATFORM" \
    --constraint "$WORK/constraints.txt" --no-header --no-annotate \
    "$WORK/requirements.in" -o "$WORK/requirements.txt"

# -- the folder ---------------------------------------------------------------
mkdir -p "$DIR/wheels"
cp -R "$PYTHON_HOME" "$DIR/python"
# uv adds a "python" symlink to the install; Windows has no use for it.
find "$DIR/python" -maxdepth 1 -type l -delete
rm -rf "$DIR/python/include" "$DIR/python/libs" \
    "$DIR/python/Lib/idlelib" "$DIR/python/Lib/turtledemo"
cp "$WORK"/wheels/*.whl "$DIR/wheels/"
cp "$WORK/requirements.txt" "$DIR/requirements.txt"
cp "$HERE/../bootstrap.py" "$HERE/launcher.py" "$DIR/"
cp "$HERE/install.cmd" "$HERE/install.ps1" "$HERE/uninstall.cmd" \
    "$HERE/uninstall.ps1" "$HERE/Rhino Recorder.cmd" "$HERE/README.txt" "$DIR/"
cp "$ROOT/LICENSE" "$DIR/"
echo "$BUILD_ID" > "$DIR/build-id"
QT_QPA_PLATFORM=offscreen "$DEV_PY" -c '
import sys
from PySide6.QtGui import QGuiApplication, QIcon
app = QGuiApplication([])
QIcon(sys.argv[1]).pixmap(256, 256).save(sys.argv[2], "ICO")
' "$ROOT/src/rhinorecorder/resources/rhinorecorder.svg" "$DIR/rhino-recorder.ico"

# -- zip ------------------------------------------------------------------------
mkdir -p "$OUT"
ZIP="$OUT/$NAME.zip"
rm -f "$ZIP"
"$DEV_PY" - "$WORK" "$NAME" "$ZIP" <<'PY'
import os, sys, zipfile
work, name, out = sys.argv[1:]
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for folder, _, files in os.walk(os.path.join(work, name)):
        for file in sorted(files):
            path = os.path.join(folder, file)
            z.write(path, os.path.relpath(path, work))
PY
echo "Built:"
du -sh "$ZIP"
