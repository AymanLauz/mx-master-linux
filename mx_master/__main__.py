"""Entry point: python -m mx_master  or  mx-master (after install)."""

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="mx-master",
        description="MX Master 3S button daemon for Linux",
    )
    parser.add_argument(
        "--config", "-c",
        type=Path,
        default=None,
        metavar="PATH",
        help="Path to config YAML (default: ~/.config/mx-master/config.yaml)",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Print raw HID++ and evdev events",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List detected HID and input devices then exit",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    if args.list_devices:
        from .device import list_all
        list_all()
        return

    from . import config as cfg_module
    from .daemon import Daemon

    config = cfg_module.load(args.config)
    daemon = Daemon(config, debug=args.debug)

    try:
        daemon.start()
    except KeyboardInterrupt:
        print("\nStopped.")
    except PermissionError:
        print(
            "ERROR: Permission denied accessing mouse device.\n"
            "Make sure you are in the 'input' and 'plugdev' groups:\n"
            "  sudo usermod -aG input,plugdev $USER\n"
            "Then log out and back in.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
