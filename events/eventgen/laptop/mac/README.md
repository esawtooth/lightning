# macOS

This folder contains utilities that emit laptop status information as `Event` objects.

`tracker.py` gathers several metrics using built-in macOS tools and outputs each
measurement as a JSON encoded event. It currently collects:

- **laptop.in_use** – idle time in seconds and whether the machine is considered
  active (idle less than five minutes).
- **laptop.battery** – battery percentage and charging status from `pmset`.
- **laptop.location** – latitude and longitude via `CoreLocationCLI` when
  available.
- **laptop.program** – name of the frontmost application using AppleScript.

Run the script directly to print the events:

```bash
python tracker.py
```
