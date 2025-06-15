# Linux

Utilities here gather laptop information on Linux distributions. Metrics are
formatted as `Event` objects so they can be queued to the backend.

`system_status.py` collects several basic statistics using standard system
interfaces:

- **laptop.battery** – percentage and charging status from
  `/sys/class/power_supply` when available.
- **laptop.cpu** – load average from `os.getloadavg()`.
- **laptop.memory** – total and available memory parsed from `/proc/meminfo`.
- **laptop.network** – hostname and IP address.

Run the script directly to print each event as a JSON object:

```bash
python system_status.py
```
