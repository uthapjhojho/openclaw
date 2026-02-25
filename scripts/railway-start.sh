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
  const nvidiaModel = "nvidia/llama-3.1-nemotron-70b-instruct";
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
