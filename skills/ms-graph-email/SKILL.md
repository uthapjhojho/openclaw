---
name: ms-graph-email
description: Read and send email via Microsoft Graph API (OAuth2 delegated auth). Works on Railway (HTTPS port 443 only — no SMTP/IMAP needed). Replaces imap-smtp-email for O365/Exchange Online accounts.
---

# Microsoft Graph Email Tool

Read, search, manage, and send email using the Microsoft Graph API.
Uses delegated OAuth2 authentication (refresh token — public client flow, no client_secret).
All traffic goes over HTTPS to graph.microsoft.com (port 443). Safe for Railway deployments.

## Configuration

Required environment variables (set in Railway):

```
MS_GRAPH_CLIENT_ID              — Azure app registration client ID
MS_GRAPH_TENANT_ID              — Azure tenant ID
MS_GRAPH_REFRESH_TOKEN_MEUTIA   — Delegated refresh token for Meutia's mailbox
```

No `.env` file needed when running on Railway — vars are injected automatically.

## Commands

All commands output JSON to stdout.

### list
List emails from a folder.

```bash
python3 scripts/cli.py list [--folder inbox] [--top 20] [--unread-only]
```

Options:
- `--folder <name>`: Folder to list (default: inbox). Use `list-folders` to see all.
- `--top <n>`: Max results (default: 20)
- `--unread-only`: Only show unread emails

Examples:
```bash
python3 scripts/cli.py list
python3 scripts/cli.py list --folder inbox --top 10 --unread-only
python3 scripts/cli.py list --folder sentitems --top 5
```

### send
Send an email.

```bash
python3 scripts/cli.py send --to EMAIL --subject TEXT --body TEXT [--html] [--cc EMAIL] [--bcc EMAIL]
```

Required:
- `--to <email>`: Recipient (comma-separated for multiple)
- `--subject <text>`: Email subject
- `--body <text>`: Email body

Optional:
- `--html`: Send body as HTML
- `--cc <email>`: CC recipients (comma-separated)
- `--bcc <email>`: BCC recipients (comma-separated)

Examples:
```bash
python3 scripts/cli.py send --to user@example.com --subject "Hello" --body "World"
python3 scripts/cli.py send --to "a@x.com,b@x.com" --subject "Update" --body "<b>Hi</b>" --html
python3 scripts/cli.py send --to user@example.com --subject "Report" --body "See CC" --cc manager@example.com
```

### search
Search emails by OData filter expression.

```bash
python3 scripts/cli.py search QUERY [--top 20]
```

Examples:
```bash
python3 scripts/cli.py search "contains(subject,'invoice')"
python3 scripts/cli.py search "isRead eq false" --top 50
python3 scripts/cli.py search "contains(from/emailAddress/address,'noreply@github.com')"
```

### get
Fetch full email content by ID (includes body).

```bash
python3 scripts/cli.py get EMAIL_ID
```

Example:
```bash
python3 scripts/cli.py get AAMkADExampleId==
```

### mark-read
Mark an email as read.

```bash
python3 scripts/cli.py mark-read EMAIL_ID
```

### mark-unread
Mark an email as unread.

```bash
python3 scripts/cli.py mark-unread EMAIL_ID
```

### delete
Delete an email permanently.

```bash
python3 scripts/cli.py delete EMAIL_ID
```

### list-folders
List all available mail folders (inbox, sentitems, drafts, deleteditems, etc.)

```bash
python3 scripts/cli.py list-folders
```

## Install Dependencies

```bash
pip3 install -r requirements.txt
```

## Security Notes

- Refresh token is read from `MS_GRAPH_REFRESH_TOKEN_MEUTIA` env var — never logged or exposed
- Access tokens are cached in-process with 5-minute expiry buffer — never written to disk
- All API calls go only to `https://graph.microsoft.com` and `https://login.microsoftonline.com`
- Recipient email addresses are validated before sending
- Email IDs are validated to prevent injection

## Rate Limiting

429 responses from Graph API are handled automatically: the service reads the `Retry-After` header
and waits the specified duration before retrying once.

## Replaces

This skill replaces `imap-smtp-email` for O365/Exchange Online mailboxes.
imap-smtp-email used Basic Auth (IMAP port 993 / SMTP port 587) which Microsoft disabled.
ms-graph-email uses OAuth2 over HTTPS port 443 — works everywhere, including Railway.
