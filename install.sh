#!/usr/bin/env bash
set -euo pipefail

APP_NAME="imac-fan-studio"
INSTALL_DIR="/opt/${APP_NAME}"
BIN_PATH="/usr/local/bin/${APP_NAME}"
DESKTOP_FILE="/usr/share/applications/${APP_NAME}.desktop"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./install.sh"
  exit 1
fi

if [[ ! -f "imac_fan_gui.py" && ! -f "all_fan.py" && ! -f "Victus_Fan.py" ]]; then
  echo "No supported GUI script found in this folder."
  echo "Run this installer from the project root after cloning the repo."
  exit 1
fi

SOURCE_SCRIPT=""
if [[ -f "imac_fan_gui.py" ]]; then
  SOURCE_SCRIPT="imac_fan_gui.py"
elif [[ -f "all_fan.py" ]]; then
  SOURCE_SCRIPT="all_fan.py"
else
  SOURCE_SCRIPT="Victus_Fan.py"
fi

echo "Using GUI script: ${SOURCE_SCRIPT}"

echo "[1/5] Installing dependencies..."
apt update
apt install -y python3 python3-tk lm-sensors policykit-1

echo "[2/5] Installing application files..."
mkdir -p "$INSTALL_DIR"
install -m 755 "$SOURCE_SCRIPT" "$INSTALL_DIR/app.py"
[[ -f README.md ]] && install -m 644 README.md "$INSTALL_DIR/README.md"

echo "[3/5] Creating launcher command..."
cat > "$BIN_PATH" <<'EOF'
#!/usr/bin/env bash
exec pkexec /usr/bin/python3 /opt/imac-fan-studio/app.py "$@"
EOF
chmod 755 "$BIN_PATH"

echo "[4/5] Creating desktop entry..."
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Name=iMac Fan Studio
Comment=Fan control utility for iMac sensors
Exec=$BIN_PATH
Terminal=false
Type=Application
Categories=System;Monitor;
StartupNotify=true
EOF
chmod 644 "$DESKTOP_FILE"

echo "[5/5] Done."
echo "Run: ${APP_NAME}"
