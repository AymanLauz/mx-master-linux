"""
HID++ 2.0 protocol layer for the MX Master 3S.

HID++ 2.0 message format:
  Short (7 bytes):  [0x10, device_idx, feature_idx, (func<<4)|sw_id, p0, p1, p2]
  Long  (20 bytes): [0x11, device_idx, feature_idx, (func<<4)|sw_id, p0..p15]

To call a feature function:
  1. Query feature index via ROOT (feature index 0x00, function 0)
  2. Use the returned index to call functions on that feature

Events from the device arrive the same way, with byte 3 indicating which
function/event triggered the notification.
"""

import os
import time
import struct
import threading

SHORT = 0x10
LONG  = 0x11

# HID++ 2.0 feature codes (not indices — indices are device-specific)
FEAT_ROOT               = 0x0000
FEAT_REPROG_CONTROLS_V4 = 0x1B04
FEAT_THUMBWHEEL         = 0x2150
FEAT_SMART_SHIFT        = 0x2110

# Software ID embedded in byte 3 (identifies us as the requester).
# The kernel's logitech-hidpp-device driver uses SW_ID=0x01; we use 0x08
# (user-space range 0x07-0x0F) so kernel responses don't match our filter.
SW_ID = 0x08

# For Bluetooth direct connection the device index is 0xFF
DEVICE_INDEX = 0xFF


class HIDPPError(Exception):
    pass


