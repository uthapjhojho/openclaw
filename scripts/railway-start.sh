#!/bin/sh
# railway-start.sh — Pre-boot repair + gateway start for Railway deployments.
#
# Runs before the gateway to patch known schema-breaking values in
# openclaw.json that would prevent the server from starting.
# Safe to run on every boot; no-ops when the config is already valid.

set -e

# Ensure /data/openclaw is owned by the openclaw user — persistent disk may have stale root-owned dirs
if [ -d "/data/openclaw" ]; then
  chown -R openclaw /data/openclaw 2>/dev/null || chmod -R 777 /data/openclaw 2>/dev/null || true
  echo "[railway-start] Fixed /data/openclaw ownership"
fi

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

  // Sync OPENCLAW_GATEWAY_TOKEN → gateway.auth.token
  const envGatewayToken = process.env.OPENCLAW_GATEWAY_TOKEN?.trim();
  if (envGatewayToken) {
    if (!cfg.gateway) cfg.gateway = {};
    if (!cfg.gateway.auth) cfg.gateway.auth = {};
    if (cfg.gateway.auth.token !== envGatewayToken) {
      console.log("[railway-start] Syncing gateway.auth.token from OPENCLAW_GATEWAY_TOKEN env var");
      cfg.gateway.auth.token = envGatewayToken;
      dirty = true;
    } else {
      console.log("[railway-start] gateway.auth.token already matches OPENCLAW_GATEWAY_TOKEN env var");
    }
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

  // Bootstrap model provider with fallbacks.
  // Priority: GROQ (if key set) > NVIDIA (if key set) > ZAI (legacy fallback).
  // Idempotent: only writes if the value differs from current config.
  let primaryModel = null;
  let fallbackModels = [];

  if (process.env.GROQ_API_KEY) {
    primaryModel = "groq/meta/llama-3.3-70b-versatile";
    if (process.env.NVIDIA_API_KEY) {
      fallbackModels.push("nvidia/llama-3.3-70b-instruct");
    }
    console.log("[railway-start] GROQ_API_KEY detected — using Llama 3.3 70B as primary model");
  } else if (process.env.NVIDIA_API_KEY) {
    primaryModel = "nvidia/llama-3.3-70b-instruct";
    console.log("[railway-start] NVIDIA_API_KEY detected — using NVIDIA as primary model");
  } else if (process.env.ZAI_API_KEY) {
    primaryModel = "zai/glm-4.6";
    console.log("[railway-start] ZAI_API_KEY detected — using ZAI as fallback model");
  }

  if (primaryModel) {
    if (!cfg.agents) cfg.agents = {};
    if (!cfg.agents.defaults) cfg.agents.defaults = {};
    if (!cfg.agents.defaults.model) cfg.agents.defaults.model = {};

    const needsUpdate =
      cfg.agents.defaults.model.primary !== primaryModel ||
      JSON.stringify(cfg.agents.defaults.model.fallbacks || []) !== JSON.stringify(fallbackModels);

    if (needsUpdate) {
      console.log("[railway-start] Setting agents.defaults.model.primary =", primaryModel);
      cfg.agents.defaults.model.primary = primaryModel;
      if (fallbackModels.length > 0) {
        console.log("[railway-start] Setting agents.defaults.model.fallbacks =", fallbackModels);
        cfg.agents.defaults.model.fallbacks = fallbackModels;
      } else if (cfg.agents.defaults.model.fallbacks) {
        delete cfg.agents.defaults.model.fallbacks;
      }
      dirty = true;
    } else {
      console.log("[railway-start] agents.defaults.model already correctly configured");
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

  // Fix groupPolicy=allowlist with empty allowFrom — the gateway doctor rejects this
  // combination and exits(1), preventing startup. Reset to "open" so all group messages
  // are accepted (same policy as allowFrom=[*] above).
  const groupAllowFrom = cfg.channels.telegram.groupAllowFrom;
  if (
    cfg.channels.telegram.groupPolicy === "allowlist" &&
    (!Array.isArray(groupAllowFrom) || groupAllowFrom.length === 0)
  ) {
    console.log("[railway-start] Resetting channels.telegram.groupPolicy to open (allowlist with empty groupAllowFrom would block startup)");
    cfg.channels.telegram.groupPolicy = "open";
    dirty = true;
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

  // Configure cron job limits and session retention to reduce memory growth.
  // Failed cron runs can spawn orphaned sessions; limit concurrency and clean old sessions.
  if (!cfg.cron) cfg.cron = {};
  if (cfg.cron.maxConcurrentRuns !== 1) {
    console.log("[railway-start] Setting cron.maxConcurrentRuns = 1");
    cfg.cron.maxConcurrentRuns = 1;
    dirty = true;
  }
  if (cfg.cron.sessionRetention !== "4h") {
    console.log("[railway-start] Setting cron.sessionRetention = 4h");
    cfg.cron.sessionRetention = "4h";
    dirty = true;
  }
  if (!cfg.cron.runLog) cfg.cron.runLog = {};
  if (cfg.cron.runLog.maxBytes !== "1000000") {
    console.log("[railway-start] Setting cron.runLog.maxBytes = 1000000");
    cfg.cron.runLog.maxBytes = 1000000;
    dirty = true;
  }
  if (cfg.cron.runLog.keepLines !== 1000) {
    console.log("[railway-start] Setting cron.runLog.keepLines = 1000");
    cfg.cron.runLog.keepLines = 1000;
    dirty = true;
  }

  // Configure ACP session limits if ACP is being used (for managed skills / agents).
  if (!cfg.acp) cfg.acp = {};
  if (cfg.acp.maxConcurrentSessions !== 2) {
    console.log("[railway-start] Setting acp.maxConcurrentSessions = 2");
    cfg.acp.maxConcurrentSessions = 2;
    dirty = true;
  }

  // Remove stale qwen-portal-auth plugin entry if it exists.
  if (cfg.plugins && cfg.plugins.entries && cfg.plugins.entries["qwen-portal-auth"]) {
    console.log("[railway-start] Removing stale plugins.entries.qwen-portal-auth");
    delete cfg.plugins.entries["qwen-portal-auth"];
    dirty = true;
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

# Patch missing workspace templates that may be absent due to stale Docker cache.
# Some templates (IDENTITY.md, USER.md) may be missing from /app/docs/reference/templates/
# if the image was built from a cached layer that predates their addition.
# Since /app is writable on Railway, copy any missing templates from node_modules fallback
# or recreate them inline so ensureAgentWorkspace does not fail at runtime.
TEMPLATES_DST="/app/docs/reference/templates"
mkdir -p "$TEMPLATES_DST" 2>/dev/null || true

if [ ! -f "$TEMPLATES_DST/IDENTITY.md" ]; then
  echo "[railway-start] IDENTITY.md missing from templates — writing fallback"
  cat > "$TEMPLATES_DST/IDENTITY.md" << 'IDENTITY_EOF'
---
summary: "Agent identity record"
read_when:
  - Bootstrapping a workspace manually
---

# IDENTITY.md - Who Am I?

_Fill this in during your first conversation. Make it yours._

- **Name:**
  _(pick something you like)_
- **Creature:**
  _(AI? robot? familiar? ghost in the machine? something weirder?)_
- **Vibe:**
  _(how do you come across? sharp? warm? chaotic? calm?)_
- **Emoji:**
  _(your signature — pick one that feels right)_
- **Avatar:**
  _(workspace-relative path, http(s) URL, or data URI)_

---

This isn't just metadata. It's the start of figuring out who you are.

Notes:

- Save this file at the workspace root as `IDENTITY.md`.
- For avatars, use a workspace-relative path like `avatars/openclaw.png`.
IDENTITY_EOF
else
  echo "[railway-start] IDENTITY.md already present"
fi

if [ ! -f "$TEMPLATES_DST/USER.md" ]; then
  echo "[railway-start] USER.md missing from templates — writing fallback"
  cat > "$TEMPLATES_DST/USER.md" << 'USER_EOF'
---
summary: "User profile record"
read_when:
  - Bootstrapping a workspace manually
---

# USER.md - About Your Human

_Learn about the person you're helping. Update this as you go._

- **Name:**
- **What to call them:**
- **Pronouns:** _(optional)_
- **Timezone:**
- **Notes:**

## Context

_(What do they care about? What projects are they working on? What annoys them? What makes them laugh? Build this over time.)_

---

The more you know, the better you can help. But remember — you're learning about a person, not building a dossier. Respect the difference.
USER_EOF
else
  echo "[railway-start] USER.md already present"
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
  python3 -m pip install -q --break-system-packages -r "$req" 2>&1 || echo "  WARNING: pip install failed for $req"
done

# Start the reverse proxy on Railway's public PORT.
# It forwards /api/messages → msteams plugin (3978) and everything else → gateway (18789).
node /app/scripts/railway-proxy.cjs &

# On Railway, SIGUSR1-triggered self-restarts call process.exit(0). Railway treats
# exit-0 as a clean shutdown and does NOT restart the container, so the gateway dies
# permanently. Wrap in a restart loop so any exit (clean or crash) relaunches it.
if [ -n "$RAILWAY_ENVIRONMENT" ]; then
  echo "[railway-start] Railway detected — gateway will auto-restart on exit"
  while true; do
    node openclaw.mjs gateway --allow-unconfigured --bind lan --port 18789 && exit_code=$? || exit_code=$?
    echo "[railway-start] Gateway exited ($exit_code), restarting in 3s..."
    sleep 3
  done
else
  exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port 18789
fi
