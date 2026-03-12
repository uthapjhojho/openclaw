#!/bin/sh
# railway-start.sh — Pre-boot repair + gateway start for Railway deployments.
#
# Runs before the gateway to patch known schema-breaking values in
# openclaw.json that would prevent the server from starting.
# Safe to run on every boot; no-ops when the config is already valid.

set -e

# Repair gateway.auth.mode if it holds an invalid value.
# Valid values (from src/config/types.gateway.ts): token | password | trusted-proxy
# Uses write-to-temp-then-rename to avoid EACCES on the original file.
# rename(2) only requires write permission on the directory, not the file itself.
node - <<'JSEOF'
const fs = require("fs");
const path = require("path");
const stateDir = process.env.OPENCLAW_STATE_DIR;
if (!stateDir) {
  console.log("[railway-start] OPENCLAW_STATE_DIR not set, skipping config repair");
  process.exit(0);
}
const configPath = path.join(stateDir, "openclaw.json");
let cfg = {};
let dirty = false;

if (fs.existsSync(configPath)) {
  try {
    const raw = fs.readFileSync(configPath, "utf8");
    cfg = JSON.parse(raw);
  } catch (e) {
    console.log("[railway-start] Failed to parse existing config, starting fresh");
    cfg = {};
    dirty = true;
  }
} else {
  console.log("[railway-start] No config file at", configPath, "— creating new one");
  dirty = true;
}

