#!/usr/bin/env python3
"""Modern Context Hub CLI - Git-like interface for CRDT collaboration."""

from __future__ import annotations

import json
import os
import sys
import time
import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import click
import requests
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich.text import Text
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich import print as rprint
import jwt
import base64
import urllib.parse
import webbrowser
import threading
import socket
from http.server import HTTPServer, BaseHTTPRequestHandler
import uuid
import difflib
import tempfile


# Global console for rich output
console = Console()

# Configuration
CONFIG_FILE = Path.home() / ".context-hub" / "config.json"
SYNC_STATE_FILE = ".ch-sync-state.json"  # Track sync state in each pulled directory
DEFAULT_CONFIG = {
    "url": "http://localhost:3000",
    "user": None,
    "agent": None,
    "current_workspace": None,
    "verbose": False,
    "json_output": False,
    "azure_tenant_id": None,
    "azure_client_id": None,
    "azure_scope": "api://context-hub/.default",
    "token_cache_file": str(Path.home() / ".context-hub" / "tokens.json")
}

# Global flags for output control
VERBOSE_MODE = False
JSON_OUTPUT = False


def set_output_mode(verbose: bool = False, json_output: bool = False):
    """Set global output mode for agent-friendly reporting."""
    global VERBOSE_MODE, JSON_OUTPUT
    VERBOSE_MODE = verbose
    JSON_OUTPUT = json_output


def agent_log(message: str, level: str = "info", data: Dict[str, Any] = None):
    """Agent-friendly logging with structured output."""
    if JSON_OUTPUT:
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "data": data or {}
        }
        print(json.dumps(log_entry))
    elif VERBOSE_MODE:
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = {"info": "blue", "success": "green", "warning": "yellow", "error": "red"}.get(level, "white")
        console.print(f"[dim]{timestamp}[/dim] [{color}]{level.upper()}[/{color}] {message}")
        if data:
            console.print(f"[dim]  Data: {data}[/dim]")


def llm_response(success: bool, operation: str, data: Dict[str, Any] = None, error: str = None):
    """Structured LLM-friendly response format."""
    response = {
        "success": success,
        "operation": operation,
        "timestamp": datetime.now().isoformat(),
        "data": data or {},
        "error": error
    }
    
    if JSON_OUTPUT:
        print(json.dumps(response, indent=2))
        return response
    
    return response


def operation_summary(operation: str, stats: Dict[str, Any]):
    """Provide detailed operation summary for agents."""
    if JSON_OUTPUT:
        summary = {
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "stats": stats,
            "success": stats.get("errors", 0) == 0
        }
        print(json.dumps(summary))
    else:
        console.print(f"\n[bold]Operation Summary: {operation}[/bold]")
        for key, value in stats.items():
            if key == "duration":
                console.print(f"  {key}: {value:.2f}s")
            else:
                console.print(f"  {key}: {value}")


def enhanced_progress_bar(description: str, total: Optional[int] = None):
    """Create an enhanced progress bar with agent-friendly output."""
    if JSON_OUTPUT:
        return None  # Don't show progress bars in JSON mode
    
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn() if total else "",
        TaskProgressColumn() if total else "",
        TimeRemainingColumn() if total else "",
        console=console,
        transient=not VERBOSE_MODE  # Keep progress visible in verbose mode
    )


