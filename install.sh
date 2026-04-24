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
    rm -rf "$SHARE_DIR"
    echo "Done."
}

install_packages() {
    echo "==> Installing system dependencies (apt)..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y --no-install-recommends \
        python3 python3-tk policykit-1 lm-sensors
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
exec python3 $SHARE_DIR/imac_fan_control.py "\$@"
EOF
    chmod 0755 "$BIN_PATH"

    if [[ -f "$SRC_DIR/imac-fan-control.svg" ]]; then
        install -m 0644 "$SRC_DIR/imac-fan-control.svg" "$ICON_PATH"
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
        update-desktop-database -q || true
    fi
    if command -v gtk-update-icon-cache >/dev/null; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
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
