#!/usr/bin/env bash
# Installer for iMac Fan Control on Debian-based systems (ParrotOS, Kali,
# Debian, Ubuntu, Linux Mint).  Installs the script, a polkit rule that lets
# normal users write to applesmc fan files, and a .desktop launcher.
#
# Usage:   sudo ./install.sh
# Remove:  sudo ./install.sh --uninstall

set -euo pipefail

PREFIX="${PREFIX:-/usr/local}"
BIN_PATH="$PREFIX/bin/imac-fan-control"
SHARE_DIR="$PREFIX/share/imac-fan-control"
DESKTOP_PATH="/usr/share/applications/imac-fan-control.desktop"
POLKIT_PATH="/usr/share/polkit-1/actions/org.imacfan.policy"
ICON_PATH="$PREFIX/share/icons/hicolor/scalable/apps/imac-fan-control.svg"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

require_root() {
    if [[ $EUID -ne 0 ]]; then
        echo "This installer must be run as root.  Try: sudo $0" >&2
        exit 1
    fi
}

uninstall() {
    require_root
    echo "Removing iMac Fan Control..."
    rm -f "$BIN_PATH" "$DESKTOP_PATH" "$POLKIT_PATH" "$ICON_PATH"
    rm -f /usr/share/pixmaps/imac-fan-control.svg
    for sz in 16 22 24 32 48 64 128 256; do
        rm -f "/usr/share/icons/hicolor/${sz}x${sz}/apps/imac-fan-control.png"
    done
    # Refuse to recurse if PREFIX got emptied / points at root.
    if [[ -z "${SHARE_DIR:-}" || "$SHARE_DIR" == "/" || "$SHARE_DIR" != *"/imac-fan-control" ]]; then
        echo "ERROR: refusing to 'rm -rf' suspicious SHARE_DIR='$SHARE_DIR'" >&2
        exit 1
    fi
    rm -rf "$SHARE_DIR"
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    echo "Done."
}

install_packages() {
    echo "==> Installing system dependencies (apt)..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
        python3 policykit-1 lm-sensors librsvg2-bin desktop-file-utils

    # Tk package name varies by distro / Python version.  Try the generic
    # name first, then fall back to the versioned one (e.g. python3.11-tk).
    if ! apt-get install -y --no-install-recommends python3-tk; then
        local pyver
        pyver="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
        echo "python3-tk not available, trying python${pyver}-tk..."
        apt-get install -y --no-install-recommends "python${pyver}-tk" || {
            echo "ERROR: could not install Tk for Python 3." >&2
            echo "Check that 'main' (Debian/Parrot) or 'universe' (Ubuntu)" >&2
            echo "is enabled in /etc/apt/sources.list, then retry." >&2
            exit 1
        }
    fi

    # Verify Tk actually imports.
    if ! python3 -c 'import tkinter' 2>/dev/null; then
        echo "ERROR: Tk is installed but 'import tkinter' still fails." >&2
        exit 1
    fi
}

ensure_applesmc() {
    echo "==> Ensuring the 'applesmc' kernel module is loaded..."
    if ! lsmod | grep -q '^applesmc'; then
        modprobe applesmc || {
            echo "WARNING: Could not load applesmc.  Are you on a Mac?" >&2
        }
    fi
    # Auto-load on boot
    echo "applesmc" > /etc/modules-load.d/applesmc.conf
}

install_files() {
    echo "==> Installing files into $PREFIX..."
    install -d "$SHARE_DIR" "$(dirname "$BIN_PATH")" "$(dirname "$ICON_PATH")"
    install -m 0755 "$SRC_DIR/imac_fan_control.py" "$SHARE_DIR/imac_fan_control.py"

    cat > "$BIN_PATH" <<EOF
#!/usr/bin/env bash
exec python3 "$SHARE_DIR/imac_fan_control.py" "\$@"
EOF
    chmod 0755 "$BIN_PATH"

    # Icon: install to the hicolor scalable dir AND to /usr/share/pixmaps
    # (fallback location some DEs still scan).
    if [[ -f "$SRC_DIR/imac-fan-control.svg" ]]; then
        install -m 0644 "$SRC_DIR/imac-fan-control.svg" "$ICON_PATH"
        install -d /usr/share/pixmaps
        install -m 0644 "$SRC_DIR/imac-fan-control.svg" \
            /usr/share/pixmaps/imac-fan-control.svg

        # Also render PNGs at common sizes if rsvg-convert is available.
        if command -v rsvg-convert >/dev/null; then
            for sz in 16 22 24 32 48 64 128 256; do
                d="/usr/share/icons/hicolor/${sz}x${sz}/apps"
                install -d "$d"
                rsvg-convert -w "$sz" -h "$sz" \
                    "$SRC_DIR/imac-fan-control.svg" \
                    -o "$d/imac-fan-control.png" 2>/dev/null || true
            done
        fi
    fi

    if [[ -f "$SRC_DIR/imac-fan-control.desktop" ]]; then
        install -m 0644 "$SRC_DIR/imac-fan-control.desktop" "$DESKTOP_PATH"
    fi

    if [[ -f "$SRC_DIR/org.imacfan.policy" ]]; then
        install -m 0644 "$SRC_DIR/org.imacfan.policy" "$POLKIT_PATH"
    fi
}

post_install() {
    if command -v update-desktop-database >/dev/null; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
    if command -v xdg-desktop-menu >/dev/null; then
        xdg-desktop-menu forceupdate --mode system 2>/dev/null || true
    fi
    # MATE / Cinnamon occasionally cache the menu per-user; nudge it.
    if command -v mate-panel >/dev/null; then
        pkill -HUP mate-panel 2>/dev/null || true
    fi
}

main() {
    if [[ "${1:-}" == "--uninstall" ]]; then
        uninstall
        exit 0
    fi
    require_root
    install_packages
    ensure_applesmc
    install_files
    post_install
    cat <<EOF

================================================================
iMac Fan Control installed.

    Launch from a terminal:    imac-fan-control
    Or look for it in your application menu (Utilities).

    For full fan-control privileges run with sudo or pkexec:
        pkexec imac-fan-control

================================================================
EOF
}

main "$@"
