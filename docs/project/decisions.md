# Architecture Decision Records (ADRs)

This file tracks significant architectural and design decisions made during OpenClaw/ALGOWAY development.

---

## ADR-001: Microsoft Graph API over IMAP/SMTP for Meutia Email

**Date**: 2026-03-01
**Status**: Accepted

**Context**: Railway hobby plan blocks all SMTP ports (25, 465, 587). Microsoft O365 also disabled Basic Auth for IMAP. The `imap-smtp-email` skill was non-functional in this environment.

**Decision**: Use Microsoft Graph API (OAuth2 delegated auth, refresh token) over HTTPS port 443. Replicated pattern from `whatsapp-mcp/services/bot/services/email.py`. Implemented as `skills/ms-graph-email/`.

**Consequences**: Email works on Railway without port exceptions. Requires `MS_GRAPH_CLIENT_ID`, `MS_GRAPH_TENANT_ID`, `MS_GRAPH_REFRESH_TOKEN_MEUTIA` in Railway vars. Token refresh is automatic.

---

## ADR-002: Prompt Injection Defense for Email Watcher Cron

**Date**: 2026-03-01
**Status**: Accepted

**Context**: Automated email reading is a prompt injection vector — anyone can send Meutia an email with malicious instructions.

**Decision**: Implement L1-L3 defenses in cron prompt:
- (L1) Content isolation — email body is treated as UNTRUSTED EXTERNAL DATA
- (L2) Sender allowlist — @algowayss.co only
- (L3) Locked action scope — read + notify only, no replies/forwards/deletes

**Consequences**: Meutia will not act on instructions in email bodies during automated checks. External sender emails are flagged but not processed.