try {

  // Repair gateway.auth.mode if it holds an invalid value.
  const validModes = ["token", "password", "trusted-proxy"];
  const mode = cfg && cfg.gateway && cfg.gateway.auth && cfg.gateway.auth.mode;
  if (mode && !validModes.includes(mode)) {
    console.log("[railway-start] Removing invalid gateway.auth.mode:", mode);
    delete cfg.gateway.auth.mode;
    dirty = true;
  } else if (fs.existsSync(configPath)) {
    console.log("[railway-start] Config OK (gateway.auth.mode:", mode || "unset", ")");
  }

  // Ensure gateway.controlUi.allowInsecureAuth is true so the Control UI can
  // authenticate via shared secret alone (no device-token pairing required).
  // Railway serves over plain HTTP, so this flag must be set to avoid
  // device_token_mismatch errors after redeploys.
  if (!cfg.gateway) cfg.gateway = {};
  if (!cfg.gateway.controlUi) cfg.gateway.controlUi = {};
  if (cfg.gateway.controlUi.allowInsecureAuth !== true) {
    console.log("[railway-start] Setting gateway.controlUi.allowInsecureAuth = true");
    cfg.gateway.controlUi.allowInsecureAuth = true;
    dirty = true;
  } else {
    console.log("[railway-start] gateway.controlUi.allowInsecureAuth already true");
  }

  // Ensure gateway.controlUi.dangerouslyDisableDeviceAuth is true to disable
  // device authentication on the Control UI for Railway deployments.
  if (cfg.gateway.controlUi.dangerouslyDisableDeviceAuth !== true) {
    console.log("[railway-start] Setting gateway.controlUi.dangerouslyDisableDeviceAuth = true");
    cfg.gateway.controlUi.dangerouslyDisableDeviceAuth = true;
    dirty = true;
  } else {
    console.log("[railway-start] gateway.controlUi.dangerouslyDisableDeviceAuth already true");
  }

  // Ensure gateway.controlUi.allowedOrigins includes the Railway public HTTPS origin.
  // RAILWAY_PUBLIC_DOMAIN is set automatically by Railway (e.g. openclaw-production-da81.up.railway.app).
  // Without this, the gateway's origin check rejects the browser WebSocket and closes with 1008.
  const railwayDomain = process.env.RAILWAY_PUBLIC_DOMAIN?.trim();
  if (railwayDomain) {
    const expectedOrigin = `https://${railwayDomain}`;
    const existing = cfg.gateway.controlUi.allowedOrigins;
    if (!Array.isArray(existing) || !existing.includes(expectedOrigin)) {
      console.log("[railway-start] Setting gateway.controlUi.allowedOrigins =", [expectedOrigin]);
      cfg.gateway.controlUi.allowedOrigins = [expectedOrigin];
      dirty = true;
    } else {
      console.log("[railway-start] gateway.controlUi.allowedOrigins already includes", expectedOrigin);
    }
  } else {
    console.log("[railway-start] RAILWAY_PUBLIC_DOMAIN not set, skipping allowedOrigins config");
  }

  // Bootstrap ZAI as default model provider when ZAI_API_KEY is set.
  // Idempotent: only writes if the value is not already set to the ZAI model.
  const zaiModel = "zai/glm-4.6";
  // Future-proof stub for vision model — uncomment when ready:
  // const zaiVisionModel = "zai/glm-4.6v-flash";
  if (process.env.ZAI_API_KEY) {
    if (!cfg.agents) cfg.agents = {};
    if (!cfg.agents.defaults) cfg.agents.defaults = {};
    if (!cfg.agents.defaults.model) cfg.agents.defaults.model = {};
    if (cfg.agents.defaults.model.primary !== zaiModel) {
      console.log("[railway-start] Setting agents.defaults.model.primary =", zaiModel);
      cfg.agents.defaults.model.primary = zaiModel;
      dirty = true;
    } else {
      console.log("[railway-start] agents.defaults.model.primary already set to ZAI model");
    }
  }

  // Wire Meutia persona: set agents.defaults.workspace to the meutia workspace dir,
  // and ensure the default agent entry has the Meutia identity (name + emoji).
  // The workspace files are bundled in meutia-workspace/ inside the openclaw repo
  // and synced to /data/openclaw/meutia-workspace/ at startup (see shell block below).
  const meutiaWorkspaceDir = "/data/openclaw/meutia-workspace";
  if (!cfg.agents) cfg.agents = {};
  if (!cfg.agents.defaults) cfg.agents.defaults = {};
  if (cfg.agents.defaults.workspace !== meutiaWorkspaceDir) {
    console.log("[railway-start] Setting agents.defaults.workspace =", meutiaWorkspaceDir);
    cfg.agents.defaults.workspace = meutiaWorkspaceDir;
    dirty = true;
  } else {
    console.log("[railway-start] agents.defaults.workspace already set to meutia workspace");
  }

  // Set Meutia identity on the first agent list entry (or the defaults-level identity).
  // Using agents.list with a single default agent entry.
  if (!cfg.agents.list || cfg.agents.list.length === 0) {
    cfg.agents.list = [{ id: "main", default: true }];
    dirty = true;
  }
  const mainAgent = cfg.agents.list[0];
  if (!mainAgent.identity) mainAgent.identity = {};
  if (mainAgent.identity.name !== "Meutia" || mainAgent.identity.emoji !== "🌸") {
    console.log("[railway-start] Setting agent identity: Meutia 🌸");
    mainAgent.identity.name = "Meutia";
    mainAgent.identity.emoji = "🌸";
    dirty = true;
  } else {
    console.log("[railway-start] Agent identity already Meutia 🌸");
  }

  // Sync TELEGRAM_BOT_TOKEN env var into channels.telegram.botToken so the env var
  // always wins over any stale token persisted in openclaw.json on the /data volume.
  // This prevents 409 Conflict errors caused by leftover tokens from previous bot accounts.
  const envTelegramToken = process.env.TELEGRAM_BOT_TOKEN?.trim();
  if (envTelegramToken) {
    if (!cfg.channels) cfg.channels = {};
    if (!cfg.channels.telegram) cfg.channels.telegram = {};
    if (cfg.channels.telegram.botToken !== envTelegramToken) {
      console.log("[railway-start] Syncing channels.telegram.botToken from TELEGRAM_BOT_TOKEN env var");
      cfg.channels.telegram.botToken = envTelegramToken;
      dirty = true;
    } else {
      console.log("[railway-start] channels.telegram.botToken already matches TELEGRAM_BOT_TOKEN env var");
    }
  }

  // Open DMs: allow all senders without pairing requirement
  if (!cfg.channels) cfg.channels = {};
  if (!cfg.channels.telegram) cfg.channels.telegram = {};
  if (cfg.channels.telegram.dmPolicy !== "open") {
    console.log("[railway-start] Setting channels.telegram.dmPolicy = open");
    cfg.channels.telegram.dmPolicy = "open";
    dirty = true;
  } else {
    console.log("[railway-start] channels.telegram.dmPolicy already open");
  }
  if (!Array.isArray(cfg.channels.telegram.allowFrom) || !cfg.channels.telegram.allowFrom.includes("*")) {
    console.log("[railway-start] Setting channels.telegram.allowFrom = [*]");
    cfg.channels.telegram.allowFrom = ["*"];
    dirty = true;
  } else {
    console.log("[railway-start] channels.telegram.allowFrom already open");
  }

  // Suppress HEARTBEAT_OK delivery to Telegram — showOk=true causes the literal
  // "HEARTBEAT_OK" string to be sent to the user whenever there are no active tasks.
  // Default is already false, but the Control UI can toggle it on — force it off here.
  if (!cfg.channels.telegram.heartbeat) cfg.channels.telegram.heartbeat = {};
  if (cfg.channels.telegram.heartbeat.showOk !== false) {
    console.log("[railway-start] Setting channels.telegram.heartbeat.showOk = false");
    cfg.channels.telegram.heartbeat.showOk = false;
    dirty = true;
  } else {
    console.log("[railway-start] channels.telegram.heartbeat.showOk already false");
  }

  // Webhook mode: if TELEGRAM_WEBHOOK_URL is set, configure webhook instead of polling
  const webhookUrl = process.env.TELEGRAM_WEBHOOK_URL;
  const webhookSecret = process.env.TELEGRAM_WEBHOOK_SECRET;
  if (webhookUrl) {
    if (cfg.channels.telegram.webhookUrl !== webhookUrl) {
      console.log("[railway-start] Setting channels.telegram.webhookUrl = " + webhookUrl);
      cfg.channels.telegram.webhookUrl = webhookUrl;
      dirty = true;
    } else {
      console.log("[railway-start] channels.telegram.webhookUrl already set");
    }
    if (webhookSecret && cfg.channels.telegram.webhookSecret !== webhookSecret) {
      console.log("[railway-start] Setting channels.telegram.webhookSecret");
      cfg.channels.telegram.webhookSecret = webhookSecret;
      dirty = true;
    }
    if (cfg.channels.telegram.webhookPath !== "/telegram/webhook") {
      console.log("[railway-start] Setting channels.telegram.webhookPath = /telegram/webhook");
      cfg.channels.telegram.webhookPath = "/telegram/webhook";
      dirty = true;
    } else {
      console.log("[railway-start] channels.telegram.webhookPath already set");
    }
  }

  // Enable Microsoft Teams channel when MSTEAMS_APP_ID env var is set.
  // Credentials (appId/appPassword/tenantId) are read directly from env vars
  // by the msteams plugin — no need to embed them in the config file.
  const msteamsAppId = process.env.MSTEAMS_APP_ID?.trim();
  if (msteamsAppId) {
    if (!cfg.channels) cfg.channels = {};
    if (!cfg.channels.msteams) cfg.channels.msteams = {};
    if (cfg.channels.msteams.enabled !== true) {
      console.log("[railway-start] Enabling channels.msteams");
      cfg.channels.msteams.enabled = true;
      dirty = true;
    }
    // Open DMs so Meutia responds to anyone who messages the bot directly.
    const msteamsDmPolicy = process.env.MSTEAMS_DM_POLICY || "open";
    if (cfg.channels.msteams.dmPolicy !== msteamsDmPolicy) {
      console.log("[railway-start] Setting channels.msteams.dmPolicy =", msteamsDmPolicy);
      cfg.channels.msteams.dmPolicy = msteamsDmPolicy;
      dirty = true;
    }
    if (!Array.isArray(cfg.channels.msteams.allowFrom) || !cfg.channels.msteams.allowFrom.includes("*")) {
      console.log("[railway-start] Setting channels.msteams.allowFrom = [*]");
      cfg.channels.msteams.allowFrom = ["*"];
      dirty = true;
    }
    // Allow group channels (teams/channels) — set groupPolicy to open.
    const msteamsGroupPolicy = process.env.MSTEAMS_GROUP_POLICY || "open";
    if (cfg.channels.msteams.groupPolicy !== msteamsGroupPolicy) {
      console.log("[railway-start] Setting channels.msteams.groupPolicy =", msteamsGroupPolicy);
      cfg.channels.msteams.groupPolicy = msteamsGroupPolicy;
      dirty = true;
    }
  } else if (fs.existsSync(configPath)) {
    console.log("[railway-start] MSTEAMS_APP_ID not set, skipping MS Teams config");
  }

  // Enable OpenClaw hooks (HTTP webhook inbound + AgentOS integration).
  // Requires OPENCLAW_HOOKS_ENABLED=true + OPENCLAW_HOOKS_TOKEN env vars.
  if (process.env.OPENCLAW_HOOKS_ENABLED === "true") {
    if (!cfg.hooks) cfg.hooks = {};
    cfg.hooks.enabled = true;
    cfg.hooks.token = process.env.OPENCLAW_HOOKS_TOKEN;
    cfg.hooks.path = process.env.OPENCLAW_HOOKS_PATH || "/hooks";
    cfg.hooks.defaultSessionKey = "hook:agentOS";
    cfg.hooks.allowRequestSessionKey = false;
    cfg.hooks.allowedSessionKeyPrefixes = ["hook:"];
    cfg.hooks.allowedAgentIds = ["*"];
    dirty = true;
  } else if (fs.existsSync(configPath)) {
    console.log("[railway-start] Hooks not enabled (OPENCLAW_HOOKS_ENABLED not true)");
  }

  if (dirty) {
    // Stamp meta.lastTouchedAt so downstream readers can detect stale configs.
    if (!cfg.meta) cfg.meta = {};
    cfg.meta.lastTouchedAt = new Date().toISOString();
    // Write to a temp file in the same directory then rename over the original.
    // rename(2) only needs write permission on the directory, not the file.
    const tmpPath = path.join(stateDir, ".openclaw.json.tmp");
    fs.writeFileSync(tmpPath, JSON.stringify(cfg, null, 2));
    fs.renameSync(tmpPath, configPath);
    console.log("[railway-start] Config patched at", configPath);
  }
} catch (err) {
  console.error("[railway-start] Failed to patch config:", err.message);
  // Non-fatal — if we can't fix it, try starting anyway.
  // The gateway's --allow-unconfigured flag may tolerate a missing/bad config.
  // If it cannot start, run: railway run node openclaw.mjs doctor --fix
}
JSEOF

