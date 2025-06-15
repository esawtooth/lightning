"""
Cleanup script to remove redundant Azure Functions after Vextir OS migration
These functions have been replaced by drivers and are no longer needed
"""

import os
import shutil
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Functions that have been migrated to drivers and can be removed
REDUNDANT_FUNCTIONS = [
    "ContextHubManager",      # Replaced by ContextHubDriver
    "ContextSynthesizer",     # Replaced by ContextHubDriver
    "ChatResponder",          # Replaced by ChatAgentDriver
    "UserAuth",               # Replaced by AuthenticationDriver
    "EmailCalendarConnector", # Replaced by EmailConnectorDriver + CalendarConnectorDriver
    "UserMessenger",          # Replaced by UserMessengerDriver
    "InstructionProcessor",   # Replaced by InstructionEngineDriver
    "InstructionManager",     # Replaced by InstructionEngineDriver
    "TaskMonitor",            # Replaced by TaskMonitorDriver
    "Scheduler",              # Replaced by SchedulerDriver
    "ScheduleWorker",         # Replaced by SchedulerDriver
    "WorkerTaskRunner",       # Functionality moved to drivers
    "VoiceCallRunner",        # Can be migrated to driver later if needed
]

# Functions to keep (essential for system operation)
KEEP_FUNCTIONS = [
    "UniversalEventProcessor",  # Core processor - enhanced, not replaced
    "Health",                   # Health check endpoint
    "PutEvent",                # Event ingestion endpoint
    "RegisterRepo",            # Repository registration
]

def backup_function(function_name: str, backup_dir: str = "azure-function-backup"):
    """Backup a function before removal"""
    source_path = Path(f"azure-function/{function_name}")
    backup_path = Path(f"{backup_dir}/{function_name}")
    
    if source_path.exists():
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, backup_path, dirs_exist_ok=True)
        logger.info(f"Backed up {function_name} to {backup_path}")
        return True
    return False

def remove_function(function_name: str):
    """Remove a redundant Azure Function"""
    function_path = Path(f"azure-function/{function_name}")
    
    if function_path.exists():
        shutil.rmtree(function_path)
        logger.info(f"Removed redundant function: {function_name}")
        return True
    else:
        logger.warning(f"Function {function_name} not found, skipping")
        return False

def update_host_json():
    """Update host.json to remove references to deleted functions"""
    host_json_path = Path("azure-function/host.json")
    
    if host_json_path.exists():
        # Read current host.json
        with open(host_json_path, 'r') as f:
            content = f.read()
        
        # Create backup
        backup_path = Path("azure-function-backup/host.json.backup")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with open(backup_path, 'w') as f:
            f.write(content)
        
        logger.info("Backed up host.json")
        logger.info("host.json may need manual review for function-specific configurations")

def cleanup_redundant_functions(create_backup: bool = True):
    """Main cleanup function"""
    logger.info("Starting cleanup of redundant Azure Functions...")
    
    if create_backup:
        logger.info("Creating backups before removal...")
    
    removed_count = 0
    backed_up_count = 0
    
    for function_name in REDUNDANT_FUNCTIONS:
        if create_backup:
            if backup_function(function_name):
                backed_up_count += 1
        
        if remove_function(function_name):
            removed_count += 1
    
    # Update host.json
    if create_backup:
        update_host_json()
    
    logger.info(f"\nCleanup Summary:")
    logger.info(f"Functions backed up: {backed_up_count}")
    logger.info(f"Functions removed: {removed_count}")
    logger.info(f"Functions kept: {len(KEEP_FUNCTIONS)}")
    
    logger.info(f"\nRemaining functions:")
    for func in KEEP_FUNCTIONS:
        func_path = Path(f"azure-function/{func}")
        status = "✅" if func_path.exists() else "❌"
        logger.info(f"  {status} {func}")
    
    logger.info(f"\nRemoved functions (now handled by drivers):")
    for func in REDUNDANT_FUNCTIONS:
        logger.info(f"  🗑️  {func}")
    
    if create_backup:
        logger.info(f"\n📁 Backups stored in: azure-function-backup/")
        logger.info("You can restore any function from backup if needed")
    
    logger.info("\n✅ Cleanup complete! The system now runs entirely on Vextir OS drivers.")

def list_current_functions():
    """List all current Azure Functions"""
    azure_function_dir = Path("azure-function")
    
    if not azure_function_dir.exists():
        logger.error("azure-function directory not found")
        return
    
    logger.info("Current Azure Functions:")
    for item in azure_function_dir.iterdir():
        if item.is_dir() and not item.name.startswith('.') and not item.name.startswith('__'):
            status = "🔄 REDUNDANT" if item.name in REDUNDANT_FUNCTIONS else "✅ KEEP"
            logger.info(f"  {status} {item.name}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        list_current_functions()
    elif len(sys.argv) > 1 and sys.argv[1] == "--no-backup":
        cleanup_redundant_functions(create_backup=False)
    elif len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Usage:")
        print("  python cleanup_redundant_functions.py           # Cleanup with backup")
        print("  python cleanup_redundant_functions.py --list    # List current functions")
        print("  python cleanup_redundant_functions.py --no-backup # Cleanup without backup")
        print("  python cleanup_redundant_functions.py --help    # Show this help")
    else:
        cleanup_redundant_functions(create_backup=True)
