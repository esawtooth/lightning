#!/usr/bin/env python3
"""
Script to check the latest GitHub Action run status and fetch logs if failed.
Requires GitHub CLI (gh) to be installed and authenticated.
"""

import json
import subprocess
import sys
from datetime import datetime


def run_command(cmd, capture_output=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=capture_output, 
            text=True, 
            check=True
        )
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        if capture_output:
            print(f"Error running command: {cmd}")
            print(f"Error: {e.stderr}")
        raise


def get_latest_run():
    """Get the latest GitHub Action run."""
    print("🔍 Fetching latest GitHub Action run...")
    
    # Get the latest run with databaseId which is needed for API calls
    cmd = "gh run list --limit 1 --json status,conclusion,workflowName,number,createdAt,url,databaseId"
    output = run_command(cmd)
    
    if not output:
        print("❌ No GitHub Action runs found")
        return None
    
    runs = json.loads(output)
    if not runs:
        print("❌ No GitHub Action runs found")
        return None
    
    return runs[0]


def format_datetime(iso_string):
    """Format ISO datetime string to readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except:
        return iso_string


def get_failed_job_logs(run_info):
    """Get logs for failed jobs in a run."""
    run_number = run_info.get('number')
    run_id = run_info.get('databaseId')
    
    print(f"📋 Fetching job details for run #{run_number} (ID: {run_id})...")
    
    # Try using the databaseId first, then fall back to run number
    for identifier in [run_id, run_number]:
        if not identifier:
            continue
            
        try:
            # Get jobs for the run
            cmd = f"gh run view {identifier} --json jobs"
            output = run_command(cmd)
            break
        except subprocess.CalledProcessError:
            print(f"⚠️  Could not fetch run details using identifier: {identifier}")
            continue
    else:
        print("❌ Could not fetch job details with any identifier")
        # Try alternative approach - get logs directly
        print("🔄 Trying alternative log fetching method...")
        try:
            if run_id:
                log_cmd = f"gh run view {run_id} --log-failed"
            else:
                log_cmd = f"gh run view {run_number} --log-failed"
            run_command(log_cmd, capture_output=False)
        except subprocess.CalledProcessError:
            print("❌ Could not fetch logs using any method")
        return
    
    if not output:
        print("❌ Could not fetch job details")
        return
    
    data = json.loads(output)
    jobs = data.get('jobs', [])
    
    failed_jobs = [job for job in jobs if job.get('conclusion') == 'failure']
    
    if not failed_jobs:
        print("🤔 No failed jobs found (run may have failed for other reasons)")
        # Still try to get general logs
        print("🔄 Trying to get general failure logs...")
        try:
            identifier = run_id if run_id else run_number
            log_cmd = f"gh run view {identifier} --log-failed"
            run_command(log_cmd, capture_output=False)
        except subprocess.CalledProcessError:
            print("❌ Could not fetch general logs")
        return
    
    print(f"🔍 Found {len(failed_jobs)} failed job(s)")
    
    for job in failed_jobs:
        job_name = job.get('name', 'Unknown Job')
        job_id = job.get('databaseId')
        
        print(f"\n{'='*60}")
        print(f"❌ FAILED JOB: {job_name}")
        print(f"{'='*60}")
        
        if job_id:
            print(f"📝 Fetching logs for job ID: {job_id}")
            try:
                # Get logs for the specific job
                log_cmd = f"gh api repos/:owner/:repo/actions/jobs/{job_id}/logs"
                logs = run_command(log_cmd)
                
                if logs:
                    print("\n📄 JOB LOGS:")
                    print("-" * 40)
                    # Print last 100 lines to avoid overwhelming output
                    log_lines = logs.split('\n')
                    if len(log_lines) > 200:
                        print(f"... (showing last 100 lines of {len(log_lines)} total lines)")
                        logs = '\n'.join(log_lines[-100:])
                    print(logs)
                else:
                    print("⚠️  No logs available for this job")
                    
            except subprocess.CalledProcessError:
                print(f"⚠️  Could not fetch logs for job: {job_name}")
                print("Trying alternative method...")
                
                # Fallback: get all run logs
                try:
                    identifier = run_id if run_id else run_number
                    log_cmd = f"gh run view {identifier} --log-failed"
                    run_command(log_cmd, capture_output=False)
                except subprocess.CalledProcessError:
                    print("❌ Could not fetch logs using fallback method")


def main():
    """Main function."""
    print("🚀 GitHub Actions Status Checker")
    print("=" * 50)
    
    # Check if gh CLI is available
    try:
        run_command("gh --version")
    except subprocess.CalledProcessError:
        print("❌ GitHub CLI (gh) is not installed or not in PATH")
        print("Please install it from: https://cli.github.com/")
        sys.exit(1)
    
    # Check if we're in a git repository
    try:
        run_command("git rev-parse --git-dir")
    except subprocess.CalledProcessError:
        print("❌ Not in a git repository")
        sys.exit(1)
    
    # Get latest run
    latest_run = get_latest_run()
    if not latest_run:
        sys.exit(1)
    
    # Display run information
    workflow_name = latest_run.get('workflowName', 'Unknown Workflow')
    run_number = latest_run.get('number')
    run_id = latest_run.get('databaseId')
    status = latest_run.get('status', 'unknown')
    conclusion = latest_run.get('conclusion')
    created_at = latest_run.get('createdAt', '')
    url = latest_run.get('url', '')
    
    print(f"\n📊 LATEST RUN STATUS")
    print("-" * 30)
    print(f"Workflow: {workflow_name}")
    print(f"Run #: {run_number}")
    print(f"Run ID: {run_id}")
    print(f"Status: {status}")
    print(f"Conclusion: {conclusion or 'In Progress'}")
    print(f"Created: {format_datetime(created_at)}")
    print(f"URL: {url}")
    
    # Determine status emoji and message
    if status == 'completed':
        if conclusion == 'success':
            print("\n✅ WORKFLOW PASSED!")
        elif conclusion == 'failure':
            print("\n❌ WORKFLOW FAILED!")
            print("\n🔍 Fetching failure logs...")
            get_failed_job_logs(latest_run)
        elif conclusion == 'cancelled':
            print("\n⏹️  WORKFLOW CANCELLED")
        else:
            print(f"\n⚠️  WORKFLOW COMPLETED WITH STATUS: {conclusion}")
    elif status == 'in_progress':
        print("\n🔄 WORKFLOW IN PROGRESS")
    elif status == 'queued':
        print("\n⏳ WORKFLOW QUEUED")
    else:
        print(f"\n❓ UNKNOWN STATUS: {status}")
    
    print("\n" + "=" * 50)
    print("💡 Tip: Use 'gh run list' to see more runs")
    print("💡 Tip: Use 'gh run view <run-number>' for detailed view")


if __name__ == "__main__":
    main()
