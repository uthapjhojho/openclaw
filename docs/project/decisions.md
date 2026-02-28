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

---

## ADR-002 Amendment: L2 Noise Filter (2026-03-01)

**Date**: 2026-03-01
**Status**: Supersedes ADR-002 L2

**Context**: The original L2 defense used a strict `@algowayss.co` sender allowlist — this meant Meutia would notify Captain of every external email (Teams notifications, LinkedIn, calendar invites, Mailchimp, Outlook delivery reports). After the first real cron run, Captain observed the notification was full of noise: Microsoft Teams, Outlook delivery notices, and a self-sent email.

**Decision**: Replace the strict allowlist with a smart noise filter. Instead of blocking all external senders, the filter uses explicit patterns (sender address substrings, subject keywords, known automated service names) to silently discard automated/marketing/system emails. LLM judgment handles edge cases: "if it looks like a robot sent it, skip it." Real human emails from any domain still generate notifications.

**Consequences**: Meutia now only notifies Captain of emails that genuinely require human attention, regardless of sender domain. Marketing emails, newsletters, calendar notifications, Teams alerts, Mailchimp, and self-sent emails are silently discarded. The noise filter is defined in the cron prompt at `skills/email-watcher/SKILL.md` and in Railway `cron/jobs.json`.

---

## ADR-003: Python Packages on Railway via PYTHONPATH Venv

**Date**: 2026-03-01
**Status**: Accepted

**Context**: Railway's container is Debian-based with Python 3.11. PEP 668 marks the system Python as "externally managed" — `pip install` and `python3 -m pip install` are both blocked system-wide. `ensurepip` is stripped (Railway strips it to reduce image size). `python3-pip` and `python3-requests` are not available via apt. The `ms-graph-email` skill's `requirements.txt` (`requests`) cannot be installed at container startup.

**Decision**: Create a virtualenv on the persistent `/data` disk (`/data/openclaw/venv`) so it survives redeployments. Install packages there once. Set `PYTHONPATH=/data/openclaw/venv/lib/python3.11/site-packages` as a permanent Railway environment variable so the system `python3` interpreter finds venv packages at runtime without needing pip on every boot.

The `railway-start.sh` pip loop (get-pip.py bootstrap + pip install) is kept as a fallback/future safety net but is effectively a no-op when `PYTHONPATH` is already set.

**Consequences**: Skill Python dependencies (`requests`, etc.) are resolved via PYTHONPATH at zero boot cost. New dependencies require a one-time manual `python3 -m pip install -r requirements.txt --prefix /data/openclaw/venv` inside the Railway container, or a Railway env var update. The venv lives at `/data/openclaw/venv` and must match Railway's Python version (currently 3.11).
