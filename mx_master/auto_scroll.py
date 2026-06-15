"""
Auto-scroll mode: click the scroll wheel, move the mouse to scroll.

Works by injecting synthetic scroll events via Linux's uinput interface.
The further the mouse moves from the click point, the faster it scrolls.
A second click exits the mode.
"""

import threading
import time
import evdev
from evdev import UInput, ecodes


# Pixels of mouse travel per unit of scroll speed
_DEAD_ZONE = 10     # px — no scroll within this radius of the origin
_SPEED_DIV = 30     # higher = slower acceleration


class AutoScroller:
    def __init__(self, debug: bool = False):
        self._debug = debug
        self._active = False
        self._origin_x = 0
        self._origin_y = 0
        self._cur_x = 0
        self._cur_y = 0
        self._thread: threading.Thread | None = None
        self._ui: UInput | None = None

    def start(self, origin_x: int = 0, origin_y: int = 0) -> None:
        """Enter auto-scroll mode. Call update() as the mouse moves."""
        if self._active:
            return
        self._origin_x = origin_x
        self._origin_y = origin_y
        self._cur_x = origin_x
        self._cur_y = origin_y
        self._active = True

        self._ui = UInput({ecodes.EV_REL: [ecodes.REL_WHEEL, ecodes.REL_HWHEEL]},
                          name="mx-master-autoscroll")

        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        if self._debug:
            print("  auto-scroll: started")

    def update(self, dx: int, dy: int) -> None:
        """Call this with relative mouse movement deltas while in auto-scroll mode."""
        self._cur_x += dx
        self._cur_y += dy

    def stop(self) -> None:
        """Exit auto-scroll mode."""
        self._active = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        if self._ui:
            self._ui.close()
            self._ui = None
        if self._debug:
            print("  auto-scroll: stopped")

    @property
    def active(self) -> bool:
        return self._active

    def _loop(self) -> None:
        """Background thread: emit scroll events proportional to mouse displacement."""
        while self._active:
            off_x = self._cur_x - self._origin_x
            off_y = self._cur_y - self._origin_y

            vert_scroll = 0
            horiz_scroll = 0

            if abs(off_y) > _DEAD_ZONE:
                vert_scroll = -int((off_y - _DEAD_ZONE * (1 if off_y > 0 else -1)) / _SPEED_DIV)

            if abs(off_x) > _DEAD_ZONE:
                horiz_scroll = int((off_x - _DEAD_ZONE * (1 if off_x > 0 else -1)) / _SPEED_DIV)

            if self._ui and (vert_scroll or horiz_scroll):
                if vert_scroll:
                    self._ui.write(ecodes.EV_REL, ecodes.REL_WHEEL, vert_scroll)
                if horiz_scroll:
                    self._ui.write(ecodes.EV_REL, ecodes.REL_HWHEEL, horiz_scroll)
                self._ui.syn()

            time.sleep(0.05)  # 20 Hz scroll rate
