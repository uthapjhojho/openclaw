#!/usr/bin/env python3
"""GitHub PR helper — CLI + importable functions for blog-content skill."""

import argparse
import base64
import json
import os
import socket
import sys

import requests
from requests.adapters import HTTPAdapter

TIMEOUT = 20
API_BASE = "https://api.github.com"


# =============================================================================
# IPv4 ADAPTER (Railway compatibility)
# =============================================================================

class IPv4HTTPAdapter(HTTPAdapter):
    """HTTP Adapter that forces IPv4 connections for Railway compatibility."""

    def init_poolmanager(self, *args, **kwargs):
        import urllib3.util.connection as urllib3_conn

        _orig_create_connection = urllib3_conn.create_connection

        def patched_create_connection(address, *args, **kwargs):
            host, port = address
            for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM):
                af, socktype, proto, canonname, sa = res
                try:
                    sock = socket.socket(af, socktype, proto)
                    sock.settimeout(kwargs.get("timeout", TIMEOUT))
                    sock.connect(sa)
                    return sock
                except socket.error:
                    try:
                        sock.close()
                    except Exception:
                        pass
                    continue
            raise socket.error(f"Could not connect to {host}:{port} via IPv4")

        urllib3_conn.create_connection = patched_create_connection
        super().init_poolmanager(*args, **kwargs)


def _create_session() -> requests.Session:
    """Create a requests.Session that forces IPv4."""
    session = requests.Session()
    adapter = IPv4HTTPAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def _headers():
    token = os.environ.get("GITHUB_TOKEN", "")
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }


def _api_error(msg: str, status: int = 0):
    """Print JSON error to stdout and exit 1."""
    print(json.dumps({"error": msg, "status": status}))
    sys.exit(1)


# =============================================================================
# API FUNCTIONS
# =============================================================================

def get_default_branch(repo: str) -> str:
    """Return the default branch name for a repo (e.g. 'main')."""
    sess = _create_session()
    r = sess.get(f"{API_BASE}/repos/{repo}", headers=_headers(), timeout=TIMEOUT)
    if r.status_code != 200:
        _api_error(f"Failed to get repo info: {r.text}", r.status_code)
    return r.json()["default_branch"]


def create_branch(repo: str, branch: str, from_branch: str) -> str:
    """Create a new branch from from_branch. Returns the commit sha."""
    sess = _create_session()
    # Get the sha of the source branch
    r = sess.get(
        f"{API_BASE}/repos/{repo}/git/ref/heads/{from_branch}",
        headers=_headers(), timeout=TIMEOUT,
    )
    if r.status_code != 200:
        _api_error(f"Failed to get ref for {from_branch}: {r.text}", r.status_code)
    sha = r.json()["object"]["sha"]

    # Create the new branch
    r = sess.post(
        f"{API_BASE}/repos/{repo}/git/refs",
        headers=_headers(), timeout=TIMEOUT,
        json={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    if r.status_code not in (200, 201):
        _api_error(f"Failed to create branch {branch}: {r.text}", r.status_code)
    return sha


def get_file(repo: str, branch: str, path: str):
    """Get file from repo. Returns {"content_b64": ..., "sha": ...} or None."""
    sess = _create_session()
    r = sess.get(
        f"{API_BASE}/repos/{repo}/contents/{path}",
        headers=_headers(), timeout=TIMEOUT,
        params={"ref": branch},
    )
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        _api_error(f"Failed to get file {path}: {r.text}", r.status_code)
    data = r.json()
    return {"content_b64": data["content"], "sha": data["sha"]}


def upsert_file(repo: str, branch: str, path: str, content_str: str,
                commit_msg: str, sha: str = None) -> str:
    """Create or update a file. Returns the new blob sha."""
    sess = _create_session()
    content_b64 = base64.b64encode(content_str.encode()).decode()
    payload = {
        "message": commit_msg,
        "content": content_b64,
        "branch": branch,
    }
    if sha is not None:
        payload["sha"] = sha

    r = sess.put(
        f"{API_BASE}/repos/{repo}/contents/{path}",
        headers=_headers(), timeout=TIMEOUT,
        json=payload,
    )
    if r.status_code not in (200, 201):
        _api_error(f"Failed to upsert file {path}: {r.text}", r.status_code)
    return r.json()["content"]["sha"]


def create_pr(repo: str, title: str, body: str, head: str,
              base: str = None) -> dict:
    """Create a pull request. Respects DRY_RUN env var."""
    dry_run = os.environ.get("DRY_RUN") == "1"

    if base is None:
        base = "main" if dry_run else get_default_branch(repo)

    payload = {
        "title": title,
        "body": body,
        "head": head,
        "base": base,
    }

    if dry_run:
        return {"dry_run": True, "payload": payload}

    sess = _create_session()
    r = sess.post(
        f"{API_BASE}/repos/{repo}/pulls",
        headers=_headers(), timeout=TIMEOUT,
        json=payload,
    )
    if r.status_code not in (200, 201):
        _api_error(f"Failed to create PR: {r.text}", r.status_code)
    data = r.json()
    return {"url": data["url"], "number": data["number"], "html_url": data["html_url"]}


def list_open_prs(repo: str) -> list:
    """List open pull requests."""
    sess = _create_session()
    r = sess.get(
        f"{API_BASE}/repos/{repo}/pulls",
        headers=_headers(), timeout=TIMEOUT,
        params={"state": "open"},
    )
    if r.status_code != 200:
        _api_error(f"Failed to list PRs: {r.text}", r.status_code)
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "head_branch": pr["head"]["ref"],
            "html_url": pr["html_url"],
        }
        for pr in r.json()
    ]


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="GitHub PR helper")
    sub = parser.add_subparsers(dest="command")

    # get-default-branch
    p = sub.add_parser("get-default-branch")
    p.add_argument("--repo", required=True)

    # create-branch
    p = sub.add_parser("create-branch")
    p.add_argument("--repo", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--from-branch", required=True)

    # get-file
    p = sub.add_parser("get-file")
    p.add_argument("--repo", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--path", required=True)

    # upsert-file
    p = sub.add_parser("upsert-file")
    p.add_argument("--repo", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--path", required=True)
    p.add_argument("--content", required=True)
    p.add_argument("--message", required=True)
    p.add_argument("--sha", default=None)

    # create-pr
    p = sub.add_parser("create-pr")
    p.add_argument("--repo", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--body", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--base", default=None)

    # list-open-prs
    p = sub.add_parser("list-open-prs")
    p.add_argument("--repo", required=True)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "get-default-branch":
        result = get_default_branch(args.repo)
    elif args.command == "create-branch":
        result = create_branch(args.repo, args.branch, args.from_branch)
    elif args.command == "get-file":
        result = get_file(args.repo, args.branch, args.path)
    elif args.command == "upsert-file":
        # Read content from file path if it exists, else treat as literal
        content = args.content
        if os.path.isfile(content):
            with open(content, "r") as f:
                content = f.read()
        result = upsert_file(args.repo, args.branch, args.path, content,
                             args.message, sha=args.sha)
    elif args.command == "create-pr":
        result = create_pr(args.repo, args.title, args.body, args.branch,
                           base=args.base)
    elif args.command == "list-open-prs":
        result = list_open_prs(args.repo)
    else:
        parser.print_help()
        sys.exit(1)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
