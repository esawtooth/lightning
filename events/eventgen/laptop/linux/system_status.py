import os
import json
import socket
import getpass
from datetime import datetime
from typing import List, Optional, Tuple

from events import Event


def _read_first(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def get_battery_status() -> Tuple[Optional[int], Optional[bool]]:
    """Return (percentage, charging) from /sys/class/power_supply if available."""
    base = "/sys/class/power_supply"
    if not os.path.isdir(base):
        return None, None
    for name in os.listdir(base):
        if name.startswith("BAT"):
            percent = _read_first(os.path.join(base, name, "capacity"))
            status = _read_first(os.path.join(base, name, "status"))
            try:
                percent_val = int(percent) if percent is not None else None
            except Exception:
                percent_val = None
            charging = status.lower() == "charging" if status else None
            return percent_val, charging
    return None, None


def get_cpu_load() -> Optional[Tuple[float, float, float]]:
    try:
        return os.getloadavg()
    except Exception:
        return None


def get_memory_usage() -> Tuple[Optional[int], Optional[int]]:
    """Return (total_kb, available_kb) from /proc/meminfo."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, rest = line.split(":", 1)
                value = rest.strip().split()[0]
                info[key] = int(value)
        return info.get("MemTotal"), info.get("MemAvailable")
    except Exception:
        return None, None


def get_network_info() -> Tuple[str, Optional[str]]:
    hostname = socket.gethostname()
    try:
        ip = socket.gethostbyname(hostname)
    except Exception:
        ip = None
    return hostname, ip


def collect_events(user_id: Optional[str] = None) -> List[Event]:
    user_id = user_id or getpass.getuser()
    events: List[Event] = []
    now = datetime.utcnow()

    load_avg = get_cpu_load()
    if load_avg is not None:
        events.append(
            Event(
                timestamp=now,
                source="linux.laptop",
                type="laptop.cpu",
                user_id=user_id,
                metadata={"load_avg": list(load_avg)},
            )
        )

    total_kb, avail_kb = get_memory_usage()
    if total_kb is not None:
        events.append(
            Event(
                timestamp=now,
                source="linux.laptop",
                type="laptop.memory",
                user_id=user_id,
                metadata={"total_kb": total_kb, "available_kb": avail_kb},
            )
        )

    percent, charging = get_battery_status()
    if percent is not None:
        events.append(
            Event(
                timestamp=now,
                source="linux.laptop",
                type="laptop.battery",
                user_id=user_id,
                metadata={"percentage": percent, "charging": charging},
            )
        )

    hostname, ip = get_network_info()
    events.append(
        Event(
            timestamp=now,
            source="linux.laptop",
            type="laptop.network",
            user_id=user_id,
            metadata={"hostname": hostname, "ip": ip},
        )
    )

    return events


if __name__ == "__main__":
    for event in collect_events():
        print(json.dumps(event.to_dict()))