# Sync Meutia persona workspace files to the persistent data volume.
# Files are bundled in meutia-workspace/ inside the openclaw repo (available in the Docker image).
# They are copied to /data/openclaw/meutia-workspace/ so openclaw can read them at runtime.
MEUTIA_SRC="$(dirname "$0")/../meutia-workspace"
MEUTIA_DST="/data/openclaw/meutia-workspace"
if [ -d "$MEUTIA_SRC" ]; then
  mkdir -p "$MEUTIA_DST" 2>/dev/null || true
  cp -n "$MEUTIA_SRC"/*.md "$MEUTIA_DST/" 2>/dev/null || true
  echo "[railway-start] Meutia workspace synced: $MEUTIA_DST"
else
  echo "[railway-start] WARNING: meutia-workspace source dir not found at $MEUTIA_SRC — skipping sync"
fi

# Sync Johnny persona workspace files to the persistent data volume.
JOHNNY_SRC="$(dirname "$0")/../johnny-workspace"
JOHNNY_DST="/data/openclaw/johnny-workspace"
if [ -d "$JOHNNY_SRC" ]; then
  mkdir -p "$JOHNNY_DST" 2>/dev/null || true
  cp -n "$JOHNNY_SRC"/*.md "$JOHNNY_DST/" 2>/dev/null || true
  echo "[railway-start] Johnny workspace synced: $JOHNNY_DST"
else
  echo "[railway-start] WARNING: johnny-workspace source dir not found at $JOHNNY_SRC — skipping sync"
fi

# Install Python dependencies for managed skills
echo "Installing skill Python dependencies..."
# Bootstrap pip if not available (Alpine strips ensurepip)
if ! python3 -c "import pip" 2>/dev/null; then
  echo "  pip not found — bootstrapping via get-pip.py..."
  curl -sS https://bootstrap.pypa.io/get-pip.py | python3 -q 2>&1 || echo "  WARNING: pip bootstrap failed"
fi
find /data/openclaw/skills -name "requirements.txt" -not -path "*/.imap-smtp-email.bak/*" | while read req; do
  echo "  Installing: $req"
  python3 -m pip install -q -r "$req" 2>&1 || echo "  WARNING: pip install failed for $req"
done

# Start the reverse proxy on Railway's public PORT.
# It forwards /api/messages → msteams plugin (3978) and everything else → gateway (18789).
node /app/scripts/railway-proxy.cjs &

exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port 18789
