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

  // Bootstrap NVIDIA as default model provider when NVIDIA_API_KEY is set.
  // Idempotent: only writes if the value is not already set to the NVIDIA model.
  const nvidiaModel = "nvidia/meta/llama-3.3-70b-instruct";
  if (process.env.NVIDIA_API_KEY) {
    if (!cfg.agents) cfg.agents = {};
    if (!cfg.agents.defaults) cfg.agents.defaults = {};
    if (!cfg.agents.defaults.model) cfg.agents.defaults.model = {};
    if (cfg.agents.defaults.model.primary !== nvidiaModel) {
      console.log("[railway-start] Setting agents.defaults.model.primary =", nvidiaModel);
      cfg.agents.defaults.model.primary = nvidiaModel;
      dirty = true;
    } else {
      console.log("[railway-start] agents.defaults.model.primary already set to NVIDIA model");
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
  mkdir -p "$MEUTIA_DST"
  cp -f "$MEUTIA_SRC"/*.md "$MEUTIA_DST/"
  echo "[railway-start] Meutia workspace synced: $MEUTIA_DST"
else
  echo "[railway-start] WARNING: meutia-workspace source dir not found at $MEUTIA_SRC — skipping sync"
fi

exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port "$PORT"
