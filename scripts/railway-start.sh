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
if (!fs.existsSync(configPath)) {
  console.log("[railway-start] No config file at", configPath, "— skipping repair");
  process.exit(0);
}
try {
  const raw = fs.readFileSync(configPath, "utf8");
  const cfg = JSON.parse(raw);
  let dirty = false;

  // Repair gateway.auth.mode if it holds an invalid value.
  const validModes = ["token", "password", "trusted-proxy"];
  const mode = cfg && cfg.gateway && cfg.gateway.auth && cfg.gateway.auth.mode;
  if (mode && !validModes.includes(mode)) {
    console.log("[railway-start] Removing invalid gateway.auth.mode:", mode);
    delete cfg.gateway.auth.mode;
    dirty = true;
  } else {
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

  if (dirty) {
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

exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port "$PORT"
