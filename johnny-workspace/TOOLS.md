# TOOLS.md - Local Notes

## SharePoint Excel — Financial Data Source

ALGOWAY financial data lives in SharePoint Excel files (P&L, cash flow, invoices). Access via Microsoft Graph API, same pattern as ms-graph-email.

```bash
# List SharePoint sites
python3 /app/skills/ms-graph/scripts/cli.py sites list

# List drives in a site
python3 /app/skills/ms-graph/scripts/cli.py drives list --site-id SITE_ID

# List files in a drive/folder
python3 /app/skills/ms-graph/scripts/cli.py files list --drive-id DRIVE_ID --path "/Finance"

# Download an Excel file
python3 /app/skills/ms-graph/scripts/cli.py files download --drive-id DRIVE_ID --item-id ITEM_ID --output /tmp/report.xlsx

# Read Excel workbook data (via Graph workbooks API)
python3 /app/skills/ms-graph/scripts/cli.py workbook read --drive-id DRIVE_ID --item-id ITEM_ID --sheet "P&L"
```

Env vars: `MS_GRAPH_CLIENT_ID`, `MS_GRAPH_TENANT_ID`, `MS_GRAPH_REFRESH_TOKEN_JOHNNY` — stored in Railway, do not hardcode.

Note: If the ms-graph skill is not yet installed, check with Captain before attempting SharePoint access. Document the actual path once confirmed.

---

## CoretaxDJP — Indonesian Tax Portal

CoretaxDJP (Coretax DJP) is the Directorate General of Taxes (DJP) portal for:
- **e-Filing** — submitting SPT (annual tax returns)
- **e-Bupot** — proof of tax withholding (Bukti Potong)
- **Tax payment** tracking and ID verification

### Standard Indonesian Tax Forms

| Form | Description | Due Date |
|------|-------------|----------|
| PPh 21 | Personal income tax withholding | Monthly: 10th of following month |
| PPh 25 | Monthly corporate income tax installment | 15th of following month |
| PPh 29 | Annual corporate income tax return | End of April (4 months after fiscal year end) |
| PPN | Value Added Tax (VAT) | Monthly: end of following month |
| SPT Tahunan | Annual personal income tax return | End of March (personal) |

### Credentials

Env vars: `CORETAX_USERNAME`, `CORETAX_PASSWORD` — TBD (pending setup by Captain).

Do NOT store DJP credentials in memory files. Use env vars only.

### Key Tax Calendar (Indonesia)

- **January 31:** Deadline for e-Bupot final (tax year end)
- **March 31:** SPT Tahunan personal (PPh 21)
- **April 30:** SPT Tahunan corporate (PPh 29)
- Monthly filings: see table above

Track upcoming deadlines in `HEARTBEAT.md` when within 14 days.

---

## Report Delivery

Financial reports and alerts go to Captain via Telegram:

```bash
# Send message to Captain
# Use the telegram skill or openclaw send-message
openclaw send-message --chat-id "$CAPTAIN_CHAT_ID" --text "Your report text here"
```

Chat ID: loaded from env var `CAPTAIN_CHAT_ID` — set this in Railway vars.

Format guidelines for Telegram:
- No Markdown tables (renders poorly)
- Use bullet lists with explicit currency labels
- Lead with insight/summary, then supporting numbers
- Keep it concise — Captain does not want walls of text

---

## Hosting

You run on **Railway**.

- Persistent data volume: `/data/openclaw/johnny-workspace/`
- If the gateway needs a restart, tell Captain — do NOT attempt it yourself

---

Add whatever helps you do your job. This is your cheat sheet.
