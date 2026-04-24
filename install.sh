#!/usr/bin/env bash
set -euo pipefail

APP_NAME="imac-fan-studio"
SCRIPT_NAME="imac_fan_gui.py"
INSTALL_DIR="/opt/${APP_NAME}"
BIN_PATH="/usr/local/bin/${APP_NAME}"
DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./install.sh"
  exit 1
fi

if [[ ! -f "$SCRIPT_NAME" ]]; then
  echo "Run this installer from the repository root (missing $SCRIPT_NAME)."
  exit 1
fi

echo "[1/5] Installing dependencies..."
apt update
apt install -y python3 python3-tk lm-sensors

echo "[2/5] Installing application files..."
mkdir -p "$INSTALL_DIR"
install -m 755 "$SCRIPT_NAME" "$INSTALL_DIR/$SCRIPT_NAME"

if [[ -f README.md ]]; then
  install -m 644 README.md "$INSTALL_DIR/README.md"
fi

echo "[3/5] Creating launcher command..."
cat > "$BIN_PATH" <<EOF
#!/usr/bin/env bash
exec pkexec /usr/bin/python3 "$INSTALL_DIR/$SCRIPT_NAME" "\$@"
EOF
chmod 755 "$BIN_PATH"

echo "[4/5] Creating desktop entry..."
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=iMac Fan Studio
Comment=Retro fan control utility for iMac hwmon sensors
Exec=$BIN_PATH
Terminal=false
Type=Application
Categories=System;Monitor;
StartupNotify=true
EOF
chmod 644 "$DESKTOP_FILE"

echo "[5/5] Installation completed"
echo "Run from terminal: $APP_NAME"
echo "Or launch 'iMac Fan Studio' from your desktop menu."
