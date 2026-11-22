#!/bin/sh
set -eu

APP_ID=noctalia-util-gui
APP_DIR=/opt/$APP_ID
PYTHON=${PYTHON:-python3}
SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BUILD_VENV=$SOURCE_DIR/.build-venv
LAUNCHER=/usr/local/bin/$APP_ID
APPLICATIONS_DIR=/usr/local/share/applications
ICON_DIR=/usr/local/share/icons/hicolor/scalable/apps
PIXMAP_DIR=/usr/local/share/pixmaps

if [ "$(id -u)" -eq 0 ]; then
    printf 'Run install.sh as your desktop user; it will use sudo to install under %s.\n' \
        "$APP_DIR" >&2
    exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
    printf 'sudo is required to install the application under %s.\n' \
        "$APP_DIR" >&2
    exit 1
fi

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    printf 'Python interpreter not found: %s\n' "$PYTHON" >&2
    exit 1
fi
PYTHON=$(command -v "$PYTHON")

if ! "$PYTHON" - <<'PY'
import sys

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required.")

try:
    import tkinter
    import venv
except ImportError as exc:
    raise SystemExit(f"Python tkinter and venv support are required: {exc}")
PY
then
    exit 1
fi

for file in pyproject.toml README.md LICENSE main.py config.py \
    number_input.py data/noctalia-util-gui.svg \
    data/noctalia-util-gui.png data/noctalia-util-gui.ico \
    data/noctalia-util-gui.desktop data/noctalia-util-gui-launcher; do
    if [ ! -f "$SOURCE_DIR/$file" ]; then
        printf 'Required application file is missing: %s\n' "$SOURCE_DIR/$file" >&2
        exit 1
    fi
done

"$PYTHON" -m venv "$BUILD_VENV"
"$BUILD_VENV/bin/python" -m pip install \
    --disable-pip-version-check --upgrade build
"$BUILD_VENV/bin/python" -m build \
    --wheel --outdir "$SOURCE_DIR/dist" "$SOURCE_DIR"

VERSION=$(sed -n 's/^version = "\([^"]*\)"/\1/p' "$SOURCE_DIR/pyproject.toml" |
    head -n 1)
if [ -z "$VERSION" ]; then
    printf 'Could not read the project version from pyproject.toml.\n' >&2
    exit 1
fi
WHEEL=$SOURCE_DIR/dist/noctalia_util_gui-$VERSION-py3-none-any.whl
if [ ! -f "$WHEEL" ]; then
    printf 'Built wheel not found: %s\n' "$WHEEL" >&2
    exit 1
fi

sudo install -d -o root -g root -m 755 "$APP_DIR"
if ! sudo test -x "$APP_DIR/venv/bin/python"; then
    sudo "$PYTHON" -m venv "$APP_DIR/venv"
fi
sudo "$APP_DIR/venv/bin/python" -m pip install \
    --disable-pip-version-check --only-binary=:all: \
    --upgrade --force-reinstall "$WHEEL"
sudo chown -R root:root "$APP_DIR"
sudo chmod -R go-w "$APP_DIR"

sudo install -Dm755 "$SOURCE_DIR/data/noctalia-util-gui-launcher" "$LAUNCHER"
sudo install -Dm644 "$SOURCE_DIR/data/noctalia-util-gui.desktop" \
    "$APPLICATIONS_DIR/$APP_ID.desktop"
sudo install -Dm644 "$SOURCE_DIR/data/noctalia-util-gui.svg" \
    "$ICON_DIR/$APP_ID.svg"
sudo install -Dm644 "$SOURCE_DIR/data/noctalia-util-gui.png" \
    "$PIXMAP_DIR/$APP_ID.png"

USER_DATA_HOME=${XDG_DATA_HOME:-"$HOME/.local/share"}
case $USER_DATA_HOME in
    /*)
        rm -f \
            "$HOME/.local/bin/$APP_ID" \
            "$USER_DATA_HOME/applications/$APP_ID.desktop" \
            "$USER_DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"
        ;;
    *)
        printf 'Skipping old user-local entry cleanup: XDG_DATA_HOME is not absolute.\n' >&2
        ;;
esac

if command -v xdg-desktop-menu >/dev/null 2>&1; then
    sudo xdg-desktop-menu forceupdate --mode system
fi

printf 'Installed %s under %s.\n' "$APP_ID" "$APP_DIR"
printf 'Launch it from your application menu or run: %s\n' "$LAUNCHER"