def load_config() -> Dict[str, Any]:
    """Load configuration from file or create default."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    CONFIG_FILE.parent.mkdir(exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def get_current_user() -> str:
    """Get current user from config or environment."""
    config = load_config()
    user = config.get("user") or os.environ.get("CONTEXT_HUB_USER")
    if not user:
        console.print("[red]Error: No user configured. Run 'ch config user <username>' first.[/red]")
        sys.exit(1)
    return user


def api_request(method: str, path: str, **kwargs) -> Any:
    """Make API request with Azure AD authentication."""
    config = load_config()
    url = f"{config['url']}{path}"
    
    headers = kwargs.pop("headers", {})
    
    # Add Azure AD authentication if configured
    if config.get("azure_tenant_id") and config.get("azure_client_id"):
        try:
            access_token = get_azure_token()
            headers["Authorization"] = f"Bearer {access_token}"
            agent_log("Using Azure AD authentication", "info")
        except Exception as e:
            agent_log("Azure AD authentication failed", "error", {"error": str(e)})
            console.print(f"[red]Authentication failed: {e}[/red]")
            sys.exit(1)
    else:
        # Fallback to legacy headers for local development
        headers["X-User-Id"] = get_current_user()
        if config.get("agent"):
            headers["X-Agent-Id"] = config["agent"]
        agent_log("Using legacy authentication headers", "info")
    
    try:
        resp = requests.request(method, url, headers=headers, **kwargs)
        if not resp.ok:
            # Handle authentication errors specifically
            if resp.status_code == 401:
                if config.get("azure_tenant_id"):
                    # Clear token cache and retry once
                    agent_log("Token expired, clearing cache", "warning")
                    cache_file = config.get("token_cache_file", str(Path.home() / ".context-hub" / "tokens.json"))
                    cache = TokenCache(cache_file)
                    cache_key = f"{config['azure_tenant_id']}:{config['azure_client_id']}:{config.get('azure_scope', 'api://context-hub/.default')}"
                    cached_tokens = cache.load_tokens()
                    if cache_key in cached_tokens:
                        del cached_tokens[cache_key]
                        cache.save_tokens(cached_tokens)
                    console.print("[yellow]Token expired. Please re-authenticate.[/yellow]")
                    # Recursively retry with fresh token
                    return api_request(method, path, headers=kwargs.pop("headers", {}), **kwargs)
                else:
                    console.print("[red]Authentication failed. Check your configuration.[/red]")
            
            error_msg = resp.text.strip() if resp.text.strip() else f"HTTP {resp.status_code} error"
            console.print(f"[red]Error {resp.status_code}: {error_msg}[/red]")
            sys.exit(1)
        
        if resp.text:
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return None
    except requests.exceptions.ConnectionError:
        console.print("[red]Error: Cannot connect to Context Hub. Is the server running?[/red]")
        sys.exit(1)


def file_hash(file_path: Path) -> str:
    """Calculate hash of file contents."""
    if not file_path.exists() or file_path.is_dir():
        return ""
    try:
        content = file_path.read_bytes()
        return hashlib.sha256(content).hexdigest()
    except:
        return ""


def save_sync_state(local_dir: Path, sync_state: Dict[str, Any]) -> None:
    """Save sync state to track changes."""
    state_file = local_dir / SYNC_STATE_FILE
    state_file.write_text(json.dumps(sync_state, indent=2))


def load_sync_state(local_dir: Path) -> Dict[str, Any]:
    """Load sync state to detect changes."""
    state_file = local_dir / SYNC_STATE_FILE
    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except:
            pass
    return {}


def scan_local_tree(local_dir: Path) -> Dict[str, Any]:
    """Scan local directory tree and create state snapshot."""
    tree_state = {}
    
    for item in local_dir.rglob("*"):
        if item.name == SYNC_STATE_FILE:
            continue
            
        rel_path = str(item.relative_to(local_dir))
        
        if item.is_file():
            tree_state[rel_path] = {
                "type": "file",
                "hash": file_hash(item),
                "size": item.stat().st_size
            }
        elif item.is_dir():
            tree_state[rel_path] = {
                "type": "folder"
            }
    
    return tree_state


def resolve_path(path: str) -> str:
    """Resolve a path to document UUID. Supports both absolute and relative paths."""
    import uuid
    
    # Already a UUID
    try:
        uuid.UUID(path)
        return path
    except ValueError:
        pass
    
    # Handle different path formats
    if path.startswith("/") or not path:
        # Absolute path from root
        current_path = path or "/"
    else:
        # Relative path from current workspace
        config = load_config()
        workspace = config.get("current_workspace") or "/"
        current_path = f"{workspace.rstrip('/')}/{path}" if workspace != "/" else f"/{path}"
    
    # Navigate to target
    parts = [p for p in current_path.strip("/").split("/") if p]
    root_resp = api_request("GET", "/root")
    current_id = root_resp["id"]
    
    for part in parts:
        items = api_request("GET", f"/folders/{current_id}")
        match = next((item for item in items if item["name"] == part), None)
        if not match:
            console.print(f"[red]Path not found: {current_path}[/red]")
            sys.exit(1)
        current_id = match["id"]
    
    return current_id


def format_size(content: str) -> str:
    """Format content size in human-readable format."""
    size = len(content.encode('utf-8'))
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def format_time_ago(timestamp: str) -> str:
    """Format timestamp as 'X minutes ago' style."""
    try:
        # This would need actual timestamp from the API
        return "just now"  # Simplified for now
    except:
        return "unknown"


# ============================================================================
# AZURE AD AUTHENTICATION
# ============================================================================

class TokenCache:
    """Handles caching and refreshing of Azure AD tokens."""
    
    def __init__(self, cache_file: str):
        self.cache_file = Path(cache_file)
        self.cache_file.parent.mkdir(exist_ok=True)
    
    def load_tokens(self) -> Dict[str, Any]:
        """Load cached tokens from file."""
        if self.cache_file.exists():
            try:
                return json.loads(self.cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}
    
    def save_tokens(self, tokens: Dict[str, Any]) -> None:
        """Save tokens to cache file."""
        self.cache_file.write_text(json.dumps(tokens, indent=2))
    
    def is_token_valid(self, token: str) -> bool:
        """Check if JWT token is still valid (not expired)."""
        try:
            # Decode without verification to check expiration
            decoded = jwt.decode(token, options={"verify_signature": False})
            exp = decoded.get("exp", 0)
            # Add 5 minute buffer for clock skew
            return exp > (time.time() + 300)
        except:
            return False


def get_azure_token() -> str:
    """Get Azure AD token using device code flow."""
    config = load_config()
    
    tenant_id = config.get("azure_tenant_id")
    client_id = config.get("azure_client_id")
    scope = config.get("azure_scope", "api://context-hub/.default")
    
    if not tenant_id or not client_id:
        console.print("[red]Azure AD not configured. Run 'ch config azure' first.[/red]")
        sys.exit(1)
    
    # Check cache first
    cache_file = config.get("token_cache_file", str(Path.home() / ".context-hub" / "tokens.json"))
    cache = TokenCache(cache_file)
    cached_tokens = cache.load_tokens()
    cache_key = f"{tenant_id}:{client_id}:{scope}"
    
    if cache_key in cached_tokens:
        access_token = cached_tokens[cache_key].get("access_token")
        if access_token and cache.is_token_valid(access_token):
            agent_log("Using cached access token", "info")
            return access_token
        
        # Try refresh token
        refresh_token = cached_tokens[cache_key].get("refresh_token")
        if refresh_token:
            agent_log("Attempting token refresh", "info")
            new_tokens = refresh_azure_token(tenant_id, client_id, refresh_token)
            if new_tokens:
                cached_tokens[cache_key] = new_tokens
                cache.save_tokens(cached_tokens)
                return new_tokens["access_token"]
    
    # Need fresh authentication
    agent_log("Starting device code flow", "info")
    return acquire_azure_token_device_flow(tenant_id, client_id, scope, cache, cache_key)


def acquire_azure_token_device_flow(tenant_id: str, client_id: str, scope: str, cache: TokenCache, cache_key: str) -> str:
    """Acquire Azure AD token using device code flow."""
    
    # Step 1: Get device code
    device_code_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/devicecode"
    device_data = {
        "client_id": client_id,
        "scope": scope
    }
    
    agent_log("Requesting device code", "info", {"tenant_id": tenant_id, "scope": scope})
    
    try:
        device_resp = requests.post(device_code_url, data=device_data)
        device_resp.raise_for_status()
        device_info = device_resp.json()
    except requests.RequestException as e:
        agent_log("Device code request failed", "error", {"error": str(e)})
        console.print(f"[red]Failed to get device code: {e}[/red]")
        sys.exit(1)
    
    # Step 2: Show user instructions
    console.print(f"\n[bold]Azure AD Authentication Required[/bold]")
    console.print(f"Please visit: [blue]{device_info['verification_uri']}[/blue]")
    console.print(f"And enter code: [yellow]{device_info['user_code']}[/yellow]")
    console.print("[dim]Opening browser automatically...[/dim]")
    
    # Auto-open browser
    try:
        webbrowser.open(device_info['verification_uri'])
    except:
        pass  # Browser opening is optional
    
    # Step 3: Poll for token
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    poll_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device_info["device_code"]
    }
    
    interval = device_info.get("interval", 5)
    expires_in = device_info.get("expires_in", 900)
    max_attempts = expires_in // interval
    
    console.print(f"[dim]Waiting for authentication... (timeout in {expires_in}s)[/dim]")
    
    with enhanced_progress_bar("Waiting for authentication...") as progress:
        if progress:
            task = progress.add_task("Waiting for user...", total=max_attempts)
        
        for attempt in range(max_attempts):
            if progress:
                progress.update(task, advance=1)
            
            try:
                token_resp = requests.post(token_url, data=poll_data)
                token_data = token_resp.json()
                
                if token_resp.status_code == 200:
                    # Success!
                    agent_log("Authentication successful", "success")
                    
                    # Cache tokens
                    cached_tokens = cache.load_tokens()
                    cached_tokens[cache_key] = {
                        "access_token": token_data["access_token"],
                        "refresh_token": token_data.get("refresh_token"),
                        "expires_at": time.time() + token_data.get("expires_in", 3600)
                    }
                    cache.save_tokens(cached_tokens)
                    
                    console.print("[green]✓ Authentication successful![/green]")
                    return token_data["access_token"]
                
                elif token_data.get("error") == "authorization_pending":
                    # Still waiting
                    time.sleep(interval)
                    continue
                
                elif token_data.get("error") == "slow_down":
                    # Rate limited
                    time.sleep(interval + 5)
                    continue
                
                else:
                    # Other error
                    error = token_data.get("error", "unknown_error")
                    agent_log("Authentication failed", "error", {"error": error})
                    console.print(f"[red]Authentication failed: {error}[/red]")
                    sys.exit(1)
                    
            except requests.RequestException as e:
                agent_log("Token polling failed", "error", {"error": str(e)})
                time.sleep(interval)
                continue
    
    console.print("[red]Authentication timed out[/red]")
    sys.exit(1)


def refresh_azure_token(tenant_id: str, client_id: str, refresh_token: str) -> Optional[Dict[str, Any]]:
    """Refresh Azure AD token using refresh token."""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    refresh_data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token
    }
    
    try:
        resp = requests.post(token_url, data=refresh_data)
        if resp.status_code == 200:
            token_data = resp.json()
            agent_log("Token refresh successful", "success")
            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "expires_at": time.time() + token_data.get("expires_in", 3600)
            }
    except requests.RequestException:
        pass
    
    agent_log("Token refresh failed", "warning")
    return None


def download_folder_recursive(folder_id: str, local_path: Path, progress=None, task_id=None) -> Dict[str, str]:
    """Download folder structure recursively. Returns mapping of local paths to hub IDs."""
    local_path.mkdir(parents=True, exist_ok=True)
    path_to_id = {}
    
    agent_log(f"Downloading folder {folder_id} to {local_path}", "info", {
        "folder_id": folder_id,
        "local_path": str(local_path)
    })
    
    # Get folder contents
    items = api_request("GET", f"/folders/{folder_id}")
    agent_log(f"Found {len(items)} items in folder", "info", {"item_count": len(items)})
    
    for i, item in enumerate(items):
        item_path = local_path / item["name"]
        rel_path = str(item_path.relative_to(local_path.parent))
        path_to_id[rel_path] = item["id"]
        
        agent_log(f"Processing item {i+1}/{len(items)}: {item['name']}", "info", {
            "item_name": item["name"],
            "item_type": item["doc_type"],
            "progress": f"{i+1}/{len(items)}"
        })
        
        if progress and task_id:
            progress.update(task_id, description=f"Downloading {item['name']} ({i+1}/{len(items)})")
        
        if item["doc_type"] == "Folder":
            # Skip index guides for cleaner local structure
            if item["name"] == "_index.guide":
                agent_log("Skipping index guide", "info")
                continue
                
            # Recursively download subfolder
            sub_mapping = download_folder_recursive(item["id"], item_path, progress, task_id)
            path_to_id.update(sub_mapping)
        else:
            # Download file content
            doc = api_request("GET", f"/docs/{item['id']}")
            content = doc.get("content", "")
            
            # Skip index guides
            if doc["doc_type"] == "IndexGuide":
                agent_log("Skipping index guide document", "info")
                continue
            
            agent_log(f"Writing file: {item['name']}", "info", {
                "file_size": len(content),
                "encoding": "utf-8"
            })
            item_path.write_text(content, encoding="utf-8")
    
    return path_to_id


def upload_changes_recursive(local_dir: Path, hub_folder_id: str, path_to_id: Dict[str, str], 
                           old_state: Dict[str, Any], new_state: Dict[str, Any]) -> Dict[str, str]:
    """Upload changes back to Context Hub with conflict resolution."""
    updated_mapping = path_to_id.copy()
    
    # Detect changes
    all_paths = set(old_state.keys()) | set(new_state.keys())
    
    for rel_path in all_paths:
        old_item = old_state.get(rel_path, {})
        new_item = new_state.get(rel_path, {})
        
        local_path = local_dir / rel_path
        
        # Item was deleted locally
        if old_item and not new_item:
            if rel_path in path_to_id:
                try:
                    api_request("DELETE", f"/docs/{path_to_id[rel_path]}")
                    console.print(f"[yellow]Deleted: {rel_path}[/yellow]")
                    del updated_mapping[rel_path]
                except:
                    console.print(f"[red]Failed to delete: {rel_path}[/red]")
            continue
        
        # Item was added locally
        if not old_item and new_item:
            parent_path = str(Path(rel_path).parent)
            if parent_path == ".":
                parent_id = hub_folder_id
            else:
                parent_id = updated_mapping.get(parent_path)
                if not parent_id:
                    # Create parent folders if needed
                    parent_id = create_folder_path(local_dir, Path(rel_path).parent, hub_folder_id, updated_mapping)
            
            if new_item["type"] == "folder":
                # Create new folder
                data = {
                    "name": Path(rel_path).name,
                    "content": "",
                    "parent_folder_id": parent_id,
                    "doc_type": "Folder"
                }
                result = api_request("POST", "/docs", json=data)
                updated_mapping[rel_path] = result["id"]
                console.print(f"[green]Created folder: {rel_path}[/green]")
            else:
                # Create new file
                content = local_path.read_text(encoding="utf-8") if local_path.exists() else ""
                data = {
                    "name": Path(rel_path).name,
                    "content": content,
                    "parent_folder_id": parent_id,
                    "doc_type": "Text"
                }
                result = api_request("POST", "/docs", json=data)
                updated_mapping[rel_path] = result["id"]
                console.print(f"[green]Created file: {rel_path}[/green]")
            continue
        
        # Item was modified (files only)
        if old_item and new_item and new_item["type"] == "file":
            old_hash = old_item.get("hash", "")
            new_hash = new_item.get("hash", "")
            
            if old_hash != new_hash and local_path.exists():
                # File content changed
                doc_id = path_to_id.get(rel_path)
                if doc_id:
                    content = local_path.read_text(encoding="utf-8")
                    # Include name field for API compatibility
                    data = {
                        "name": Path(rel_path).name,
                        "content": content
                    }
                    api_request("PUT", f"/docs/{doc_id}", json=data)
                    console.print(f"[blue]Updated: {rel_path}[/blue]")
    
    return updated_mapping


def create_folder_path(local_dir: Path, folder_path: Path, root_id: str, path_mapping: Dict[str, str]) -> str:
    """Create nested folder structure in Context Hub."""
    parts = folder_path.parts
    current_id = root_id
    current_path = ""
    
    for part in parts:
        current_path = f"{current_path}/{part}" if current_path else part
        
        if current_path in path_mapping:
            current_id = path_mapping[current_path]
        else:
            # Create folder
            data = {
                "name": part,
                "content": "",
                "parent_folder_id": current_id,
                "doc_type": "Folder"
            }
            result = api_request("POST", "/docs", json=data)
            current_id = result["id"]
            path_mapping[current_path] = current_id
            console.print(f"[green]Created folder: {current_path}[/green]")
    
    return current_id


# ============================================================================
# COMMANDS
# ============================================================================

@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output for agents")
@click.option("--json", "json_output", is_flag=True, help="Output in JSON format for machine parsing")
@click.pass_context
def cli(ctx, verbose: bool, json_output: bool):
    """Context Hub - Git-like collaboration for AI agents and humans."""
    
    # Set global output modes
    set_output_mode(verbose, json_output)
    
    # Load config and apply persistent settings
    config = load_config()
    if config.get("verbose", False):
        set_output_mode(True, json_output)
    if config.get("json_output", False):
        set_output_mode(verbose, True)
    
    if ctx.invoked_subcommand is None:
        # Show status when no command given (like git)
        ctx.invoke(status)


@cli.command()
def status():
    """Show the working directory status."""
    config = load_config()
    current_workspace = config.get("current_workspace") or "/"
    user = get_current_user()
    
    try:
        # Get current folder info
        folder_id = resolve_path("")
        folder_info = api_request("GET", f"/docs/{folder_id}")
        items = api_request("GET", f"/folders/{folder_id}")
        
        # Process items for structured output
        processed_items = []
        for item in items:
            doc_type = item["doc_type"]
            processed_item = {
                "id": item["id"],
                "name": item["name"],
                "type": doc_type.lower(),
                "doc_type": doc_type
            }
            
            # Add size for files
            if doc_type not in ["Folder", "IndexGuide"]:
                try:
                    doc = api_request("GET", f"/docs/{item['id']}")
                    content = doc.get("content", "")
                    processed_item["size_bytes"] = len(content.encode('utf-8'))
                    processed_item["size_human"] = format_size(content)
                    processed_item["line_count"] = len(content.splitlines())
                except:
                    processed_item["size_bytes"] = 0
                    processed_item["size_human"] = ""
                    processed_item["line_count"] = 0
            
            processed_items.append(processed_item)
        
        # Count types
        folders = [item for item in processed_items if item["type"] == "folder"]
        files = [item for item in processed_items if item["type"] not in ["folder", "indexguide"]]
        guides = [item for item in processed_items if item["type"] == "indexguide"]
        
        status_data = {
            "workspace": current_workspace,
            "user": user,
            "folder_id": folder_id,
            "folder_name": folder_info.get("name", ""),
            "total_items": len(processed_items),
            "counts": {
                "folders": len(folders),
                "files": len(files),
                "guides": len(guides)
            },
            "items": processed_items,
            "is_empty": len(processed_items) == 0
        }
        
        if JSON_OUTPUT:
            return llm_response(True, "status", status_data)
        
        # Human-friendly output
        console.print(f"[bold]Context Hub Status[/bold]")
        console.print(f"User: [cyan]{user}[/cyan]")
        console.print(f"Workspace: [blue]{current_workspace}[/blue]")
        
        if not items:
            console.print("\n[dim]Empty workspace[/dim]")
            return
        
        # Show contents table
        console.print(f"\n[bold]Contents ({len(items)} items):[/bold]")
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Type", width=8)
        table.add_column("Name", style="cyan")
        table.add_column("Size", justify="right", width=8)
        table.add_column("Lines", justify="right", width=6)
        
        for item in processed_items:
            if item["type"] == "folder":
                type_str = "📁 dir"
                size_str = ""
                lines_str = ""
            elif item["type"] == "indexguide":
                type_str = "📋 guide"
                size_str = ""
                lines_str = ""
            else:
                type_str = "📄 file"
                size_str = item.get("size_human", "")
                lines_str = str(item.get("line_count", ""))
            
            table.add_row(type_str, item["name"], size_str, lines_str)
        
        console.print(table)
        
        # Show shared folders in root
        if current_workspace == "/":
            shared_count = sum(1 for item in items if item["name"].endswith(" (shared)"))
            if shared_count > 0:
                console.print(f"\n[yellow]📤 {shared_count} shared folders available[/yellow]")
                
    except Exception as e:
        error_msg = str(e)
        if JSON_OUTPUT:
            return llm_response(False, "status", error=error_msg)
        else:
            console.print(f"[red]Error: {error_msg}[/red]")
            sys.exit(1)


@cli.command()
@click.argument("path", default="")
def ls(path: str):
    """List contents of a folder."""
    folder_id = resolve_path(path)
    folder_info = api_request("GET", f"/docs/{folder_id}")
    items = api_request("GET", f"/folders/{folder_id}")
    
    if folder_info["doc_type"] != "Folder":
        console.print(f"[red]Not a folder: {path}[/red]")
        sys.exit(1)
    
    if not items:
        console.print("[dim]Empty folder[/dim]")
        return
    
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column("Type", width=2)
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right", width=8)
    
    # Sort: folders first, then files
    items.sort(key=lambda x: (x["doc_type"] != "Folder", x["name"]))
    
    for item in items:
        if item["doc_type"] == "Folder":
            icon = "📁"
            size = ""
        elif item["doc_type"] == "IndexGuide":
            icon = "📋"
            size = ""
        else:
            icon = "📄"
            try:
                doc = api_request("GET", f"/docs/{item['id']}")
                size = format_size(doc.get("content", ""))
            except:
                size = ""
        
        table.add_row(icon, item["name"], size)
    
    console.print(table)


@cli.command()
@click.argument("path")
@click.option("--numbered", "-n", is_flag=True, help="Show content with line numbers")
def cat(path: str, numbered: bool):
    """Show content of a document."""
    doc_id = resolve_path(path)
    
    # Use numbered format if requested
    params = {"format": "numbered"} if numbered else {}
    doc = api_request("GET", f"/docs/{doc_id}", params=params)
    
    if doc["doc_type"] == "Folder":
        console.print(f"[red]Cannot cat a folder. Use 'ch ls {path}' instead.[/red]")
        sys.exit(1)
    
    # Handle numbered or regular content
    if numbered and "numbered_content" in doc:
        content = doc["numbered_content"]
        line_count = doc.get("line_count", 0)
        agent_log("Retrieved numbered content", "info", {"line_count": line_count})
    else:
        content = doc.get("content", "")
    
    if not content:
        console.print("[dim]Empty file[/dim]")
    else:
        console.print(content)


@cli.command()
@click.argument("path")
def cd(path: str):
    """Change current workspace directory."""
    folder_id = resolve_path(path)
    folder_info = api_request("GET", f"/docs/{folder_id}")
    
    if folder_info["doc_type"] != "Folder":
        console.print(f"[red]Not a folder: {path}[/red]")
        sys.exit(1)
    
    # Update config with new workspace
    config = load_config()
    current = config.get("current_workspace") or "/"
    
    if path.startswith("/"):
        # Absolute path
        config["current_workspace"] = path
    else:
        # Relative path
        if current == "/":
            config["current_workspace"] = f"/{path}"
        else:
            config["current_workspace"] = f"{current.rstrip('/')}/{path}"
    
    save_config(config)
    console.print(f"[green]Changed to: {config['current_workspace']}[/green]")


@cli.command()
def pwd():
    """Show current workspace directory."""
    config = load_config()
    workspace = config.get("current_workspace") or "/"
    console.print(workspace)


@cli.command()
@click.argument("name")
@click.option("--folder", "-d", is_flag=True, help="Create a folder")
@click.option("--content", "-c", default="", help="Initial content for file")
@click.option("--edit", "-e", is_flag=True, help="Open editor after creation")
def new(name: str, folder: bool, content: str, edit: bool):
    """Create a new file or folder."""
    current_id = resolve_path("")
    
    doc_type = "Folder" if folder else "Text"
    data = {
        "name": name,
        "content": content,
        "parent_folder_id": current_id,
        "doc_type": doc_type
    }
    
    result = api_request("POST", "/docs", json=data)
    
    type_str = "folder" if folder else "file"
    console.print(f"[green]Created {type_str}: {name}[/green]")
    
    if edit and not folder:
        # Would open editor here
        console.print("[dim]Editor integration coming soon![/dim]")


@cli.command()
@click.argument("source")
@click.argument("dest")
def mv(source: str, dest: str):
    """Move or rename a file/folder."""
    source_id = resolve_path(source)
    
    # Determine if dest is a rename or move
    if "/" in dest:
        # Move to different location
        dest_parts = dest.rsplit("/", 1)
        dest_folder = resolve_path(dest_parts[0])
        new_name = dest_parts[1]
        
        # Move
        move_data = {"new_parent_folder_id": dest_folder}
        api_request("PUT", f"/docs/{source_id}/move", json=move_data)
        
        # Rename if name changed
        if new_name != source.split("/")[-1]:
            rename_data = {"name": new_name}
            api_request("PUT", f"/docs/{source_id}/rename", json=rename_data)
    else:
        # Just rename
        rename_data = {"name": dest}
        api_request("PUT", f"/docs/{source_id}/rename", json=rename_data)
    
    console.print(f"[green]Moved {source} → {dest}[/green]")


@cli.command()
@click.argument("path")
def rm(path: str):
    """Remove a file or folder."""
    doc_id = resolve_path(path)
    doc_info = api_request("GET", f"/docs/{doc_id}")
    
    api_request("DELETE", f"/docs/{doc_id}")
    
    type_str = "folder" if doc_info["doc_type"] == "Folder" else "file"
    console.print(f"[green]Removed {type_str}: {path}[/green]")


@cli.command()
@click.argument("path")
@click.option("--patch-file", "-f", help="Apply patch from file")
@click.option("--patch", "-p", help="Apply patch from string")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be patched without applying")
def patch(path: str, patch_file: str, patch: str, dry_run: bool):
    """Apply unified diff patch to a document."""
    doc_id = resolve_path(path)
    doc_info = api_request("GET", f"/docs/{doc_id}")
    
    if doc_info["doc_type"] == "Folder":
        console.print(f"[red]Cannot patch a folder: {path}[/red]")
        sys.exit(1)
    
    # Get patch content
    if patch_file:
        try:
            patch_content = Path(patch_file).read_text()
            agent_log("Loaded patch from file", "info", {"file": patch_file, "size": len(patch_content)})
        except IOError as e:
            console.print(f"[red]Error reading patch file: {e}[/red]")
            sys.exit(1)
    elif patch:
        patch_content = patch
        agent_log("Using inline patch", "info", {"size": len(patch_content)})
    else:
        console.print("[red]Must specify either --patch-file or --patch[/red]")
        sys.exit(1)
    
    # Validate patch format (basic check)
    if not any(line.startswith(('@@', '---', '+++', '-', '+')) for line in patch_content.splitlines()):
        console.print("[yellow]Warning: Patch doesn't look like unified diff format[/yellow]")
    
    if dry_run:
        console.print(f"[blue]Would apply patch to: {path}[/blue]")
        console.print("[dim]Patch content:[/dim]")
        console.print(patch_content)
        console.print("[dim]Use without --dry-run to apply[/dim]")
        return
    
    # Apply patch
    try:
        data = {"patch": patch_content}
        result = api_request("PATCH", f"/docs/{doc_id}", json=data)
        
        agent_log("Patch applied successfully", "success", {
            "document": path,
            "patch_size": len(patch_content)
        })
        
        console.print(f"[green]✓ Patch applied to: {path}[/green]")
        if result and "message" in result:
            console.print(f"[dim]{result['message']}[/dim]")
            
    except Exception as e:
        agent_log("Patch application failed", "error", {"error": str(e)})
        console.print(f"[red]Patch failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("path")
@click.argument("local_file", required=False)
@click.option("--output", "-o", help="Save diff to file")
@click.option("--context", "-c", default=3, help="Number of context lines")
def diff(path: str, local_file: str, output: str, context: int):
    """Generate unified diff between document and local file."""
    doc_id = resolve_path(path)
    doc = api_request("GET", f"/docs/{doc_id}")
    
    if doc["doc_type"] == "Folder":
        console.print(f"[red]Cannot diff a folder: {path}[/red]")
        sys.exit(1)
    
    # Get document content
    doc_content = doc.get("content", "").splitlines(keepends=True)
    doc_name = f"a/{doc['name']}"
    
    if local_file:
        # Compare with local file
        try:
            local_content = Path(local_file).read_text().splitlines(keepends=True)
            local_name = f"b/{Path(local_file).name}"
        except IOError as e:
            console.print(f"[red]Error reading local file: {e}[/red]")
            sys.exit(1)
    else:
        # Compare with stdin or empty
        console.print("[blue]Enter content to compare (Ctrl+D when done):[/blue]")
        try:
            import sys
            stdin_content = sys.stdin.read().splitlines(keepends=True)
            local_content = stdin_content
            local_name = "b/stdin"
        except KeyboardInterrupt:
            console.print("\n[yellow]Diff cancelled[/yellow]")
            sys.exit(0)
    
    # Generate unified diff
    diff_lines = list(difflib.unified_diff(
        doc_content, 
        local_content,
        fromfile=doc_name,
        tofile=local_name,
        n=context
    ))
    
    if not diff_lines:
        console.print("[green]No differences found[/green]")
        return
    
    diff_text = ''.join(diff_lines)
    
    if output:
        # Save to file
        Path(output).write_text(diff_text)
        console.print(f"[green]Diff saved to: {output}[/green]")
        agent_log("Diff saved to file", "success", {
            "output_file": output,
            "diff_size": len(diff_text)
        })
    else:
        # Print to console
        console.print(diff_text)
    
    # Show summary
    added = len([line for line in diff_lines if line.startswith('+')])
    removed = len([line for line in diff_lines if line.startswith('-')])
    console.print(f"[dim]+{added} -{removed} lines[/dim]")


@cli.command()
@click.argument("operation", type=click.Choice(['create', 'update', 'patch', 'delete']))
@click.option("--file", "-f", required=True, help="JSON file with batch operations")
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be done without executing")
@click.option("--parallel", "-p", default=1, help="Number of parallel operations")
def batch(operation: str, file: str, dry_run: bool, parallel: int):
    """Execute batch operations from JSON file."""
    try:
        batch_data = json.loads(Path(file).read_text())
    except (IOError, json.JSONDecodeError) as e:
        console.print(f"[red]Error reading batch file: {e}[/red]")
        sys.exit(1)
    
    if not isinstance(batch_data, list):
        console.print("[red]Batch file must contain a JSON array[/red]")
        sys.exit(1)
    
    console.print(f"[blue]Batch {operation}: {len(batch_data)} operations[/blue]")
    
    if dry_run:
        console.print("[dim]Dry run - no changes will be made[/dim]")
        for i, item in enumerate(batch_data, 1):
            console.print(f"[dim]{i}. {operation} {item.get('path', item.get('name', 'unnamed'))}[/dim]")
        return
    
    success_count = 0
    error_count = 0
    
    with enhanced_progress_bar(f"Executing {operation} operations...") as progress:
        if progress:
            task = progress.add_task(f"Processing...", total=len(batch_data))
        
        for i, item in enumerate(batch_data):
            if progress:
                progress.update(task, advance=1, description=f"Processing {i+1}/{len(batch_data)}")
            
            try:
                if operation == "create":
                    # Expected: {"name": "file.txt", "content": "...", "parent_folder_id": "..."}
                    api_request("POST", "/docs", json=item)
                    console.print(f"[green]✓ Created: {item.get('name')}[/green]")
                
                elif operation == "update":
                    # Expected: {"path": "/file.txt", "content": "..."}
                    doc_id = resolve_path(item["path"])
                    update_data = {k: v for k, v in item.items() if k != "path"}
                    api_request("PUT", f"/docs/{doc_id}", json=update_data)
                    console.print(f"[green]✓ Updated: {item['path']}[/green]")
                
                elif operation == "patch":
                    # Expected: {"path": "/file.txt", "patch": "unified diff"}
                    doc_id = resolve_path(item["path"])
                    api_request("PATCH", f"/docs/{doc_id}", json={"patch": item["patch"]})
                    console.print(f"[green]✓ Patched: {item['path']}[/green]")
                
                elif operation == "delete":
                    # Expected: {"path": "/file.txt"}
                    doc_id = resolve_path(item["path"])
                    api_request("DELETE", f"/docs/{doc_id}")
                    console.print(f"[green]✓ Deleted: {item['path']}[/green]")
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                path = item.get("path", item.get("name", "unknown"))
                console.print(f"[red]✗ Failed {operation} {path}: {e}[/red]")
                
                if error_count > len(batch_data) // 2:
                    console.print("[red]Too many errors, stopping batch operation[/red]")
                    break
    
    console.print(f"\n[bold]Batch {operation} complete:[/bold]")
    console.print(f"[green]Success: {success_count}[/green]")
    console.print(f"[red]Errors: {error_count}[/red]")
    
    agent_log("Batch operation completed", "info", {
        "operation": operation,
        "total": len(batch_data),
        "success": success_count,
        "errors": error_count
    })


@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Maximum results")
def search(query: str, limit: int):
    """Search for content across all accessible documents."""
    params = {"q": query, "limit": limit}
    results = api_request("GET", "/search", params=params)
    
    if not results:
        console.print(f"[yellow]No results found for: {query}[/yellow]")
        return
    
    console.print(f"[bold]Found {len(results)} results for '{query}':[/bold]\n")
    
    for result in results:
        console.print(f"[cyan]{result['name']}[/cyan]")
        console.print(f"[dim]{result['snippet']}...[/dim]")
        console.print()


@cli.command()
@click.argument("path")
@click.argument("user")
@click.option("--write", "-w", is_flag=True, help="Grant write access")
def share(path: str, user: str, write: bool):
    """Share a folder with another user."""
    folder_id = resolve_path(path)
    rights = "write" if write else "read"
    
    data = {"user": user, "rights": rights}
    api_request("POST", f"/folders/{folder_id}/share", json=data)
    
    access = "write" if write else "read-only"
    console.print(f"[green]Shared {path} with {user} ({access})[/green]")


@cli.command()
def shared():
    """Show all shared folders and their permissions."""
    # Get root folder items to find shared folders
    root_id = api_request("GET", "/root")["id"]
    items = api_request("GET", f"/folders/{root_id}")
    
    console.print("[bold]Shared Folders:[/bold]\n")
    
    shared_found = False
    for item in items:
        if item["doc_type"] == "Folder":
            try:
                sharing_info = api_request("GET", f"/docs/{item['id']}/sharing")
                if sharing_info:  # Has sharing permissions
                    shared_found = True
                    console.print(f"📁 [cyan]{item['name']}[/cyan]")
                    for perm in sharing_info:
                        access_color = "green" if perm["access"] == "Write" else "yellow"
                        console.print(f"  └─ {perm['principal']}: [{access_color}]{perm['access'].lower()}[/{access_color}]")
                    console.print()
            except:
                continue  # No sharing info available
    
    if not shared_found:
        console.print("[dim]No shared folders found[/dim]")


@cli.group()
def config():
    """Configuration management."""
    pass


@config.command()
@click.argument("username")
def user(username: str):
    """Set the current user."""
    config = load_config()
    config["user"] = username
    save_config(config)
    console.print(f"[green]User set to: {username}[/green]")


@config.command()
@click.argument("url")
def server(url: str):
    """Set the server URL."""
    config = load_config()
    config["url"] = url.rstrip("/")
    save_config(config)
    console.print(f"[green]Server set to: {url}[/green]")


@config.command()
@click.argument("agent_id")
def agent(agent_id: str):
    """Set the agent ID."""
    config = load_config()
    config["agent"] = agent_id
    save_config(config)
    console.print(f"[green]Agent set to: {agent_id}[/green]")


@config.command()
def show():
    """Show current configuration."""
    config = load_config()
    
    table = Table(title="Context Hub Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Server", config.get("url", "Not set"))
    table.add_row("User", config.get("user", "Not set"))
    table.add_row("Agent", config.get("agent", "Not set"))
    table.add_row("Workspace", config.get("current_workspace", "/"))
    table.add_row("Azure Tenant ID", config.get("azure_tenant_id", "Not set"))
    table.add_row("Azure Client ID", config.get("azure_client_id", "Not set"))
    table.add_row("Azure Scope", config.get("azure_scope", "api://context-hub/.default"))
    
    # Show authentication status
    auth_status = "Legacy Headers"
    if config.get("azure_tenant_id") and config.get("azure_client_id"):
        cache_file = config.get("token_cache_file", str(Path.home() / ".context-hub" / "tokens.json"))
        cache = TokenCache(cache_file)
        cached_tokens = cache.load_tokens()
        cache_key = f"{config['azure_tenant_id']}:{config['azure_client_id']}:{config.get('azure_scope', 'api://context-hub/.default')}"
        
        if cache_key in cached_tokens:
            access_token = cached_tokens[cache_key].get("access_token")
            if access_token and cache.is_token_valid(access_token):
                auth_status = "Azure AD (Valid Token)"
            else:
                auth_status = "Azure AD (Token Expired)"
        else:
            auth_status = "Azure AD (Not Authenticated)"
    
    table.add_row("Auth Status", auth_status)
    console.print(table)


@config.command()
@click.argument("setting")
@click.argument("value", required=False)
def set(setting: str, value: Optional[str]):
    """Set persistent configuration options."""
    config = load_config()
    
    if setting == "verbose":
        config["verbose"] = value.lower() in ("true", "1", "yes", "on") if value else True
        save_config(config)
        console.print(f"[green]Verbose mode: {'enabled' if config['verbose'] else 'disabled'}[/green]")
    
    elif setting == "json":
        config["json_output"] = value.lower() in ("true", "1", "yes", "on") if value else True
        save_config(config)
        console.print(f"[green]JSON output: {'enabled' if config['json_output'] else 'disabled'}[/green]")
    
    elif setting == "workspace":
        config["current_workspace"] = value or "/"
        save_config(config)
        console.print(f"[green]Workspace set to: {config['current_workspace']}[/green]")
    
    else:
        console.print(f"[red]Unknown setting: {setting}[/red]")
        console.print("Available settings: verbose, json, workspace")
        sys.exit(1)


@config.command()
def reset():
    """Reset all configuration to defaults."""
    config = DEFAULT_CONFIG.copy()
    save_config(config)
    console.print("[green]Configuration reset to defaults[/green]")


@config.command()
@click.argument("tenant_id", required=False)
@click.argument("client_id", required=False)
@click.option("--scope", default="api://context-hub/.default", help="Azure AD scope")
@click.option("--from-env", is_flag=True, help="Load from ../env.azure file")
def azure(tenant_id: str, client_id: str, scope: str, from_env: bool):
    """Configure Azure AD authentication."""
    config = load_config()
    
    if from_env or (not tenant_id and not client_id):
        # Load from .env.azure file
        env_file = Path(__file__).parent.parent / ".env.azure"
        if env_file.exists():
            console.print(f"[blue]Loading Azure AD config from {env_file}[/blue]")
            
            env_vars = {}
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
            
            tenant_id = env_vars.get("AAD_TENANT_ID")
            client_id = env_vars.get("AAD_CLIENT_ID")
            
            if not tenant_id or not client_id:
                console.print("[red]AAD_TENANT_ID or AAD_CLIENT_ID not found in .env.azure[/red]")
                sys.exit(1)
                
            console.print("[green]✓ Found Azure AD configuration in .env.azure[/green]")
        else:
            console.print(f"[red].env.azure file not found at {env_file}[/red]")
            console.print("Usage: ch config azure <tenant-id> <client-id>")
            sys.exit(1)
    
    if not tenant_id or not client_id:
        console.print("[red]Missing tenant_id or client_id[/red]")
        console.print("Usage: ch config azure <tenant-id> <client-id>")
        console.print("   or: ch config azure --from-env")
        sys.exit(1)
    
    config["azure_tenant_id"] = tenant_id
    config["azure_client_id"] = client_id
    config["azure_scope"] = scope
    save_config(config)
    
    console.print("[green]Azure AD configuration saved[/green]")
    console.print(f"Tenant ID: [cyan]{tenant_id}[/cyan]")
    console.print(f"Client ID: [cyan]{client_id}[/cyan]")
    console.print(f"Scope: [cyan]{scope}[/cyan]")
    console.print("\n[dim]Run any command to authenticate with Azure AD[/dim]")


@config.command()
def login():
    """Force Azure AD login/re-authentication."""
    config = load_config()
    
    if not config.get("azure_tenant_id") or not config.get("azure_client_id"):
        console.print("[red]Azure AD not configured. Run 'ch config azure' first.[/red]")
        sys.exit(1)
    
    # Clear existing tokens to force fresh login
    cache_file = config.get("token_cache_file", str(Path.home() / ".context-hub" / "tokens.json"))
    cache = TokenCache(cache_file)
    cache_key = f"{config['azure_tenant_id']}:{config['azure_client_id']}:{config.get('azure_scope', 'api://context-hub/.default')}"
    cached_tokens = cache.load_tokens()
    if cache_key in cached_tokens:
        del cached_tokens[cache_key]
        cache.save_tokens(cached_tokens)
    
    console.print("[blue]Initiating Azure AD authentication...[/blue]")
    
    try:
        access_token = get_azure_token()
        console.print("[green]✓ Successfully authenticated with Azure AD![/green]")
        
        # Decode token to show user info
        try:
            decoded = jwt.decode(access_token, options={"verify_signature": False})
            if "name" in decoded:
                console.print(f"Logged in as: [cyan]{decoded['name']}[/cyan]")
            elif "upn" in decoded:
                console.print(f"Logged in as: [cyan]{decoded['upn']}[/cyan]")
        except:
            pass
            
    except Exception as e:
        console.print(f"[red]Authentication failed: {e}[/red]")
        sys.exit(1)


@config.command()
def logout():
    """Clear cached Azure AD tokens."""
    config = load_config()
    
    if not config.get("azure_tenant_id"):
        console.print("[yellow]No Azure AD configuration found[/yellow]")
        return
    
    cache_file = config.get("token_cache_file", str(Path.home() / ".context-hub" / "tokens.json"))
    cache = TokenCache(cache_file)
    cache_key = f"{config['azure_tenant_id']}:{config['azure_client_id']}:{config.get('azure_scope', 'api://context-hub/.default')}"
    cached_tokens = cache.load_tokens()
    
    if cache_key in cached_tokens:
        del cached_tokens[cache_key]
        cache.save_tokens(cached_tokens)
        console.print("[green]✓ Logged out from Azure AD[/green]")
    else:
        console.print("[yellow]No active session found[/yellow]")


@cli.command()
@click.argument("hub_path")
@click.argument("local_path")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing local directory")
def pull(hub_path: str, local_path: str, force: bool):
    """Pull Context Hub folder to local filesystem for editing."""
    start_time = time.time()
    local_dir = Path(local_path)
    
    agent_log("Starting pull operation", "info", {
        "hub_path": hub_path,
        "local_path": local_path,
        "force": force
    })
    
    # Check if local directory exists
    if local_dir.exists() and not force:
        if list(local_dir.iterdir()):  # Not empty
            agent_log("Directory exists and is not empty", "error", {
                "path": local_path,
                "solution": "use --force flag"
            })
            console.print(f"[red]Directory {local_path} already exists and is not empty.[/red]")
            console.print("Use --force to overwrite or choose a different path.")
            sys.exit(1)
    
    # Resolve hub path to ID
    agent_log("Resolving hub path", "info", {"hub_path": hub_path})
    resolve_start = time.time()
    hub_folder_id = resolve_path(hub_path)
    resolve_duration = time.time() - resolve_start
    
    hub_doc = api_request("GET", f"/docs/{hub_folder_id}")
    agent_log("Hub path resolved", "info", {
        "hub_folder_id": hub_folder_id,
        "folder_name": hub_doc["name"],
        "resolve_duration": resolve_duration
    })
    
    if hub_doc["doc_type"] != "Folder":
        agent_log("Path is not a folder", "error", {
            "path": hub_path,
            "actual_type": hub_doc["doc_type"]
        })
        console.print(f"[red]Path is not a folder: {hub_path}[/red]")
        sys.exit(1)
    
    if not JSON_OUTPUT:
        console.print(f"[blue]Pulling '{hub_doc['name']}' to {local_path}...[/blue]")
    
    # Create/clear local directory
    if local_dir.exists() and force:
        agent_log("Removing existing directory", "info", {"path": local_path})
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    
    # Download with enhanced progress
    agent_log("Starting download", "info")
    download_start = time.time()
    
    progress_bar = enhanced_progress_bar("Downloading files...")
    if progress_bar:
        with progress_bar as progress:
            task = progress.add_task("Downloading files...", total=None)
            path_to_id = download_folder_recursive(hub_folder_id, local_dir, progress, task)
            progress.update(task, description="Download complete!")
    else:
        path_to_id = download_folder_recursive(hub_folder_id, local_dir)
    
    download_duration = time.time() - download_start
    
    # Save sync state for future push
    initial_state = scan_local_tree(local_dir)
    sync_state = {
        "hub_folder_id": hub_folder_id,
        "hub_path": hub_path,
        "pulled_at": datetime.now().isoformat(),
        "path_to_id": path_to_id,
        "initial_state": initial_state,
        "user": get_current_user()
    }
    save_sync_state(local_dir, sync_state)
    
    # Calculate statistics
    file_count = len([s for s in initial_state.values() if s["type"] == "file"])
    folder_count = len([s for s in initial_state.values() if s["type"] == "folder"])
    total_size = sum(s.get("size", 0) for s in initial_state.values() if s["type"] == "file")
    
    pull_stats = {
        "result": "success",
        "duration": time.time() - start_time,
        "download_duration": download_duration,
        "resolve_duration": resolve_duration,
        "files_downloaded": file_count,
        "folders_created": folder_count,
        "total_size_bytes": total_size,
        "items_total": len(path_to_id)
    }
    
    agent_log("Pull completed successfully", "success", pull_stats)
    
    console.print(f"\n[green]✓ Successfully pulled to {local_path}[/green]")
    console.print(f"Files: {file_count}, Folders: {folder_count}")
    if VERBOSE_MODE:
        console.print(f"Total size: {total_size} bytes")
        console.print(f"Download time: {download_duration:.2f}s")
    
    console.print(f"\n[dim]Work locally with normal tools, then run:[/dim]")
    console.print(f"[cyan]ch push {local_path} {hub_path}[/cyan]")
    
    operation_summary("pull", pull_stats)


@cli.command()
@click.argument("local_path")
@click.argument("hub_path", required=False)
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be changed without uploading")
@click.option("--no-confirm", is_flag=True, help="Skip confirmation prompt (for automated workflows)")
def push(local_path: str, hub_path: Optional[str], dry_run: bool, no_confirm: bool):
    """Push local changes back to Context Hub with auto conflict resolution."""
    start_time = time.time()
    local_dir = Path(local_path)
    
    agent_log("Starting push operation", "info", {
        "local_path": local_path,
        "hub_path": hub_path,
        "dry_run": dry_run,
        "no_confirm": no_confirm
    })
    
    if not local_dir.exists():
        agent_log("Directory does not exist", "error", {"path": local_path})
        console.print(f"[red]Local directory does not exist: {local_path}[/red]")
        sys.exit(1)
    
    # Load sync state
    agent_log("Loading sync state", "info")
    sync_state = load_sync_state(local_dir)
    if not sync_state:
        agent_log("No sync state found", "error", {"local_path": local_path})
        console.print(f"[red]No sync state found in {local_path}[/red]")
        console.print("This directory was not pulled from Context Hub.")
        console.print("Use 'ch pull <hub_path> <local_path>' first.")
        sys.exit(1)
    
    # Use hub path from sync state if not provided
    if not hub_path:
        hub_path = sync_state["hub_path"]
        agent_log("Using hub path from sync state", "info", {"hub_path": hub_path})
        if not JSON_OUTPUT:
            console.print(f"[dim]Using hub path from sync state: {hub_path}[/dim]")
    
    hub_folder_id = sync_state["hub_folder_id"]
    old_state = sync_state["initial_state"]
    path_to_id = sync_state["path_to_id"]
    
    # Scan current local state
    agent_log("Scanning local changes", "info")
    if not JSON_OUTPUT:
        console.print("[blue]Scanning local changes...[/blue]")
    
    scan_start = time.time()
    current_state = scan_local_tree(local_dir)
    scan_duration = time.time() - scan_start
    
    agent_log("Scan completed", "info", {
        "scan_duration": scan_duration,
        "files_scanned": len(current_state)
    })
    
    # Detect changes
    added = set(current_state.keys()) - set(old_state.keys())
    removed = set(old_state.keys()) - set(current_state.keys())
    modified = []
    
    for path in set(old_state.keys()) & set(current_state.keys()):
        old_item = old_state[path]
        new_item = current_state[path]
        
        if old_item["type"] == "file" and new_item["type"] == "file":
            if old_item.get("hash") != new_item.get("hash"):
                modified.append(path)
    
    # Detailed change analysis
    change_stats = {
        "added": len(added),
        "removed": len(removed), 
        "modified": len(modified),
        "total_changes": len(added) + len(removed) + len(modified)
    }
    
    agent_log("Change detection completed", "info", change_stats)
    
    if change_stats["total_changes"] == 0:
        agent_log("No changes detected", "info")
        console.print("[green]No changes detected.[/green]")
        operation_summary("push", {
            "result": "no_changes",
            "duration": time.time() - start_time,
            **change_stats
        })
        return
    
    # Show detailed change summary
    if not JSON_OUTPUT:
        console.print(f"\n[bold]Changes detected:[/bold]")
        if added:
            console.print(f"[green]Added ({len(added)}):[/green]")
            for path in sorted(added):
                item_type = current_state[path]["type"]
                size_info = f" ({current_state[path].get('size', 0)} bytes)" if item_type == "file" else ""
                console.print(f"  + {path} ({item_type}){size_info}")
        
        if removed:
            console.print(f"[red]Removed ({len(removed)}):[/red]")
            for path in sorted(removed):
                item_type = old_state[path]["type"]
                console.print(f"  - {path} ({item_type})")
        
        if modified:
            console.print(f"[blue]Modified ({len(modified)}):[/blue]")
            for path in sorted(modified):
                old_size = old_state[path].get("size", 0)
                new_size = current_state[path].get("size", 0)
                size_change = f" ({old_size} → {new_size} bytes)" if old_size != new_size else ""
                console.print(f"  ~ {path}{size_change}")
    
    if dry_run:
        agent_log("Dry run completed", "info", change_stats)
        console.print(f"\n[dim]Dry run complete. Use 'ch push {local_path}' to apply changes.[/dim]")
        operation_summary("push_dry_run", {
            "result": "dry_run",
            "duration": time.time() - start_time,
            **change_stats
        })
        return
    
    # Confirm push (agent-friendly: default Yes, or skip entirely)
    if not no_confirm:
        if not click.confirm(f"\nPush {change_stats['total_changes']} changes to Context Hub?", default=True):
            agent_log("Push cancelled by user", "info")
            console.print("Push cancelled.")
            return
    else:
        agent_log("Auto-confirming push", "info", {"reason": "no_confirm_flag"})
        if not JSON_OUTPUT:
            console.print(f"\n[dim]Auto-pushing {change_stats['total_changes']} changes (--no-confirm)[/dim]")
    
    # Upload changes
    agent_log("Starting upload process", "info", change_stats)
    if not JSON_OUTPUT:
        console.print(f"\n[blue]Pushing changes to {hub_path}...[/blue]")
    
    upload_start = time.time()
    try:
        updated_mapping = upload_changes_recursive(
            local_dir, hub_folder_id, path_to_id, old_state, current_state
        )
        upload_duration = time.time() - upload_start
        
        # Update sync state
        sync_state["path_to_id"] = updated_mapping
        sync_state["initial_state"] = current_state
        sync_state["last_push"] = datetime.now().isoformat()
        save_sync_state(local_dir, sync_state)
        
        agent_log("Push completed successfully", "success", {
            "upload_duration": upload_duration,
            "total_duration": time.time() - start_time,
            **change_stats
        })
        
        console.print(f"\n[green]✓ Successfully pushed {change_stats['total_changes']} changes![/green]")
        console.print("[dim]CRDT auto-resolution handled any conflicts.[/dim]")
        
        operation_summary("push", {
            "result": "success",
            "duration": time.time() - start_time,
            "upload_duration": upload_duration,
            "scan_duration": scan_duration,
            "errors": 0,
            **change_stats
        })
        
    except Exception as e:
        error_duration = time.time() - start_time
        agent_log("Push failed", "error", {
            "error": str(e),
            "duration": error_duration,
            **change_stats
        })
        
        console.print(f"[red]Error during push: {e}[/red]")
        
        operation_summary("push", {
            "result": "error",
            "duration": error_duration,
            "error": str(e),
            "errors": 1,
            **change_stats
        })
        
        sys.exit(1)


@cli.command()
@click.argument("local_path")
def sync_status(local_path: str):
    """Show sync status for a pulled directory."""
    local_dir = Path(local_path)
    
    if not local_dir.exists():
        console.print(f"[red]Directory does not exist: {local_path}[/red]")
        sys.exit(1)
    
    sync_state = load_sync_state(local_dir)
    if not sync_state:
        console.print(f"[red]No sync state found in {local_path}[/red]")
        console.print("This directory was not pulled from Context Hub.")
        return
    
    # Show sync info
    console.print(f"[bold]Sync Status: {local_path}[/bold]")
    console.print(f"Hub Path: [blue]{sync_state['hub_path']}[/blue]")
    console.print(f"User: [cyan]{sync_state['user']}[/cyan]")
    console.print(f"Pulled: [dim]{sync_state['pulled_at']}[/dim]")
    
    if "last_push" in sync_state:
        console.print(f"Last Push: [dim]{sync_state['last_push']}[/dim]")
    
    # Check for changes
    old_state = sync_state["initial_state"]
    current_state = scan_local_tree(local_dir)
    
    added = set(current_state.keys()) - set(old_state.keys())
    removed = set(old_state.keys()) - set(current_state.keys())
    modified = []
    
    for path in set(old_state.keys()) & set(current_state.keys()):
        old_item = old_state[path]
        new_item = current_state[path]
        
        if old_item["type"] == "file" and new_item["type"] == "file":
            if old_item.get("hash") != new_item.get("hash"):
                modified.append(path)
    
    total_changes = len(added) + len(removed) + len(modified)
    
    if total_changes == 0:
        console.print("\n[green]✓ No local changes[/green]")
    else:
        console.print(f"\n[yellow]⚠ {total_changes} local changes pending[/yellow]")
        console.print(f"Run: [cyan]ch push {local_path}[/cyan]")


@cli.command()
@click.argument("local_path")
@click.option("--watch", "-w", is_flag=True, help="Watch for changes and auto-push")
@click.option("--interval", "-i", default=5, help="Watch interval in seconds")
def auto_sync(local_path: str, watch: bool, interval: int):
    """Auto-sync local directory with Context Hub (experimental)."""
    local_dir = Path(local_path)
    
    if not local_dir.exists():
        console.print(f"[red]Directory does not exist: {local_path}[/red]")
        sys.exit(1)
    
    sync_state = load_sync_state(local_dir)
    if not sync_state:
        console.print(f"[red]No sync state found in {local_path}[/red]")
        sys.exit(1)
    
    console.print(f"[blue]Auto-sync enabled for {local_path}[/blue]")
    console.print(f"Watching for changes every {interval}s...")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    
    try:
        last_state = sync_state["initial_state"]
        
        while True:
            time.sleep(interval)
            current_state = scan_local_tree(local_dir)
            
            # Check for changes
            if current_state != last_state:
                console.print(f"[yellow]Changes detected at {datetime.now().strftime('%H:%M:%S')}[/yellow]")
                
                # Auto-push changes
                try:
                    updated_mapping = upload_changes_recursive(
                        local_dir, sync_state["hub_folder_id"], 
                        sync_state["path_to_id"], last_state, current_state
                    )
                    
                    # Update sync state
                    sync_state["path_to_id"] = updated_mapping
                    sync_state["initial_state"] = current_state
                    sync_state["last_push"] = datetime.now().isoformat()
                    save_sync_state(local_dir, sync_state)
                    
                    change_count = len(set(current_state.keys()) - set(last_state.keys())) + \
                                 len(set(last_state.keys()) - set(current_state.keys())) + \
                                 len([p for p in set(last_state.keys()) & set(current_state.keys()) 
                                      if last_state[p].get("hash") != current_state[p].get("hash")])
                    
                    console.print(f"[green]✓ Auto-pushed {change_count} changes[/green]")
                    last_state = current_state
                    
                except Exception as e:
                    console.print(f"[red]Auto-push failed: {e}[/red]")
                    
    except KeyboardInterrupt:
        console.print("\n[dim]Auto-sync stopped[/dim]")


# ============================================================================
# LLM-OPTIMIZED COMMANDS
# ============================================================================

@cli.group()
def llm():
    """LLM-optimized commands with structured output."""
    pass


@llm.command()
@click.argument("path")
@click.option("--lines", "-l", help="Specific line range (e.g., 1-10, 5, 10-)")
def read(path: str, lines: str):
    """Read document with line numbers optimized for LLM processing."""
    try:
        doc_id = resolve_path(path)
        
        # Get numbered content
        doc = api_request("GET", f"/docs/{doc_id}", params={"format": "numbered"})
        
        if doc["doc_type"] == "Folder":
            return llm_response(False, "llm_read", error="Path is a folder, not a file")
        
        content = doc.get("numbered_content", "")
        line_count = doc.get("line_count", 0)
        
        # Parse line range if specified
        if lines:
            content_lines = content.splitlines()
            try:
                if '-' in lines:
                    if lines.endswith('-'):
                        # "10-" means from line 10 to end
                        start = int(lines[:-1]) - 1
                        filtered_lines = content_lines[start:]
                    elif lines.startswith('-'):
                        # "-10" means first 10 lines
                        end = int(lines[1:])
                        filtered_lines = content_lines[:end]
                    else:
                        # "5-10" means lines 5 to 10
                        start, end = map(int, lines.split('-'))
                        filtered_lines = content_lines[start-1:end]
                else:
                    # Single line number
                    line_num = int(lines) - 1
                    filtered_lines = [content_lines[line_num]] if 0 <= line_num < len(content_lines) else []
                
                content = '\n'.join(filtered_lines)
            except (ValueError, IndexError):
                return llm_response(False, "llm_read", error=f"Invalid line range: {lines}")
        
        data = {
            "path": path,
            "doc_id": doc_id,
            "content": content,
            "line_count": line_count,
            "doc_type": doc["doc_type"],
            "name": doc.get("name", ""),
            "size_bytes": len(doc.get("content", "").encode('utf-8'))
        }
        
        if lines:
            data["line_range"] = lines
        
        return llm_response(True, "llm_read", data)
        
    except Exception as e:
        return llm_response(False, "llm_read", error=str(e))


@llm.command()
@click.argument("path")
@click.argument("content")
@click.option("--patch-mode", is_flag=True, help="Treat content as unified diff patch")
def write(path: str, content: str, patch_mode: bool):
    """Write or patch document content optimized for LLM."""
    try:
        doc_id = resolve_path(path)
        
        if patch_mode:
            # Apply as patch
            result = api_request("PATCH", f"/docs/{doc_id}", json={"patch": content})
            operation = "llm_patch"
        else:
            # Full content replacement
            doc_info = api_request("GET", f"/docs/{doc_id}")
            name = doc_info.get("name", "")
            
            result = api_request("PUT", f"/docs/{doc_id}", json={
                "name": name,
                "content": content
            })
            operation = "llm_write"
        
        # Get updated info
        updated_doc = api_request("GET", f"/docs/{doc_id}")
        new_content = updated_doc.get("content", "")
        
        data = {
            "path": path,
            "doc_id": doc_id,
            "content_length": len(new_content),
            "line_count": len(new_content.splitlines()),
            "operation_type": "patch" if patch_mode else "write"
        }
        
        return llm_response(True, operation, data)
        
    except Exception as e:
        operation = "llm_patch" if patch_mode else "llm_write"
        return llm_response(False, operation, error=str(e))


@llm.command()
@click.argument("query")
@click.option("--limit", default=50, help="Maximum results")
@click.option("--include-content", is_flag=True, help="Include file content in results")
def find(query: str, limit: int, include_content: bool):
    """Search with structured LLM-friendly output."""
    try:
        params = {"q": query, "limit": limit}
        results = api_request("GET", "/search", params=params)
        
        processed_results = []
        for result in results:
            processed_result = {
                "name": result.get("name", ""),
                "snippet": result.get("snippet", ""),
                "score": result.get("score", 0),
                "path": result.get("path", ""),
                "doc_type": result.get("doc_type", "")
            }
            
            if include_content and result.get("id"):
                try:
                    doc = api_request("GET", f"/docs/{result['id']}")
                    processed_result["full_content"] = doc.get("content", "")
                    processed_result["line_count"] = len(doc.get("content", "").splitlines())
                except:
                    processed_result["full_content"] = ""
                    processed_result["line_count"] = 0
            
            processed_results.append(processed_result)
        
        data = {
            "query": query,
            "total_results": len(processed_results),
            "results": processed_results,
            "include_content": include_content
        }
        
        return llm_response(True, "llm_find", data)
        
    except Exception as e:
        return llm_response(False, "llm_find", error=str(e))


@llm.command()
@click.argument("path", default="")
def inspect(path: str):
    """Get detailed structured information about path for LLM analysis."""
    try:
        doc_id = resolve_path(path)
        doc_info = api_request("GET", f"/docs/{doc_id}")
        
        data = {
            "id": doc_id,
            "name": doc_info.get("name", ""),
            "doc_type": doc_info.get("doc_type", ""),
            "path": path or "/",
        }
        
        if doc_info["doc_type"] == "Folder":
            # Get folder contents
            items = api_request("GET", f"/folders/{doc_id}")
            data["is_folder"] = True
            data["item_count"] = len(items)
            data["items"] = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "type": item["doc_type"].lower(),
                    "doc_type": item["doc_type"]
                }
                for item in items
            ]
        else:
            # Get file content info
            content = doc_info.get("content", "")
            data["is_folder"] = False
            data["content"] = content
            data["size_bytes"] = len(content.encode('utf-8'))
            data["line_count"] = len(content.splitlines())
            data["is_empty"] = len(content.strip()) == 0
        
        return llm_response(True, "llm_inspect", data)
        
    except Exception as e:
        return llm_response(False, "llm_inspect", error=str(e))


@llm.command()
def schema():
    """Output JSON schema for LLM command responses."""
    schema_data = {
        "response_format": {
            "success": "boolean - operation success status",
            "operation": "string - operation type identifier", 
            "timestamp": "string - ISO timestamp",
            "data": "object - operation-specific data",
            "error": "string|null - error message if failed"
        },
        "operations": {
            "llm_read": {
                "data": {
                    "path": "string - document path",
                    "doc_id": "string - document UUID",
                    "content": "string - file content with line numbers",
                    "line_count": "number - total lines",
                    "doc_type": "string - document type",
                    "name": "string - document name",
                    "size_bytes": "number - content size",
                    "line_range": "string - optional line range"
                }
            },
            "llm_write": {
                "data": {
                    "path": "string - document path",
                    "doc_id": "string - document UUID", 
                    "content_length": "number - new content length",
                    "line_count": "number - new line count",
                    "operation_type": "string - 'write' or 'patch'"
                }
            },
            "llm_find": {
                "data": {
                    "query": "string - search query",
                    "total_results": "number - result count",
                    "results": "array - search results with name, snippet, score",
                    "include_content": "boolean - whether full content included"
                }
            },
            "llm_inspect": {
                "data": {
                    "id": "string - document/folder UUID",
                    "name": "string - item name",
                    "doc_type": "string - type",
                    "path": "string - full path",
                    "is_folder": "boolean - whether item is folder",
                    "content": "string - file content (if file)",
                    "items": "array - folder contents (if folder)"
                }
            }
        },
        "examples": {
            "successful_read": {
                "success": True,
                "operation": "llm_read",
                "data": {
                    "path": "/project/main.py",
                    "content": "1: def main():\n2:     print('Hello')\n3:     return 0",
                    "line_count": 3
                }
            },
            "error_response": {
                "success": False,
                "operation": "llm_read", 
                "error": "File not found: /invalid/path"
            }
        }
    }
    
    print(json.dumps(schema_data, indent=2))


if __name__ == "__main__":
    cli() 