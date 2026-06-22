"""Execute mapped actions: key combos, commands, volume, screenshots."""

import subprocess
import shutil
import time
import threading

import evdev
from evdev import ecodes, UInput


# Key name → evdev keycode
_KEY_MAP = {
    "super":     ecodes.KEY_LEFTMETA,
    "ctrl":      ecodes.KEY_LEFTCTRL,
    "alt":       ecodes.KEY_LEFTALT,
    "shift":     ecodes.KEY_LEFTSHIFT,
    "left":      ecodes.KEY_LEFT,
    "right":     ecodes.KEY_RIGHT,
    "up":        ecodes.KEY_UP,
    "down":      ecodes.KEY_DOWN,
    "page_up":   ecodes.KEY_PAGEUP,
    "page_down": ecodes.KEY_PAGEDOWN,
    "tab":       ecodes.KEY_TAB,
    "f1": ecodes.KEY_F1, "f2": ecodes.KEY_F2, "f3": ecodes.KEY_F3,
    "f4": ecodes.KEY_F4, "f5": ecodes.KEY_F5, "f6": ecodes.KEY_F6,
}


class ActionRunner:
    def __init__(self, config: dict, debug: bool = False):
        self._cfg = config
        self._debug = debug
        self._uinput = UInput(
            {ecodes.EV_KEY: list(_KEY_MAP.values())},
            name="mx-master-keys",
        )
        self._check_deps()

    def close(self) -> None:
        self._uinput.close()

    def _check_deps(self) -> None:
        missing = [t for t in ("wpctl", "flameshot") if not shutil.which(t)]
        if missing:
            print(f"WARNING: Missing tools: {', '.join(missing)}")

    def run(self, button_name: str) -> None:
        action_cfg = self._cfg.get("buttons", {}).get(button_name)
        if not action_cfg:
            if self._debug:
                print(f"  No mapping for '{button_name}'")
            return
        self._dispatch(action_cfg, button_name)

    def _dispatch(self, action_cfg: dict, button_name: str) -> None:
        action = action_cfg.get("action")

        if action == "key":
            self._key(action_cfg["value"])

        elif action == "command":
            self._command(action_cfg["value"])

        elif action == "volume_up":
            step = action_cfg.get("step", 5)
            self._command(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {step}%+")

        elif action == "volume_down":
            step = action_cfg.get("step", 5)
            self._command(f"wpctl set-volume @DEFAULT_AUDIO_SINK@ {step}%-")

        elif action in ("auto_scroll", "workspace_swipe"):
            pass

        else:
            print(f"WARNING: Unknown action '{action}' for '{button_name}'")

    def workspace_swipe(self, direction: str) -> None:
        swipe_cfg = self._cfg.get("workspace_swipe", {})
        combo = swipe_cfg.get(direction, "ctrl+alt+left" if direction == "left" else "ctrl+alt+right")
        self._key(combo)

    def _key(self, combo: str) -> None:
        if self._debug:
            print(f"  key: {combo}")
        keys = [_KEY_MAP[k.lower()] for k in combo.split("+") if k.lower() in _KEY_MAP]
        if not keys:
            print(f"WARNING: unknown key combo '{combo}'")
            return
        # Run in a thread so we don't block the event loop
        threading.Thread(target=self._send_keys, args=(keys,), daemon=True).start()

    def _send_keys(self, keys: list) -> None:
        for k in keys:
            self._uinput.write(ecodes.EV_KEY, k, 1)
        self._uinput.syn()
        time.sleep(0.05)
        for k in reversed(keys):
            self._uinput.write(ecodes.EV_KEY, k, 0)
        self._uinput.syn()

    def _command(self, cmd: str) -> None:
        if self._debug:
            print(f"  cmd: {cmd}")
        subprocess.Popen(cmd, shell=True)
