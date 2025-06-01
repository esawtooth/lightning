# Event Generators

This directory contains helper programs that can collect status information from a user's devices and publish them as events.

Each subfolder focuses on a specific type of device. These scripts are not implemented yet; placeholders describe the intended functionality.

- `laptop/` – utilities for macOS, Windows and Linux laptops.
- `mobile/` – utilities for iOS and Android devices.

Generated events should conform to the `Event` structure defined in `events/` and can be forwarded to the Event API.
