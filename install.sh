#!/usr/bin/env bash
set -e

echo "==> Installing MX Master Linux daemon"

# Check groups
if ! groups | grep -q input; then
    echo "WARNING: You are not in the 'input' group."
    echo "Run: sudo usermod -aG input $USER"
    echo "Then log out and back in. Re-run this script after."
    exit 1
fi

# Install Python package
echo "==> Installing Python package..."
pip install -e . --quiet

# Install config
CONFIG_DIR="$HOME/.config/mx-master"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
if [ ! -f "$CONFIG_FILE" ]; then
    mkdir -p "$CONFIG_DIR"
    cp config/example.yaml "$CONFIG_FILE"
    echo "==> Config written to $CONFIG_FILE"
else
    echo "==> Config already exists at $CONFIG_FILE (not overwriting)"
fi

# Install udev rule (gives input group access to the mouse's hidraw device)
UDEV_RULE="/etc/udev/rules.d/99-mx-master.rules"
if [ ! -f "$UDEV_RULE" ] || ! diff -q udev/99-mx-master.rules "$UDEV_RULE" &>/dev/null; then
    echo "==> Installing udev rule (requires sudo)..."
    sudo cp udev/99-mx-master.rules "$UDEV_RULE"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw
    echo "==> udev rule installed"
else
    echo "==> udev rule already up to date"
fi

# Install systemd service
SERVICE_DIR="$HOME/.config/systemd/user"
mkdir -p "$SERVICE_DIR"
cp systemd/mx-master.service "$SERVICE_DIR/mx-master.service"

systemctl --user daemon-reload
systemctl --user enable mx-master
systemctl --user start mx-master

echo ""
echo "Done! Daemon is running."
echo "Edit $CONFIG_FILE to change button mappings."
echo "Then run: systemctl --user restart mx-master"
