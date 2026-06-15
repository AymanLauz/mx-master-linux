"""Execute mapped actions: key combos, commands, volume, screenshots."""

import subprocess
import shutil


class ActionRunner:
    def __init__(self, config: dict, debug: bool = False):
        self._cfg = config
        self._debug = debug
        self._check_deps()

    def _check_deps(self) -> None:
        missing = [t for t in ("ydotool", "wpctl", "flameshot") if not shutil.which(t)]
        if missing:
            print(f"WARNING: Missing tools: {', '.join(missing)}")
            print("Some actions may not work. Install them with your package manager.")

    def run(self, button_name: str) -> None:
        """Look up button_name in config and execute its action."""
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
            # Handled by the daemon directly — not dispatched here
            pass

        else:
            print(f"WARNING: Unknown action '{action}' for button '{button_name}'")

    def workspace_swipe(self, direction: str) -> None:
        """direction: 'left' or 'right'"""
        swipe_cfg = self._cfg.get("workspace_swipe", {})
        combo = swipe_cfg.get(direction, "super+Page_Up" if direction == "left" else "super+Page_Down")
        self._key(combo)

    def _key(self, combo: str) -> None:
        if self._debug:
            print(f"  key: {combo}")
        subprocess.Popen(["ydotool", "key", combo])

    def _command(self, cmd: str) -> None:
        if self._debug:
            print(f"  cmd: {cmd}")
        subprocess.Popen(cmd, shell=True)
