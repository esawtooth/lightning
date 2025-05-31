from fnmatch import fnmatchcase


def event_matches(event_type: str, pattern: str) -> bool:
    """Return True if the event_type matches the glob-style pattern."""
    return fnmatchcase(event_type, pattern)
