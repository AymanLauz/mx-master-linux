# MX Master Linux

A userspace daemon for the **Logitech MX Master 3S** on Linux that unlocks all mouse buttons and lets you map each one to any action — key combos, shell commands, or system controls.

Built because Logitech's official software (Logi Options+) doesn't exist on Linux.

> **Status:** Active development — see [Development Journey](#development-journey) for progress.

---

## The Problem

The MX Master 3S has 12 distinct inputs. On Linux without this daemon:

| Input | Status |
|-------|--------|
| Left / Right click | ✅ Works |
| Back / Forward buttons | ✅ Works |
| Scroll wheel (roll) | ✅ Works |
| Scroll wheel click (middle) | ⚠️ Clicks but no auto-scroll mode |
| Mode Shift button | ❌ Silent (not seen by OS) |
| Gesture button | ❌ Silent (not seen by OS) |
| Thumb wheel (side scroll) | ❌ Silent (not seen by OS) |

The missing buttons require speaking Logitech's **HID++ 2.0** protocol directly to the mouse firmware to activate them.

---

## What This Does

| Input | Configured behavior |
|-------|---------------------|
| Scroll wheel click | Auto-scroll mode (move mouse to scroll) |
| Mode Shift button | Take a screenshot (Flameshot) |
| Gesture button (click) | Super key (open app launcher) |
| Gesture button + move mouse | Workspace switch (like 3-finger swipe) |
| Thumb wheel | Volume up / down |
| Everything else | Configurable via `~/.config/mx-master/config.yaml` |

---

## Requirements

- Linux with Wayland
- Python 3.10+
- `ydotool` — key simulation on Wayland
- `flameshot` — screenshots
- `wireplumber` (`wpctl`) — volume control
- User must be in the `input` and `plugdev` groups:

```bash
sudo usermod -aG input,plugdev $USER
# then log out and back in
```

---

## Installation

```bash
git clone https://github.com/aymanlauz/mx-master-linux.git
cd mx-master-linux
pip install -e .
sudo bash install.sh
```

The install script registers the daemon as a systemd user service that starts automatically on login.

---

## Configuration

Edit `~/.config/mx-master/config.yaml`:

```yaml
buttons:
  middle_click:
    action: auto_scroll          # built-in auto-scroll mode

  mode_shift:
    action: command
    value: "flameshot gui"

  gesture_click:
    action: key
    value: "super"

  gesture_move:
    action: workspace_swipe      # built-in: left/right swipe switches workspaces

  thumb_wheel_up:
    action: volume_up
    step: 5                      # percent per tick

  thumb_wheel_down:
    action: volume_down
    step: 5

  back:
    action: key
    value: "alt+Left"

  forward:
    action: key
    value: "alt+Right"
```

Restart the daemon after editing:
```bash
systemctl --user restart mx-master
```

---

## Usage

```bash
# Start manually (foreground, with debug output)
python -m mx_master --debug

# List detected devices
python -m mx_master --list-devices

# Use a custom config file
python -m mx_master --config /path/to/config.yaml
```

---

## How It Works

```
Mouse (Bluetooth HID)
       │
       ├─► /dev/hidraw1 ──► HID++ 2.0 commands ──► Activates hidden buttons
       │                                            (thumb wheel, gesture, mode shift)
       │
       └─► /dev/input/event14 ──► evdev ──► Reads all button/scroll events
                                                │
                                          config.yaml mapping
                                                │
                                         Action Runner
                                          ├─ key        → ydotool key <combo>
                                          ├─ command    → subprocess
                                          ├─ volume     → wpctl set-volume
                                          ├─ auto_scroll → uinput scroll injection
                                          └─ workspace  → ydotool key super+Page_Up/Down
```

### Technical Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| HID++ 2.0 | `/dev/hidraw` (raw file I/O) | Activate hidden mouse buttons |
| Input events | `python-evdev` | Read all button/scroll events |
| Key simulation | `ydotool` | Synthesize key presses (Wayland) |
| Scroll injection | `evdev.UInput` | Inject scroll events for auto-scroll |
| Volume control | `wpctl` (wireplumber) | Adjust system volume |
| Config | `PyYAML` | Button → action mapping file |
| Service | `systemd --user` | Run on login, restart on crash |

---

## Development Journey

Each commit in this repo represents one working stage. The git history tells the full build story:

1. **Project scaffold** — README, packaging, config schema, systemd service
2. **Device detection** — find the mouse across `/dev/hidraw*` and `/dev/input/event*`
3. **HID++ 2.0 protocol** — speak to the mouse firmware, unlock hidden buttons
4. **evdev event listener** — read every button press from the kernel
5. **Config system** — YAML-based button → action mapping
6. **Action runner** — execute key combos, commands, volume, screenshots
7. **Auto-scroll mode** — middle click enters scroll-by-movement mode
8. **Gesture button** — click = Super, move = workspace switch
9. **Systemd integration** — run as a proper background service

---

## License

MIT — do whatever you want with it.
