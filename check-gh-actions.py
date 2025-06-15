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
            check=True,
        )
        return result.stdout.strip() if capture_output else None
    except subprocess.CalledProcessError as e:
        if capture_output:
            print(f"Error running command: {cmd}")
            print(f"Error: {e.stderr}")
        raise


def get_latest_run():
    """Get the latest GitHub Action run."""
    print("\U0001F50D Fetching latest GitHub Action run...")

    cmd = "gh run list --limit 1 --json status,conclusion,workflowName,number,createdAt,url,databaseId"
    output = run_command(cmd)
    if not output:
        print("\u274C No GitHub Action runs found")
        return None

    runs = json.loads(output)
    if not runs:
        print("\u274C No GitHub Action runs found")
        return None

    return runs[0]


def format_datetime(iso_string):
    """Format ISO datetime string to readable format."""
    try:
        dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
    except Exception:
        return iso_string


def get_failed_job_logs(run_info):
    """Get logs for failed jobs in a run."""
    run_number = run_info.get('number')
    run_id = run_info.get('databaseId')

    print(f"\U0001F4CB Fetching job details for run #{run_number} (ID: {run_id})...")
    output = None
    for identifier in [run_id, run_number]:
        if not identifier:
            continue
        try:
            cmd = f"gh run view {identifier} --json jobs"
            output = run_command(cmd)
            break
        except subprocess.CalledProcessError:
            print(f"\u26A0\uFE0F  Could not fetch run details using identifier: {identifier}")
            continue
    else:
        print("\u274C Could not fetch job details with any identifier")
        print("\U0001F501 Trying alternative log fetching method...")
        try:
            log_cmd = f"gh run view {run_id or run_number} --log-failed"
            run_command(log_cmd, capture_output=False)
        except subprocess.CalledProcessError:
            print("\u274C Could not fetch logs using any method")
        return

    if not output:
        print("\u274C Could not fetch job details")
        return

    data = json.loads(output)
    jobs = data.get('jobs', [])

    failed_jobs = [job for job in jobs if job.get('conclusion') == 'failure']
    if not failed_jobs:
        print("\U0001F914 No failed jobs found (run may have failed for other reasons)")
        print("\U0001F501 Trying to get general failure logs...")
        try:
            log_cmd = f"gh run view {run_id or run_number} --log-failed"
            run_command(log_cmd, capture_output=False)
        except subprocess.CalledProcessError:
            print("\u274C Could not fetch general logs")
        return

    print(f"\U0001F50D Found {len(failed_jobs)} failed job(s)")

    for job in failed_jobs:
        job_name = job.get('name', 'Unknown Job')
        job_id = job.get('databaseId')

        print(f"\n{'='*60}")
        print(f"\u274C FAILED JOB: {job_name}")
        print(f"{'='*60}")
        if job_id:
            print(f"\U0001F4DD Fetching logs for job ID: {job_id}")
            try:
                log_cmd = f"gh api repos/:owner/:repo/actions/jobs/{job_id}/logs"
                logs = run_command(log_cmd)
                if logs:
                    print("\n\U0001F4C4 JOB LOGS:")
                    print("-" * 40)
                    lines = logs.split('\n')
                    if len(lines) > 200:
                        print(f"... (showing last 100 lines of {len(lines)} total lines)")
                        logs = '\n'.join(lines[-100:])
                    print(logs)
                else:
                    print("\u26A0\uFE0F  No logs available for this job")
            except subprocess.CalledProcessError:
                print(f"\u26A0\uFE0F  Could not fetch logs for job: {job_name}")
                print("Trying alternative method...")
                try:
                    log_cmd = f"gh run view {run_id or run_number} --log-failed"
                    run_command(log_cmd, capture_output=False)
                except subprocess.CalledProcessError:
                    print("\u274C Could not fetch logs using fallback method")


def main():
    print("\U0001F680 GitHub Actions Status Checker")
    print("=" * 50)
    try:
        run_command("gh --version")
    except subprocess.CalledProcessError:
        print("\u274C GitHub CLI (gh) is not installed or not in PATH")
        print("Please install it from: https://cli.github.com/")
        sys.exit(1)

    try:
        run_command("git rev-parse --git-dir")
    except subprocess.CalledProcessError:
        print("\u274C Not in a git repository")
        sys.exit(1)

    latest_run = get_latest_run()
    if not latest_run:
        sys.exit(1)

    workflow_name = latest_run.get('workflowName', 'Unknown Workflow')
    run_number = latest_run.get('number')
    run_id = latest_run.get('databaseId')
    status = latest_run.get('status', 'unknown')
    conclusion = latest_run.get('conclusion')
    created_at = latest_run.get('createdAt', '')
    url = latest_run.get('url', '')

    print(f"\n\U0001F4CA LATEST RUN STATUS")
    print("-" * 30)
    print(f"Workflow: {workflow_name}")
    print(f"Run #: {run_number}")
    print(f"Run ID: {run_id}")
    print(f"Status: {status}")
    print(f"Conclusion: {conclusion or 'In Progress'}")
    print(f"Created: {format_datetime(created_at)}")
    print(f"URL: {url}")

    if status == 'completed':
        if conclusion == 'success':
            print("\n\u2705 WORKFLOW PASSED!")
        elif conclusion == 'failure':
            print("\n\u274C WORKFLOW FAILED!")
            print("\n\U0001F50D Fetching failure logs...")
            get_failed_job_logs(latest_run)
        elif conclusion == 'cancelled':
            print("\n\u23F9\uFE0F  WORKFLOW CANCELLED")
        else:
            print(f"\n\u26A0\uFE0F  WORKFLOW COMPLETED WITH STATUS: {conclusion}")
    elif status == 'in_progress':
        print("\n\U0001F501 WORKFLOW IN PROGRESS")
    elif status == 'queued':
        print("\n\u23F3 WORKFLOW QUEUED")
    else:
        print(f"\n\u2753 UNKNOWN STATUS: {status}")

    print("\n" + "=" * 50)
    print("\U0001F4A1 Tip: Use 'gh run list' to see more runs")
    print("\U0001F4A1 Tip: Use 'gh run view <run-number>' for detailed view")


if __name__ == "__main__":
    main()
