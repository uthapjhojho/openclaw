"""Tests for github_pr.py — requires GITHUB_TOKEN env var."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from github_pr import (
    get_default_branch,
    get_file,
    list_open_prs,
    create_branch,
    upsert_file,
    create_pr,
)
import github_pr as gpr

import pytest
import requests

pytestmark = pytest.mark.skipif(
    not os.environ.get("GITHUB_TOKEN"), reason="GITHUB_TOKEN not set"
)

REPO = "uthapjhojho/algowayss_web"


def test_repo_accessible():
    """get_default_branch returns a non-empty string."""
    result = get_default_branch(REPO)
    assert isinstance(result, str)
    assert len(result) > 0


def test_list_refs():
    """Direct API call to list refs returns 200 and a list."""
    token = os.environ["GITHUB_TOKEN"]
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/git/refs/heads",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
        timeout=20,
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_dry_run_create_pr():
    """DRY_RUN=1 makes create_pr return dry_run payload without POSTing."""
    old = os.environ.get("DRY_RUN")
    try:
        os.environ["DRY_RUN"] = "1"
        result = create_pr(REPO, "Test", "Body", "blog/test", "main")
        assert isinstance(result, dict)
        assert result["dry_run"] is True
        assert "payload" in result
        assert result["payload"]["title"] == "Test"
    finally:
        if old is None:
            os.environ.pop("DRY_RUN", None)
        else:
            os.environ["DRY_RUN"] = old


def test_list_open_prs_returns_list():
    """list_open_prs returns a list; items have expected keys."""
    result = list_open_prs(REPO)
    assert isinstance(result, list)
    for item in result:
        assert "number" in item
        assert "title" in item
        assert "head_branch" in item
        assert "html_url" in item


def test_get_file_nonexistent_returns_none():
    """get_file returns None for a file that does not exist."""
    result = get_file(
        REPO, "main", "_posts/this-file-definitely-does-not-exist-xyz-12345.md"
    )
    assert result is None
