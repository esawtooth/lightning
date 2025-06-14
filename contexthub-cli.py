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
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich import print as rprint


# Global console for rich output
console = Console()

# Configuration
CONFIG_FILE = Path.home() / ".context-hub" / "config.json"
SYNC_STATE_FILE = ".ch-sync-state.json"  # Track sync state in each pulled directory
DEFAULT_CONFIG = {
    "url": "http://localhost:3000",
    "user": None,
    "agent": None,
    "current_workspace": None
}


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
    """Make API request with automatic user/agent headers."""
    config = load_config()
    url = f"{config['url']}{path}"
    
    headers = kwargs.pop("headers", {})
    headers["X-User-Id"] = get_current_user()
    if config.get("agent"):
        headers["X-Agent-Id"] = config["agent"]
    
    try:
        resp = requests.request(method, url, headers=headers, **kwargs)
        if not resp.ok:
            console.print(f"[red]Error {resp.status_code}: {resp.text}[/red]")
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


def download_folder_recursive(folder_id: str, local_path: Path, progress=None, task_id=None) -> Dict[str, str]:
    """Download folder structure recursively. Returns mapping of local paths to hub IDs."""
    local_path.mkdir(parents=True, exist_ok=True)
    path_to_id = {}
    
    # Get folder contents
    items = api_request("GET", f"/folders/{folder_id}")
    
    for item in items:
        item_path = local_path / item["name"]
        rel_path = str(item_path.relative_to(local_path.parent))
        path_to_id[rel_path] = item["id"]
        
        if progress and task_id:
            progress.update(task_id, description=f"Downloading {item['name']}")
        
        if item["doc_type"] == "Folder":
            # Skip index guides for cleaner local structure
            if item["name"] == "_index.guide":
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
                continue
                
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
@click.pass_context
def cli(ctx):
    """Context Hub - Git-like collaboration for AI agents and humans."""
    if ctx.invoked_subcommand is None:
        # Show status when no command given (like git)
        ctx.invoke(status)


@cli.command()
def status():
    """Show the working directory status."""
    config = load_config()
    current_workspace = config.get("current_workspace") or "/"
    
    console.print(f"[bold]Context Hub Status[/bold]")
    console.print(f"User: [cyan]{get_current_user()}[/cyan]")
    console.print(f"Workspace: [blue]{current_workspace}[/blue]")
    
    # Get current folder info
    folder_id = resolve_path("")
    folder_info = api_request("GET", f"/docs/{folder_id}")
    items = api_request("GET", f"/folders/{folder_id}")
    
    if not items:
        console.print("\n[dim]Empty workspace[/dim]")
        return
    
    # Show recent activity
    console.print(f"\n[bold]Contents ({len(items)} items):[/bold]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Type", width=8)
    table.add_column("Name", style="cyan")
    table.add_column("Size", justify="right", width=8)
    table.add_column("Modified", width=12)
    
    for item in items:
        doc_type = item["doc_type"]
        if doc_type == "Folder":
            type_str = "📁 dir"
            size_str = ""
        elif doc_type == "IndexGuide":
            type_str = "📋 guide"
            size_str = ""
        else:
            type_str = "📄 file"
            # Get file details for size
            try:
                doc = api_request("GET", f"/docs/{item['id']}")
                size_str = format_size(doc.get("content", ""))
            except:
                size_str = ""
        
        table.add_row(type_str, item["name"], size_str, format_time_ago(""))
    
    console.print(table)
    
    # Show shared folders in root
    if current_workspace == "/":
        shared_count = sum(1 for item in items if item["name"].endswith(" (shared)"))
        if shared_count > 0:
            console.print(f"\n[yellow]📤 {shared_count} shared folders available[/yellow]")


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
def cat(path: str):
    """Show content of a document."""
    doc_id = resolve_path(path)
    doc = api_request("GET", f"/docs/{doc_id}")
    
    if doc["doc_type"] == "Folder":
        console.print(f"[red]Cannot cat a folder. Use 'ch ls {path}' instead.[/red]")
        sys.exit(1)
    
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
    
    console.print(table)


