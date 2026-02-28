#!/usr/bin/env python3
"""
ms-graph-email CLI

Command-line interface for Microsoft Graph email operations.
Prints results as JSON to stdout.

Usage:
    python3 scripts/cli.py list [--folder INBOX] [--top 20] [--unread-only]
    python3 scripts/cli.py send --to EMAIL --subject TEXT --body TEXT [--html] [--cc EMAIL] [--bcc EMAIL]
    python3 scripts/cli.py search QUERY [--top 20]
    python3 scripts/cli.py get EMAIL_ID
    python3 scripts/cli.py mark-read EMAIL_ID
    python3 scripts/cli.py mark-unread EMAIL_ID
    python3 scripts/cli.py delete EMAIL_ID
    python3 scripts/cli.py list-folders
"""

import argparse
import json
import logging
import re
import sys
import os

# Allow running directly from the scripts/ directory or from skill root
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from graph_email import EmailService, _is_valid_email, get_email_service  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# INPUT VALIDATION HELPERS
# =============================================================================

_SAFE_FOLDER_RE = re.compile(r'^[a-zA-Z0-9_\- ]{1,64}$')
# Graph API message IDs are base64url encoded — allow alphanumeric plus - _ = (no / to avoid path traversal)
_SAFE_ID_RE = re.compile(r'^[A-Za-z0-9\-_=]{1,800}$')


_FOLDER_ALIASES = {
    "sent items": "sentitems",
    "sent": "sentitems",
    "deleted items": "deleteditems",
    "deleted": "deleteditems",
    "junk email": "junkemail",
    "junk": "junkemail",
    "inbox": "inbox",
    "drafts": "drafts",
    "outbox": "outbox",
    "archive": "archive",
}


def normalize_folder(name: str) -> str:
    """Normalize human-readable folder names to Graph API well-known names."""
    if name is None:
        return name
    return _FOLDER_ALIASES.get(name.lower(), name)


def _validate_folder(folder: str) -> str:
    """Validate folder name — only alphanumeric, underscore, hyphen, space."""
    if not _SAFE_FOLDER_RE.match(folder):
        print(json.dumps({"error": f"Invalid folder name: {folder!r}"}))
        sys.exit(1)
    return folder


def _validate_email_id(email_id: str) -> str:
    """Validate email ID format (Graph API IDs are base64url-like)."""
    if not _SAFE_ID_RE.match(email_id):
        print(json.dumps({"error": f"Invalid email ID format"}))
        sys.exit(1)
    return email_id


def _validate_odata_filter(filter_str: str) -> str:
    """Basic OData filter validation to reject obvious injection attempts."""
    if len(filter_str) > 500:
        print(json.dumps({"error": "Filter expression too long (max 500 chars)"}))
        sys.exit(1)
    # Reject patterns that have no place in a Graph OData filter
    dangerous = [";", "--", "/*", "*/", "%00", "javascript:", "data:"]
    lower = filter_str.lower()
    for pat in dangerous:
        if pat in lower:
            print(json.dumps({"error": "Invalid filter expression"}))
            sys.exit(1)
    return filter_str


def _validate_recipients(value: str, field: str) -> str:
    """Validate comma-separated email addresses."""
    addresses = [a.strip() for a in value.split(",") if a.strip()]
    invalid = [a for a in addresses if not _is_valid_email(a)]
    if invalid:
        print(json.dumps({"error": f"Invalid email address(es) in {field}: {invalid}"}))
        sys.exit(1)
    if not addresses:
        print(json.dumps({"error": f"{field} is required and must be a valid email address"}))
        sys.exit(1)
    return value


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

def cmd_list(args: argparse.Namespace) -> None:
    folder = normalize_folder(args.folder)
    folder = _validate_folder(folder)
    svc = get_email_service()
    results = svc.list_emails(
        folder=folder,
        top=args.top,
        unread_only=args.unread_only,
    )
    print(json.dumps(results, default=str, indent=2))


