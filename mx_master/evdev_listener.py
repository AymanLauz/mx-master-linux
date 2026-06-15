"""Read standard mouse events from the kernel via evdev."""

import evdev
from evdev import ecodes


# Maps evdev key codes → our internal button names
_BTN_MAP = {
    ecodes.BTN_LEFT:    "left_click",
    ecodes.BTN_RIGHT:   "right_click",
    ecodes.BTN_MIDDLE:  "middle_click",
    ecodes.BTN_SIDE:    "back",
    ecodes.BTN_EXTRA:   "forward",
}

# Maps (EV_REL, rel_code) → internal event names for scroll
_REL_MAP = {
    ecodes.REL_WHEEL:  ("scroll", "vertical"),
    ecodes.REL_HWHEEL: ("scroll", "horizontal"),
}


class EvdevListener:
    """
    Reads events from the mouse's evdev node and yields normalised dicts.

    Yielded event shapes:
      {'type': 'button', 'name': str, 'pressed': bool}
      {'type': 'scroll', 'axis': 'vertical'|'horizontal', 'value': int}
      {'type': 'move',   'dx': int, 'dy': int}
    """

    def __init__(self, device: evdev.InputDevice, debug: bool = False):
        self._dev = device
        self._debug = debug

    def fileno(self) -> int:
        """Allow use with select()."""
        return self._dev.fileno()

    def read_events(self):
        """Generator: yield one normalised event per kernel event."""
        for event in self._dev.read():
            parsed = self._parse(event)
            if parsed:
                if self._debug:
                    print(f"  evdev: {parsed}")
                yield parsed

    def _parse(self, event: evdev.InputEvent) -> dict | None:
        if event.type == ecodes.EV_KEY:
            name = _BTN_MAP.get(event.code)
            if name:
                return {"type": "button", "name": name, "pressed": bool(event.value)}

        elif event.type == ecodes.EV_REL:
            if event.code == ecodes.REL_X:
                return {"type": "move", "dx": event.value, "dy": 0}
            if event.code == ecodes.REL_Y:
                return {"type": "move", "dx": 0, "dy": event.value}
            mapping = _REL_MAP.get(event.code)
            if mapping:
                _, axis = mapping
                return {"type": "scroll", "axis": axis, "value": event.value}

        return None
