import json
import subprocess
import getpass
from datetime import datetime
from typing import List, Optional, Tuple

from events import Event


IDLE_THRESHOLD = 300  # seconds


def _get_output(cmd: List[str]) -> str:
    """Run command and return decoded stdout."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return ""


def get_idle_time() -> Optional[float]:
    """Return idle time in seconds or None if unavailable."""
    out = _get_output(["ioreg", "-n", "IOHIDSystem"])
    for line in out.splitlines():
        if "HIDIdleTime" in line:
            try:
                idle_ns = int(line.split("=")[-1].strip())
                return idle_ns / 1e9
            except Exception:
                return None
    return None


def get_battery_status() -> Tuple[Optional[int], Optional[bool]]:
    """Return (percentage, charging) if available."""
    out = _get_output(["pmset", "-g", "batt"])
    for line in out.splitlines():
        if "%" in line:
            try:
                token = [t for t in line.split() if "%" in t][0]
                percent = int(token.strip("%;"))
                charging = "charging" in line.lower()
                return percent, charging
            except Exception:
                return None, None
    return None, None


def get_location() -> Tuple[Optional[float], Optional[float]]:
    """Return (lat, lon) via CoreLocationCLI if available."""
    out = _get_output(["CoreLocationCLI", "-f", "json"])
    if not out:
        return None, None
    try:
        data = json.loads(out)
        return float(data.get("latitude")), float(data.get("longitude"))
    except Exception:
        return None, None


def get_active_program() -> Optional[str]:
    """Return name of the frontmost application."""
    out = _get_output([
        "osascript",
        "-e",
        'tell application "System Events" to get name of first process whose frontmost is true',
    ])
    return out or None


def collect_events(user_id: Optional[str] = None) -> List[Event]:
    """Collect laptop events for the current macOS system."""
    user_id = user_id or getpass.getuser()
    events: List[Event] = []
    idle = get_idle_time()
    if idle is not None:
        events.append(
            Event(
                timestamp=datetime.utcnow(),
                source="mac.laptop",
                type="laptop.in_use",
                user_id=user_id,
                metadata={"idle_seconds": idle, "in_use": idle < IDLE_THRESHOLD},
            )
        )

    percent, charging = get_battery_status()
    if percent is not None:
        events.append(
            Event(
                timestamp=datetime.utcnow(),
                source="mac.laptop",
                type="laptop.battery",
                user_id=user_id,
                metadata={"percentage": percent, "charging": charging},
            )
        )

    lat, lon = get_location()
    if lat is not None and lon is not None:
        events.append(
            Event(
                timestamp=datetime.utcnow(),
                source="mac.laptop",
                type="laptop.location",
                user_id=user_id,
                metadata={"latitude": lat, "longitude": lon},
            )
        )

    program = get_active_program()
    if program:
        events.append(
            Event(
                timestamp=datetime.utcnow(),
                source="mac.laptop",
                type="laptop.program",
                user_id=user_id,
                metadata={"application": program},
            )
        )

    return events


if __name__ == "__main__":
    for event in collect_events():
        print(json.dumps(event.to_dict()))