@cli.command()
@click.argument("hub_path")
@click.argument("local_path")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing local directory")
def pull(hub_path: str, local_path: str, force: bool):
    """Pull Context Hub folder to local filesystem for editing."""
    local_dir = Path(local_path)
    
    # Check if local directory exists
    if local_dir.exists() and not force:
        if list(local_dir.iterdir()):  # Not empty
            console.print(f"[red]Directory {local_path} already exists and is not empty.[/red]")
            console.print("Use --force to overwrite or choose a different path.")
            sys.exit(1)
    
    # Resolve hub path to ID
    hub_folder_id = resolve_path(hub_path)
    hub_doc = api_request("GET", f"/docs/{hub_folder_id}")
    
    if hub_doc["doc_type"] != "Folder":
        console.print(f"[red]Path is not a folder: {hub_path}[/red]")
        sys.exit(1)
    
    console.print(f"[blue]Pulling '{hub_doc['name']}' to {local_path}...[/blue]")
    
    # Create/clear local directory
    if local_dir.exists() and force:
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    
    # Download with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Downloading files...", total=None)
        path_to_id = download_folder_recursive(hub_folder_id, local_dir, progress, task)
        progress.update(task, description="Download complete!")
    
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
    
    # Show summary
    file_count = len([s for s in initial_state.values() if s["type"] == "file"])
    folder_count = len([s for s in initial_state.values() if s["type"] == "folder"])
    
    console.print(f"\n[green]✓ Successfully pulled to {local_path}[/green]")
    console.print(f"Files: {file_count}, Folders: {folder_count}")
    console.print(f"\n[dim]Work locally with normal tools, then run:[/dim]")
    console.print(f"[cyan]ch push {local_path} {hub_path}[/cyan]")


@cli.command()
@click.argument("local_path")
@click.argument("hub_path", required=False)
@click.option("--dry-run", "-n", is_flag=True, help="Show what would be changed without uploading")
@click.option("--no-confirm", is_flag=True, help="Skip confirmation prompt (for automated workflows)")
def push(local_path: str, hub_path: Optional[str], dry_run: bool, no_confirm: bool):
    """Push local changes back to Context Hub with auto conflict resolution."""
    local_dir = Path(local_path)
    
    if not local_dir.exists():
        console.print(f"[red]Local directory does not exist: {local_path}[/red]")
        sys.exit(1)
    
    # Load sync state
    sync_state = load_sync_state(local_dir)
    if not sync_state:
        console.print(f"[red]No sync state found in {local_path}[/red]")
        console.print("This directory was not pulled from Context Hub.")
        console.print("Use 'ch pull <hub_path> <local_path>' first.")
        sys.exit(1)
    
    # Use hub path from sync state if not provided
    if not hub_path:
        hub_path = sync_state["hub_path"]
        console.print(f"[dim]Using hub path from sync state: {hub_path}[/dim]")
    
    hub_folder_id = sync_state["hub_folder_id"]
    old_state = sync_state["initial_state"]
    path_to_id = sync_state["path_to_id"]
    
    # Scan current local state
    console.print("[blue]Scanning local changes...[/blue]")
    current_state = scan_local_tree(local_dir)
    
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
    
    # Show summary
    total_changes = len(added) + len(removed) + len(modified)
    if total_changes == 0:
        console.print("[green]No changes detected.[/green]")
        return
    
    console.print(f"\n[bold]Changes detected:[/bold]")
    if added:
        console.print(f"[green]Added ({len(added)}):[/green]")
        for path in sorted(added):
            item_type = current_state[path]["type"]
            console.print(f"  + {path} ({item_type})")
    
    if removed:
        console.print(f"[red]Removed ({len(removed)}):[/red]")
        for path in sorted(removed):
            item_type = old_state[path]["type"]
            console.print(f"  - {path} ({item_type})")
    
    if modified:
        console.print(f"[blue]Modified ({len(modified)}):[/blue]")
        for path in sorted(modified):
            console.print(f"  ~ {path}")
    
    if dry_run:
        console.print(f"\n[dim]Dry run complete. Use 'ch push {local_path}' to apply changes.[/dim]")
        return
    
    # Confirm push (agent-friendly: default Yes, or skip entirely)
    if not no_confirm:
        if not click.confirm(f"\nPush {total_changes} changes to Context Hub?", default=True):
            console.print("Push cancelled.")
            return
    else:
        console.print(f"\n[dim]Auto-pushing {total_changes} changes (--no-confirm)[/dim]")
    
    # Upload changes
    console.print(f"\n[blue]Pushing changes to {hub_path}...[/blue]")
    
    try:
        updated_mapping = upload_changes_recursive(
            local_dir, hub_folder_id, path_to_id, old_state, current_state
        )
        
        # Update sync state
        sync_state["path_to_id"] = updated_mapping
        sync_state["initial_state"] = current_state
        sync_state["last_push"] = datetime.now().isoformat()
        save_sync_state(local_dir, sync_state)
        
        console.print(f"\n[green]✓ Successfully pushed {total_changes} changes![/green]")
        console.print("[dim]CRDT auto-resolution handled any conflicts.[/dim]")
        
    except Exception as e:
        console.print(f"[red]Error during push: {e}[/red]")
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


if __name__ == "__main__":
    cli() 