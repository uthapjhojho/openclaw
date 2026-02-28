#!/usr/bin/env python3
"""
ms-graph-email CLI

Command-line interface for Microsoft Graph email operations.
Prints results as JSON to stdout.

Usage:
    python3 scripts/cli.py list [--folder INBOX] [--top 20] [--unread-only]
    python3 scripts/cli.py check-inbox [--top 10]
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
# NOISE FILTER — deterministic, no LLM judgment required
# =============================================================================

_NOISE_SENDER_SUBSTRINGS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "notifications@", "notification@", "newsletter",
    "mailer-daemon", "postmaster", "automated",
    "bounce@", "alerts@", "admin@",
    "support@microsoft", "teams@", "calendar@",
    "mail@linkedin", "info@linkedin",
    "noreply@email.teams.microsoft.com",
]

_NOISE_SUBJECT_SUBSTRINGS = [
    "undeliverable", "delivery status notification",
    "automatic reply", "auto:", "out of office", "ndr:",
    "newsletter", "subscription", "unsubscribe",
    "marketing", "digest", "weekly update", "monthly update",
]

_NOISE_SENDER_NAMES = [
    "microsoft teams", "microsoft outlook",
    "linkedin", "mailchimp", "constant contact", "sendgrid",
    "mailer daemon",
]

_MEUTIA_EMAIL = "meutia@algowayss.co"


def _extract_from(email: dict) -> tuple:
    """Extract (address, name) from Graph API nested from field."""
    from_field = email.get("from") or {}
    if isinstance(from_field, dict):
        email_addr = from_field.get("emailAddress") or {}
        return (
            (email_addr.get("address") or "").lower(),
            (email_addr.get("name") or "").lower(),
        )
    # Fallback if already a flat string
    return (str(from_field).lower(), "")


def _is_noise(email: dict) -> bool:
    """Return True if the email matches any noise filter pattern."""
    from_addr, from_name = _extract_from(email)
    subject = (email.get("subject") or "").lower()

    # Self-sent
    if _MEUTIA_EMAIL in from_addr:
        return True

    # Sender address patterns
    for pattern in _NOISE_SENDER_SUBSTRINGS:
        if pattern in from_addr:
            return True

    # Sender display name patterns
    for pattern in _NOISE_SENDER_NAMES:
        if pattern in from_name:
            return True

    # Subject patterns
    for pattern in _NOISE_SUBJECT_SUBSTRINGS:
        if pattern in subject:
            return True

    return False


# =============================================================================
# COMMAND HANDLERS
# =============================================================================

def cmd_check_inbox(args: argparse.Namespace) -> None:
    """
    Fetch unread inbox emails, apply noise filter, mark ALL fetched emails as
    read (noise + real), and return only the real human emails as JSON.

    Output: {"real_count": N, "emails": [...]}
    If real_count == 0, no notification needed.
    """
    svc = get_email_service()
    all_unread = svc.list_emails(folder="inbox", top=args.top, unread_only=True)

    real_emails = []
    for email in all_unread:
        email_id = email.get("id")
        if not email_id:
            continue
        # Mark as read regardless (prevents infinite re-notification)
        svc.mark_as_read(email_id)
        if not _is_noise(email):
            from_addr, from_name = _extract_from(email)
            real_emails.append({
                "from": f"{from_name} <{from_addr}>" if from_name else from_addr,
                "subject": email.get("subject") or "(no subject)",
                "preview": (email.get("bodyPreview") or "")[:100],
                "receivedAt": email.get("receivedDateTime") or "",
            })

    print(json.dumps({"real_count": len(real_emails), "emails": real_emails}, indent=2))


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

    # check-inbox
    p_ci = subparsers.add_parser("check-inbox", help="Fetch unread inbox, filter noise, mark all as read, return real emails only")
    p_ci.add_argument("--top", type=int, default=10, help="Max unread emails to fetch (default: 10)")

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
    "check-inbox": cmd_check_inbox,
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
