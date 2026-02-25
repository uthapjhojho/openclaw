#!/bin/sh
# railway-start.sh — Pre-boot repair + gateway start for Railway deployments.
#
# Runs before the gateway to patch known schema-breaking values in
# openclaw.json that would prevent the server from starting.
# Safe to run on every boot; no-ops when the config is already valid.

set -e

CONFIG_FILE="${OPENCLAW_STATE_DIR}/openclaw.json"

# Repair gateway.auth.mode if it holds an invalid value.
# Valid values (from src/config/types.gateway.ts): token | password | trusted-proxy
node - <<'EOF'
const fs = require("fs");
const configPath = process.env.OPENCLAW_STATE_DIR + "/openclaw.json";
if (!fs.existsSync(configPath)) {
  process.exit(0);
}
try {
  const raw = fs.readFileSync(configPath, "utf8");
  const cfg = JSON.parse(raw);
  const validModes = ["token", "password", "trusted-proxy"];
  const mode = cfg && cfg.gateway && cfg.gateway.auth && cfg.gateway.auth.mode;
  if (mode && !validModes.includes(mode)) {
    console.log("[railway-start] Removing invalid gateway.auth.mode:", mode);
    delete cfg.gateway.auth.mode;
    fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2));
    console.log("[railway-start] Config patched at", configPath);
  } else {
    console.log("[railway-start] Config OK (gateway.auth.mode:", mode || "unset", ")");
  }
} catch (err) {
  console.error("[railway-start] Failed to patch config:", err.message);
  // Non-fatal — gateway will report the error itself on start.
}
EOF

exec node openclaw.mjs gateway --allow-unconfigured --bind lan --port "$PORT"