class HIDPPDevice:
    """
    Low-level HID++ 2.0 interface over /dev/hidrawN.

    Usage:
        dev = HIDPPDevice("/dev/hidraw1")
        dev.unlock_buttons()
        for event in dev.read_events():
            print(event)
        dev.close()
    """

    def __init__(self, path: str, debug: bool = False):
        self._path = path
        self._debug = debug
        self._fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
        self._feature_cache: dict[int, int] = {}
        self._lock = threading.Lock()

        # Known control IDs — discovered by querying REPROG_CONTROLS_V4.
        # Populated after calling unlock_buttons().
        self.controls: dict[int, dict] = {}

        # Drain any pending kernel-driver HID++ traffic before we start
        # sending our own queries (BT init can take ~1s after hidraw opens).
        self._drain(timeout_ms=1000)

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    # ------------------------------------------------------------------ #
    # Low-level I/O                                                        #
    # ------------------------------------------------------------------ #

    def _drain(self, timeout_ms: int = 1000) -> None:
        """Read and discard all pending reports to clear kernel-driver traffic."""
        import select
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            ready, _, _ = select.select([self._fd], [], [], max(0, deadline - time.monotonic()))
            if not ready:
                break
            try:
                data = os.read(self._fd, 20)
                if self._debug:
                    print(f"  HID++ drain: {data.hex(' ')}")
            except OSError:
                break

    def _write(self, report: list[int]) -> None:
        data = bytes(report)
        if self._debug:
            print(f"  HID++ TX: {data.hex(' ')}")
        os.write(self._fd, data)

    def _read(self, timeout_ms: int = 500) -> bytes | None:
        """Block until a report arrives or timeout expires."""
        import select
        ready, _, _ = select.select([self._fd], [], [], timeout_ms / 1000)
        if ready:
            data = os.read(self._fd, 20)
            if self._debug:
                print(f"  HID++ RX: {data.hex(' ')}")
            return data
        return None

    def _send_recv(self, report: list[int], timeout_ms: int = 3000) -> bytes:
        """Send a report and wait for the matching response."""
        feature_idx = report[2]
        func_sw = report[3]
        self._write(report)

        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            resp = self._read(timeout_ms=200)
            if resp is None:
                continue
            # Match on feature index and function+SW_ID
            if len(resp) >= 4 and resp[2] == feature_idx and resp[3] == func_sw:
                return resp
            # Device may send error reports (feature 0xFF)
            if len(resp) >= 3 and resp[2] == 0xFF:
                raise HIDPPError(f"HID++ error response: {resp.hex(' ')}")
            if self._debug:
                print(f"  HID++ skip (want feat={feature_idx:#x} func={func_sw:#x}): {resp.hex(' ')}")
        raise HIDPPError(f"Timeout waiting for HID++ response to feature={feature_idx:#x} func={func_sw:#x}")

    # ------------------------------------------------------------------ #
    # Feature discovery                                                    #
    # ------------------------------------------------------------------ #

    def get_feature_index(self, feature_code: int) -> int:
        """Return the device-local index for a HID++ 2.0 feature code."""
        if feature_code in self._feature_cache:
            return self._feature_cache[feature_code]

        high = (feature_code >> 8) & 0xFF
        low  = feature_code & 0xFF
        report = [LONG, DEVICE_INDEX, 0x00, (0 << 4) | SW_ID, high, low, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        resp = self._send_recv(report)

        idx = resp[4]
        if self._debug:
            print(f"  feature {feature_code:#06x} → index {idx:#04x}  raw={resp.hex(' ')}")
        if idx == 0 and feature_code != FEAT_ROOT:
            raise HIDPPError(f"Feature {feature_code:#06x} not supported by this device")

        self._feature_cache[feature_code] = idx
        return idx

    def enumerate_features(self) -> dict[int, int]:
        """Return {feature_code: feature_index} for every feature the device exposes."""
        FEAT_FEATURE_SET = 0x0001
        fs_idx = self.get_feature_index(FEAT_FEATURE_SET)
        report = [LONG, DEVICE_INDEX, fs_idx, (0 << 4) | SW_ID, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        resp = self._send_recv(report)
        count = resp[4]
        if self._debug:
            print(f"  device exposes {count} features (FEATURE_SET at index {fs_idx:#x})")
        result = {}
        for i in range(1, count + 1):
            report = [LONG, DEVICE_INDEX, fs_idx, (1 << 4) | SW_ID, i, 0x00, 0x00,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            resp = self._send_recv(report)
            code = (resp[4] << 8) | resp[5]
            result[code] = i
            if self._debug:
                print(f"    [{i:3d}] {code:#06x}")
        return result

    # ------------------------------------------------------------------ #
    # REPROG_CONTROLS_V4 — unlock hidden buttons                          #
    # ------------------------------------------------------------------ #

    def _reprog_get_count(self, feat_idx: int) -> int:
        report = [LONG, DEVICE_INDEX, feat_idx, (0 << 4) | SW_ID, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        resp = self._send_recv(report)
        return resp[4]

    def _reprog_get_control_info(self, feat_idx: int, control_index: int) -> dict:
        report = [LONG, DEVICE_INDEX, feat_idx, (1 << 4) | SW_ID,
                  control_index, 0x00, 0x00, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        resp = self._send_recv(report)
        ctrl_id  = (resp[4] << 8) | resp[5]
        task_id  = (resp[6] << 8) | resp[7]
        flags    = resp[8]
        return {"ctrl_id": ctrl_id, "task_id": task_id, "flags": flags, "index": control_index}

    def _reprog_divert_control(self, feat_idx: int, ctrl_id: int) -> None:
        """Tell the mouse to send this button's events to us via HID++ instead of default action."""
        hi = (ctrl_id >> 8) & 0xFF
        lo = ctrl_id & 0xFF
        # setCidReporting (function 3): cid (2 bytes), flags (1 byte), zeros
        # bit 0 = DIVERTED, bit 1 = DIVERTED_Xvalid (must be set together or device ignores it)
        report = [LONG, DEVICE_INDEX, feat_idx, (3 << 4) | SW_ID,
                  hi, lo, 0x03, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self._send_recv(report)
        # Read back to verify divert is active
        if self._debug:
            verify = [LONG, DEVICE_INDEX, feat_idx, (2 << 4) | SW_ID,
                      hi, lo, 0x00, 0x00, 0x00, 0x00,
                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
            resp = self._send_recv(verify)
            print(f"  getCidReporting ctrl={ctrl_id:#06x}: {resp.hex(' ')}")

    def unlock_buttons(self) -> None:
        """
        Query all controls from REPROG_CONTROLS_V4 and divert the ones we
        want to handle in software (gesture button, mode shift, thumb wheel click).
        """
        feat_idx = self.get_feature_index(FEAT_REPROG_CONTROLS_V4)
        count = self._reprog_get_count(feat_idx)

        if self._debug:
            print(f"REPROG_CONTROLS_V4 at feature index {feat_idx:#x}, {count} controls")

        for i in range(count):
            info = self._reprog_get_control_info(feat_idx, i)
            ctrl_id = info["ctrl_id"]
            if self._debug:
                divertable = "divertable" if (info["flags"] & 0x20) else "NOT divertable"
                print(f"  control[{i}]: ctrl_id={ctrl_id:#06x} task_id={info['task_id']:#06x} flags={info['flags']:#04x} ({divertable})")
            self.controls[ctrl_id] = info

        # Divert controls we want to handle ourselves.
        # These are ctrl_ids (physical button IDs), standard across MX Master devices:
        #   0x00C4 = Mode shift button
        #   0x00D7 = Gesture button (large thumb button)
        DIVERT_CTRL_IDS = {0x00C4, 0x00D7}
        for ctrl_id, info in self.controls.items():
            if ctrl_id in DIVERT_CTRL_IDS:
                if self._debug:
                    print(f"  Diverting ctrl_id={ctrl_id:#06x} (task={info['task_id']:#06x})")
                self._reprog_divert_control(feat_idx, ctrl_id)

    # ------------------------------------------------------------------ #
    # THUMBWHEEL — enable side wheel reporting                            #
    # ------------------------------------------------------------------ #

    def enable_thumbwheel(self) -> None:
        """Enable the side thumb wheel (it's off by default on Linux)."""
        try:
            feat_idx = self.get_feature_index(FEAT_THUMBWHEEL)
        except HIDPPError:
            if self._debug:
                print("THUMBWHEEL feature not found — skipping")
            return

        # setReporting (function 2): byte 4 = 0x01 (reporting enabled)
        report = [LONG, DEVICE_INDEX, feat_idx, (2 << 4) | SW_ID,
                  0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
                  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        self._send_recv(report)
        if self._debug:
            print(f"Thumbwheel enabled at feature index {feat_idx:#x}")

    # ------------------------------------------------------------------ #
    # Event reading                                                        #
    # ------------------------------------------------------------------ #

    def read_event(self, timeout_ms: int = 100) -> dict | None:
        """
        Read one HID++ event from the device.

        Returns a dict with 'type' and relevant fields, or None on timeout.

        Event types returned:
          {'type': 'button', 'ctrl_id': int, 'pressed': bool}
          {'type': 'thumbwheel', 'delta': int}   # negative=left, positive=right
          {'type': 'raw', 'data': bytes}          # unrecognised events
        """
        data = self._read(timeout_ms)
        if data is None:
            return None

        if len(data) < 4:
            return None

        feat_idx = data[2]
        func_sw  = data[3]
        func     = (func_sw >> 4) & 0x0F

        # REPROG_CONTROLS_V4 diverted button notification (function 0 = event)
        reprog_idx = self._feature_cache.get(FEAT_REPROG_CONTROLS_V4)
        if reprog_idx is not None and feat_idx == reprog_idx and func == 0:
            # Bytes 4-5: ctrl_id of pressed button (0 = released)
            ctrl_id = (data[4] << 8) | data[5]
            pressed = ctrl_id != 0
            return {"type": "button", "ctrl_id": ctrl_id, "pressed": pressed}

        # THUMBWHEEL event (function 0 = event notification)
        tw_idx = self._feature_cache.get(FEAT_THUMBWHEEL)
        if tw_idx is not None and feat_idx == tw_idx and func == 0:
            # Bytes 4-5: signed 16-bit rotation delta
            delta = struct.unpack(">h", bytes([data[4], data[5]]))[0]
            return {"type": "thumbwheel", "delta": delta}

        return {"type": "raw", "data": data}
