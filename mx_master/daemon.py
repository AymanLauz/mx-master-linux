"""
Main daemon: ties together HID++ unlock, evdev reading, and action dispatch.

Event flow:
  1. HIDPPDevice unlocks hidden buttons (gesture, mode shift, thumb wheel)
  2. Both HIDPPDevice and EvdevListener are polled with select()
  3. Events are translated to button names and dispatched via ActionRunner
  4. Special modes (auto-scroll, gesture-move) are tracked as state here
"""

import select
import logging

from .hidpp import HIDPPDevice, HIDPPError
from .evdev_listener import EvdevListener
from .actions import ActionRunner
from .auto_scroll import AutoScroller
from . import device as device_finder

log = logging.getLogger(__name__)


# Maps HID++ task_id → our internal button names.
# These are standard Logitech task IDs across devices.
_TASK_ID_NAMES = {
    0x00C4: "mode_shift",
    0x00D7: "gesture_click",
    0x00DC: "thumb_wheel_click",
}


class Daemon:
    def __init__(self, config: dict, debug: bool = False):
        self._cfg = config
        self._debug = debug

        self._hidpp: HIDPPDevice | None = None
        self._evdev: EvdevListener | None = None
        self._runner: ActionRunner | None = None
        self._scroller = AutoScroller(debug=debug)

        # Gesture button state: True while the button is held
        self._gesture_held = False

    def start(self) -> None:
        log.info("Starting MX Master daemon...")

        # Locate devices
        hidraw_path = device_finder.find_hidraw()
        evdev_dev   = device_finder.find_evdev()
        log.info(f"Found hidraw: {hidraw_path}")
        log.info(f"Found evdev:  {evdev_dev.path} ({evdev_dev.name})")

        # Set up HID++ and unlock buttons
        self._hidpp = HIDPPDevice(hidraw_path, debug=self._debug)
        try:
            self._hidpp.unlock_buttons()
            self._hidpp.enable_thumbwheel()
            log.info("HID++ button unlock complete")
        except HIDPPError as e:
            log.warning(f"HID++ setup failed: {e} — some buttons may not work")

        # Set up evdev listener and action runner
        self._evdev   = EvdevListener(evdev_dev, debug=self._debug)
        self._runner  = ActionRunner(self._cfg, debug=self._debug)

        log.info("Daemon running. Press Ctrl+C to stop.")
        self._loop()

    def _loop(self) -> None:
        hidraw_fd = self._hidpp._fd
        evdev_fd  = self._evdev.fileno()

        while True:
            readable, _, _ = select.select([hidraw_fd, evdev_fd], [], [], 1.0)

            for fd in readable:
                if fd == hidraw_fd:
                    event = self._hidpp.read_event(timeout_ms=0)
                    if event:
                        self._handle_hidpp(event)

                elif fd == evdev_fd:
                    for event in self._evdev.read_events():
                        self._handle_evdev(event)

    # ------------------------------------------------------------------ #
    # Event handlers                                                       #
    # ------------------------------------------------------------------ #

    def _handle_hidpp(self, event: dict) -> None:
        if event["type"] == "button":
            ctrl_id = event["ctrl_id"]
            pressed = event["pressed"]

            # Resolve ctrl_id → task_id → button name
            ctrl_info = self._hidpp.controls.get(ctrl_id, {})
            task_id   = ctrl_info.get("task_id", 0)
            name      = _TASK_ID_NAMES.get(task_id)

            if self._debug:
                print(f"HID++ button: ctrl={ctrl_id:#06x} task={task_id:#06x} name={name} pressed={pressed}")

            if name == "gesture_click":
                self._gesture_held = pressed
                if not pressed:
                    # Button released without significant movement → Super key
                    self._runner.run("gesture_click")

            elif name and pressed:
                self._runner.run(name)

        elif event["type"] == "thumbwheel":
            delta = event["delta"]
            if delta > 0:
                self._runner.run("thumb_wheel_up")
            elif delta < 0:
                self._runner.run("thumb_wheel_down")

    def _handle_evdev(self, event: dict) -> None:
        if event["type"] == "button":
            name    = event["name"]
            pressed = event["pressed"]

            if name == "middle_click" and pressed:
                if self._scroller.active:
                    self._scroller.stop()
                else:
                    self._scroller.start()
                return

            if pressed:
                self._runner.run(name)

        elif event["type"] == "move":
            dx, dy = event["dx"], event["dy"]

            if self._scroller.active:
                self._scroller.update(dx, dy)

            if self._gesture_held:
                # Threshold before we commit to a swipe direction
                if abs(dx) > 30:
                    self._runner.workspace_swipe("right" if dx > 0 else "left")
                    # Reset gesture state so we don't fire repeatedly
                    self._gesture_held = False

        elif event["type"] == "scroll":
            # Standard scroll wheel — pass through (kernel handles it natively)
            pass
