"""Load and validate the YAML button-mapping config."""

from pathlib import Path
import yaml

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "mx-master" / "config.yaml"

_DEFAULTS: dict = {
    "buttons": {
        "middle_click":    {"action": "auto_scroll"},
        "mode_shift":      {"action": "command", "value": "flameshot gui"},
        "gesture_click":   {"action": "key",     "value": "super"},
        "gesture_move":    {"action": "workspace_swipe"},
        "thumb_wheel_up":  {"action": "volume_up",   "step": 5},
        "thumb_wheel_down":{"action": "volume_down",  "step": 5},
        "back":            {"action": "key",     "value": "alt+Left"},
        "forward":         {"action": "key",     "value": "alt+Right"},
    },
    "workspace_swipe": {
        "left":  "super+Page_Up",
        "right": "super+Page_Down",
    },
}


def load(path: Path | None = None) -> dict:
    """Load config from path, falling back to built-in defaults for missing keys."""
    cfg = _deep_copy(_DEFAULTS)

    config_path = path or DEFAULT_CONFIG_PATH
    if config_path.exists():
        with open(config_path) as f:
            user_cfg = yaml.safe_load(f) or {}
        _deep_merge(cfg, user_cfg)

    return cfg


def _deep_copy(d: dict) -> dict:
    import copy
    return copy.deepcopy(d)


def _deep_merge(base: dict, override: dict) -> None:
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
