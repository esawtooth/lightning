#!/usr/bin/env python3
"""Simple integration test suite for the Vextir Azure Functions.

The script checks that the deployed functions respond correctly by
registering a temporary user, logging in, and sending test requests to
other endpoints. Azure CLI must be installed and authenticated via
``az login``.

Usage:
    python scripts/test_azure_functions.py <resource-group> <function-app>
    python scripts/test_azure_functions.py --base-url https://funcapp.azurewebsites.net/api

An admin token can be provided through the ``--admin-token`` argument or
``ADMIN_TOKEN`` environment variable to approve the test user so that the
login test succeeds.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

import requests

DEFAULT_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "30"))


def run(cmd):
    """Run a shell command and return stdout."""
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout.strip()


def get_base_url(args):
    if args.base_url:
        return args.base_url.rstrip('/')
    host = run(
        [
            "az",
            "functionapp",
            "show",
            "--resource-group",
            args.resource_group,
            "--name",
            args.function_app,
            "--query",
            "defaultHostName",
            "-o",
            "tsv",
        ]
    )
    if not host:
        raise RuntimeError("Unable to determine function host name")
    return f"https://{host}/api"


def register_user(base_url, username, password):
    resp = requests.post(
        f"{base_url}/auth/register",
        json={"username": username, "password": password},
        timeout=DEFAULT_TIMEOUT,
    )
    print("REGISTER", resp.status_code)
    if resp.status_code != 201 and resp.status_code != 409:
        raise RuntimeError(f"register failed: {resp.status_code} {resp.text}")


def approve_user(base_url, username, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = requests.post(
        f"{base_url}/auth/approve",
        json={"username": username, "action": "approve"},
        headers=headers,
        timeout=DEFAULT_TIMEOUT,
    )
    print("APPROVE", resp.status_code)
    if resp.status_code != 200:
        raise RuntimeError(f"approve failed: {resp.status_code} {resp.text}")


def login_user(base_url, username, password):
    resp = requests.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=DEFAULT_TIMEOUT,
    )
    print("LOGIN", resp.status_code)
    if resp.status_code != 200:
        raise RuntimeError(f"login failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]


def refresh_token(base_url, token):
    resp = requests.post(
        f"{base_url}/auth/refresh",
        headers={"Authorization": f"Bearer {token}"},
        timeout=DEFAULT_TIMEOUT,
    )
    print("REFRESH", resp.status_code)
    if resp.status_code != 200:
        raise RuntimeError(f"refresh failed: {resp.status_code} {resp.text}")
    return resp.json()["token"]


def send_event(base_url, token):
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "integration-test",
        "type": "user.message",
        "metadata": {"message": "ping"},
    }
    resp = requests.post(
        f"{base_url}/events",
        json=event,
        headers={"Authorization": f"Bearer {token}"},
        timeout=DEFAULT_TIMEOUT,
    )
    print("EVENT", resp.status_code)
    if resp.status_code != 202:
        raise RuntimeError(f"event failed: {resp.status_code} {resp.text}")


def schedule_event(base_url, token):
    event = {
        "type": "user.message",
        "source": "integration-test",
        "metadata": {"message": "future"},
    }
    timestamp = (datetime.utcnow() + timedelta(minutes=1)).isoformat() + "Z"
    payload = {"event": event, "timestamp": timestamp}
    resp = requests.post(
        f"{base_url}/schedule",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=DEFAULT_TIMEOUT,
    )
    print("SCHEDULE", resp.status_code)
    if resp.status_code != 201:
        raise RuntimeError(f"schedule failed: {resp.status_code} {resp.text}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test deployed Vextir functions")
    parser.add_argument("resource_group", nargs="?")
    parser.add_argument("function_app", nargs="?")
    parser.add_argument("--base-url")
    parser.add_argument("--admin-token", default=os.environ.get("ADMIN_TOKEN"))
    args = parser.parse_args(argv)

    if not args.base_url and not (args.resource_group and args.function_app):
        parser.error("Provide --base-url or <resource-group> <function-app>")

    base_url = get_base_url(args)
    print("Using base URL:", base_url)

    username = f"testuser{int(time.time())}"
    password = "Password1"

    register_user(base_url, username, password)

    if args.admin_token:
        approve_user(base_url, username, args.admin_token)
        token = login_user(base_url, username, password)
    else:
        try:
            token = login_user(base_url, username, password)
        except RuntimeError as e:
            print("Login failed (likely awaiting approval):", e)
            return

    token = refresh_token(base_url, token)
    send_event(base_url, token)
    schedule_event(base_url, token)
    print("All tests passed")


if __name__ == "__main__":
    main()