def cmd_send(args: argparse.Namespace) -> None:
    to = _validate_recipients(args.to, "--to")
    cc = _validate_recipients(args.cc, "--cc") if args.cc else None
    bcc = _validate_recipients(args.bcc, "--bcc") if args.bcc else None

    svc = get_email_service()
    success = svc.send_email(
        to=to,
        subject=args.subject,
        body=args.body,
        cc=cc,
        bcc=bcc,
        is_html=args.html,
    )
    print(json.dumps({"success": success}))
    if not success:
        sys.exit(1)


def cmd_search(args: argparse.Namespace) -> None:
    query = _validate_odata_filter(args.query)
    svc = get_email_service()
    results = svc.search_emails(query=query, top=args.top)
    print(json.dumps(results, default=str, indent=2))


def cmd_get(args: argparse.Namespace) -> None:
    email_id = _validate_email_id(args.email_id)
    svc = get_email_service()
    result = svc.get_email(email_id)
    if result is None:
        print(json.dumps({"error": "Email not found or inaccessible"}))
        sys.exit(1)
    print(json.dumps(result, default=str, indent=2))


def cmd_mark_read(args: argparse.Namespace) -> None:
    email_id = _validate_email_id(args.email_id)
    svc = get_email_service()
    success = svc.mark_as_read(email_id)
    print(json.dumps({"success": success}))
    if not success:
        sys.exit(1)


def cmd_mark_unread(args: argparse.Namespace) -> None:
    email_id = _validate_email_id(args.email_id)
    svc = get_email_service()
    success = svc.mark_as_unread(email_id)
    print(json.dumps({"success": success}))
    if not success:
        sys.exit(1)


def cmd_delete(args: argparse.Namespace) -> None:
    email_id = _validate_email_id(args.email_id)
    svc = get_email_service()
    success = svc.delete_email(email_id)
    print(json.dumps({"success": success}))
    if not success:
        sys.exit(1)


def cmd_list_folders(args: argparse.Namespace) -> None:
    svc = get_email_service()
    results = svc.list_folders()
    print(json.dumps(results, default=str, indent=2))


# =============================================================================
# PARSER
# =============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 scripts/cli.py",
        description="ms-graph-email: Email operations via Microsoft Graph API",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List emails from a folder")
    p_list.add_argument("--folder", default="inbox", help="Folder name (default: inbox)")
    p_list.add_argument("--top", type=int, default=20, help="Max results (default: 20)")
    p_list.add_argument("--unread-only", action="store_true", help="Only show unread emails")

    # send
    p_send = subparsers.add_parser("send", help="Send an email")
    p_send.add_argument("--to", required=True, help="Recipient email address(es), comma-separated")
    p_send.add_argument("--subject", required=True, help="Email subject")
    p_send.add_argument("--body", required=True, help="Email body text")
    p_send.add_argument("--html", action="store_true", help="Send body as HTML")
    p_send.add_argument("--cc", default=None, help="CC recipients, comma-separated")
    p_send.add_argument("--bcc", default=None, help="BCC recipients, comma-separated")

    # search
    p_search = subparsers.add_parser("search", help="Search emails by OData filter")
    p_search.add_argument("query", help="OData filter (e.g., \"contains(subject,'invoice')\")")
    p_search.add_argument("--top", type=int, default=20, help="Max results (default: 20)")

    # get
    p_get = subparsers.add_parser("get", help="Get a single email by ID")
    p_get.add_argument("email_id", help="Email message ID")

    # mark-read
    p_mr = subparsers.add_parser("mark-read", help="Mark email as read")
    p_mr.add_argument("email_id", help="Email message ID")

    # mark-unread
    p_mu = subparsers.add_parser("mark-unread", help="Mark email as unread")
    p_mu.add_argument("email_id", help="Email message ID")

    # delete
    p_del = subparsers.add_parser("delete", help="Delete an email")
    p_del.add_argument("email_id", help="Email message ID")

    # list-folders
    subparsers.add_parser("list-folders", help="List all mail folders")

    return parser


# =============================================================================
# MAIN
# =============================================================================

COMMAND_MAP = {
    "list": cmd_list,
    "send": cmd_send,
    "search": cmd_search,
    "get": cmd_get,
    "mark-read": cmd_mark_read,
    "mark-unread": cmd_mark_unread,
    "delete": cmd_delete,
    "list-folders": cmd_list_folders,
}

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()

    handler = COMMAND_MAP.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)

    handler(args)
