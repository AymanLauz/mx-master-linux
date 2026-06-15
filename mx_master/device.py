"""Locate the MX Master 3S hidraw and evdev devices."""

from pathlib import Path
import evdev

# Logitech MX Master 3S identifiers
_VENDOR_ID = "046d"
_PRODUCT_IDS = {"b034", "c548", "c94d"}  # BT and USB receiver variants
_NAME_HINT = "mx master"


def find_hidraw() -> str:
    """Return the /dev/hidrawN path for the mouse, or raise RuntimeError."""
    for entry in sorted(Path("/sys/class/hidraw").iterdir()):
        try:
            uevent = (entry / "device" / "uevent").read_text(errors="ignore").lower()
        except OSError:
            continue
        if _VENDOR_ID in uevent and any(pid in uevent for pid in _PRODUCT_IDS):
            return f"/dev/{entry.name}"
        # Fallback: match by HID_NAME if the uevent contains the friendly name
        try:
            hid_name = (entry / "device" / "report_descriptor").parent
            name_file = entry / "device" / "uevent"
            text = name_file.read_text(errors="ignore").lower()
            if _NAME_HINT in text:
                return f"/dev/{entry.name}"
        except OSError:
            continue
    raise RuntimeError(
        "MX Master 3S not found in /dev/hidraw*. "
        "Is the mouse connected and are you in the 'input' group?"
    )


def find_evdev() -> evdev.InputDevice:
    """Return the evdev InputDevice for the mouse, or raise RuntimeError."""
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
        except (OSError, PermissionError):
            continue
        if _NAME_HINT in dev.name.lower():
            # Prefer the device that reports relative motion (the pointer, not keyboard HID)
            caps = dev.capabilities()
            if evdev.ecodes.EV_REL in caps:
                return dev
    raise RuntimeError(
        "MX Master 3S evdev device not found. "
        "Is the mouse connected and are you in the 'input' group?"
    )


def list_all() -> None:
    """Print all detected HID and evdev devices (for --list-devices)."""
    print("=== hidraw devices ===")
    for entry in sorted(Path("/sys/class/hidraw").iterdir()):
        try:
            uevent = (entry / "device" / "uevent").read_text(errors="ignore").strip()
            hid_name = next((l for l in uevent.splitlines() if "HID_NAME" in l), "")
            hid_id = next((l for l in uevent.splitlines() if "HID_ID" in l), "")
            print(f"  /dev/{entry.name}  {hid_id}  {hid_name}")
        except OSError:
            print(f"  /dev/{entry.name}  (unreadable)")

    print("\n=== evdev input devices ===")
    for path in evdev.list_devices():
        try:
            dev = evdev.InputDevice(path)
            print(f"  {dev.path}  {dev.name}")
        except OSError:
            pass
