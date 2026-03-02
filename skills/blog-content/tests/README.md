# Blog Content Skill — Tests

## Setup

```bash
# From the skill root
pip install requests pytest

# Or use a venv
python3 -m venv .venv
source .venv/bin/activate
pip install requests pytest
```

## Required Environment Variables

| Variable | Required for | Notes |
|----------|-------------|-------|
| `GITHUB_TOKEN` | `test_github_pr.py` | Personal access token with `repo` scope on `uthapjhojho/algowayss_web` |

GitHub tests are automatically skipped if `GITHUB_TOKEN` is not set.

Research API tests (`test_research_api.py`) call public APIs — no auth required, but need internet access.

## Run All Tests

```bash
# From the blog-content/ skill root
python3 -m pytest tests/ -v
```

## Run Individual Test Files

```bash
python3 -m pytest tests/test_research_api.py -v
python3 -m pytest tests/test_github_pr.py -v
python3 -m pytest tests/test_jekyll_post.py -v
```

## Run Without pytest (Standalone)

```bash
# Research API — live API call test
python3 tests/test_research_api.py

# Jekyll post — pure unit tests (no network)
python3 tests/test_jekyll_post.py
```

## Test Coverage

| File | Type | Network | Auth |
|------|------|---------|------|
| `test_research_api.py` | Integration | Yes (public APIs) | None |
| `test_github_pr.py` | Integration | Yes | `GITHUB_TOKEN` |
| `test_jekyll_post.py` | Unit | No | None |

## Quick Smoke Test

```bash
# Verify academic search works
python3 scripts/research_api.py "large language models" --limit 3

# Verify Jekyll formatter works
echo "Body of the post here." | python3 scripts/jekyll_post.py \
  --title "Test Post" --tags "ai,test" --author "Meutia" --excerpt "A test."

# Verify GitHub access (needs GITHUB_TOKEN)
python3 scripts/github_pr.py get-default-branch --repo uthapjhojho/algowayss_web

# Dry-run a PR (no GitHub write needed)
DRY_RUN=1 python3 scripts/github_pr.py create-pr \
  --repo uthapjhojho/algowayss_web \
  --title "Blog: Test" \
  --body "Test body" \
  --branch blog/2026-03-10-test
```
