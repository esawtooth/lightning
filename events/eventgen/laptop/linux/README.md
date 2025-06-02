# Linux

This directory will hold tools for collecting laptop information on Linux distributions, e.g.:

- Battery level from `/sys/class/power_supply`.
- Current network status via `nmcli` or `ip`.
- CPU load and memory consumption from `/proc`.

Collected metrics should be packaged as `Event` objects for dispatching.
