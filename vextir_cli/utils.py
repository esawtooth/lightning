"""
Vextir CLI Utility Functions
"""

import asyncio
import functools
import json
from datetime import datetime
from typing import Any, Dict, Optional

from rich.syntax import Syntax


def handle_async(func):
    """Decorator to handle async functions in Click commands"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return asyncio.run(func(*args, **kwargs))
    return wrapper


def format_timestamp(timestamp: Optional[str]) -> str:
    """Format timestamp for display"""
    if not timestamp:
        return "Never"
    
    try:
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        else:
            dt = timestamp
        
        # Format as relative time if recent, otherwise absolute
        now = datetime.utcnow().replace(tzinfo=dt.tzinfo)
        diff = now - dt
        
        if diff.total_seconds() < 60:
            return "Just now"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}m ago"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        else:
            return dt.strftime("%Y-%m-%d %H:%M")
    
    except (ValueError, AttributeError):
        return str(timestamp)


def format_json(data: Any, compact: bool = False) -> Syntax:
    """Format JSON data with syntax highlighting"""
    if compact:
        json_str = json.dumps(data, separators=(',', ':'))
        if len(json_str) > 100:
            json_str = json_str[:97] + "..."
    else:
        json_str = json.dumps(data, indent=2, default=str)
    
    return Syntax(json_str, "json", theme="monokai", line_numbers=not compact)


def format_size(bytes_size: int) -> str:
    """Format byte size for human reading"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable format"""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


def truncate_string(text: str, max_length: int = 50) -> str:
    """Truncate string with ellipsis if too long"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def validate_json(json_str: str) -> bool:
    """Validate if string is valid JSON"""
    try:
        json.loads(json_str)
        return True
    except json.JSONDecodeError:
        return False


def parse_key_value_pairs(pairs: list) -> Dict[str, str]:
    """Parse key=value pairs from command line arguments"""
    result = {}
    for pair in pairs:
        if '=' in pair:
            key, value = pair.split('=', 1)
            result[key] = value
        else:
            result[pair] = ""
    return result


def format_table_data(data: list, headers: list) -> list:
    """Format data for table display"""
    formatted_rows = []
    for item in data:
        row = []
        for header in headers:
            value = item.get(header.lower().replace(' ', '_'), '')
            if isinstance(value, (list, dict)):
                value = json.dumps(value, separators=(',', ':'))
            row.append(str(value))
        formatted_rows.append(row)
    return formatted_rows


def get_status_color(status: str) -> str:
    """Get color for status display"""
    status_colors = {
        'running': 'green',
        'active': 'green',
        'healthy': 'green',
        'success': 'green',
        'stopped': 'red',
        'error': 'red',
        'failed': 'red',
        'unhealthy': 'red',
        'starting': 'yellow',
        'pending': 'yellow',
        'warning': 'yellow',
        'unknown': 'dim'
    }
    return status_colors.get(status.lower(), 'white')


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format percentage value"""
    return f"{value:.{decimals}f}%"


def format_cost(cost: float, currency: str = "USD") -> str:
    """Format cost value"""
    if cost < 0.01:
        return f"<$0.01 {currency}"
    elif cost < 1:
        return f"${cost:.3f} {currency}"
    else:
        return f"${cost:.2f} {currency}"


class ProgressTracker:
    """Simple progress tracking utility"""
    
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.start_time = datetime.utcnow()
    
    def update(self, increment: int = 1):
        """Update progress"""
        self.current += increment
    
    def get_percentage(self) -> float:
        """Get completion percentage"""
        if self.total == 0:
            return 100.0
        return (self.current / self.total) * 100
    
    def get_eta(self) -> Optional[str]:
        """Get estimated time to completion"""
        if self.current == 0:
            return None
        
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        rate = self.current / elapsed
        remaining = self.total - self.current
        
        if rate > 0:
            eta_seconds = remaining / rate
            return format_duration(eta_seconds)
        
        return None
    
    def is_complete(self) -> bool:
        """Check if progress is complete"""
        return self.current >= self.total


def safe_get(data: dict, path: str, default: Any = None) -> Any:
    """Safely get nested dictionary value using dot notation"""
    keys = path.split('.')
    current = data
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    
    return current


def merge_dicts(dict1: dict, dict2: dict) -> dict:
    """Recursively merge two dictionaries"""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    
    return result
