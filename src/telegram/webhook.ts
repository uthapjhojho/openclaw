import type { IncomingMessage, ServerResponse } from "node:http";
import { webhookCallback } from "grammy";
import { createServer } from "node:http";
import type { OpenClawConfig } from "../config/config.js";
import type { RuntimeEnv } from "../runtime.js";
import { isDiagnosticsEnabled } from "../infra/diagnostic-events.js";
import { formatErrorMessage } from "../infra/errors.js";
import { installRequestBodyLimitGuard } from "../infra/http-body.js";
import {
  logWebhookError,
  logWebhookProcessed,
  logWebhookReceived,
  startDiagnosticHeartbeat,
  stopDiagnosticHeartbeat,
} from "../logging/diagnostic.js";
import { registerPluginHttpRoute } from "../plugins/http-registry.js";
import { defaultRuntime } from "../runtime.js";
import { resolveTelegramAllowedUpdates } from "./allowed-updates.js";
import { withTelegramApiErrorLogging } from "./api-logging.js";
import { createTelegramBot } from "./bot.js";

const TELEGRAM_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024;
const TELEGRAM_WEBHOOK_BODY_TIMEOUT_MS = 30_000;
const TELEGRAM_WEBHOOK_CALLBACK_TIMEOUT_MS = 10_000;

export async function startTelegramWebhook(opts: {
  token: string;
  accountId?: string;
  config?: OpenClawConfig;
  path?: string;
  port?: number;
  host?: string;
  secret?: string;
  runtime?: RuntimeEnv;
  fetch?: typeof fetch;
  abortSignal?: AbortSignal;
  healthPath?: string;
  publicUrl?: string;
  /**
   * When true, registers the webhook handler via the gateway plugin HTTP route
   * system instead of starting a standalone HTTP server. Use this when running
   * inside the gateway process (e.g. Railway) so the handler is reachable on
   * the same port as the gateway without requiring a separate listener.
   */
  useGatewayRouter?: boolean;
}) {
  const path = opts.path ?? "/telegram-webhook";
  const healthPath = opts.healthPath ?? "/healthz";
  const port = opts.port ?? 8787;
  const host = opts.host ?? "127.0.0.1";
  const secret = typeof opts.secret === "string" ? opts.secret.trim() : "";
  if (!secret) {
    throw new Error(
      "Telegram webhook mode requires a non-empty secret token. " +
        "Set channels.telegram.webhookSecret in your config.",
    );
  }
  const runtime = opts.runtime ?? defaultRuntime;
  const diagnosticsEnabled = isDiagnosticsEnabled(opts.config);
  const bot = createTelegramBot({
    token: opts.token,
    runtime,
    proxyFetch: opts.fetch,
    config: opts.config,
    accountId: opts.accountId,
  });
  const handler = webhookCallback(bot, "http", {
    secretToken: secret,
    onTimeout: "return",
    timeoutMilliseconds: TELEGRAM_WEBHOOK_CALLBACK_TIMEOUT_MS,
  });

  if (diagnosticsEnabled) {
    startDiagnosticHeartbeat();
  }

  // Shared request handler for the webhook path — used by both the standalone
  // server mode and the gateway-router mode.
  const handleWebhookRequest = (req: IncomingMessage, res: ServerResponse) => {
    if (req.method !== "POST") {
      res.writeHead(405, { Allow: "POST" });
      res.end();
      return;
    }
    const startTime = Date.now();
    if (diagnosticsEnabled) {
      logWebhookReceived({ channel: "telegram", updateType: "telegram-post" });
    }
    const guard = installRequestBodyLimitGuard(req, res, {
      maxBytes: TELEGRAM_WEBHOOK_MAX_BODY_BYTES,
      timeoutMs: TELEGRAM_WEBHOOK_BODY_TIMEOUT_MS,
      responseFormat: "text",
    });
    if (guard.isTripped()) {
      return;
    }
    const handled = handler(req, res);
    if (handled && typeof handled.catch === "function") {
      void handled
        .then(() => {
          if (diagnosticsEnabled) {
            logWebhookProcessed({
              channel: "telegram",
              updateType: "telegram-post",
              durationMs: Date.now() - startTime,
            });
          }
        })
        .catch((err) => {
          if (guard.isTripped()) {
            return;
          }
          const errMsg = formatErrorMessage(err);
          if (diagnosticsEnabled) {
            logWebhookError({
              channel: "telegram",
              updateType: "telegram-post",
              error: errMsg,
            });
          }
          runtime.log?.(`webhook handler failed: ${errMsg}`);
          if (!res.headersSent) {
            res.writeHead(500);
          }
          res.end();
        })
        .finally(() => {
          guard.dispose();
        });
      return;
    }
    guard.dispose();
  };

  if (opts.useGatewayRouter) {
    // Gateway-router mode: register the handler with the plugin HTTP route
    // system so it is served on the same port as the gateway.  This avoids
    // the need for a separate listener and prevents the Control UI catch-all
    // from returning 405 for POST requests to the webhook path.
    const publicUrl = opts.publicUrl;
    if (!publicUrl) {
      throw new Error(
        "Telegram webhook gateway-router mode requires publicUrl " +
          "(set TELEGRAM_WEBHOOK_URL env var or channels.telegram.webhookUrl).",
      );
    }

    const unregister = registerPluginHttpRoute({
      path,
      pluginId: "telegram",
      accountId: opts.accountId,
      log: (msg) => runtime.log?.(msg),
      handler: handleWebhookRequest,
    });

    await withTelegramApiErrorLogging({
      operation: "setWebhook",
      runtime,
      fn: () =>
        bot.api.setWebhook(publicUrl, {
          secret_token: secret,
          allowed_updates: resolveTelegramAllowedUpdates(),
        }),
    });

    runtime.log?.(`telegram: webhook registered at ${path} (gateway router, public: ${publicUrl})`);

    const shutdown = () => {
      unregister();
      void bot.stop();
      if (diagnosticsEnabled) {
        stopDiagnosticHeartbeat();
      }
    };
    if (opts.abortSignal) {
      opts.abortSignal.addEventListener("abort", shutdown, { once: true });
    }

    // Keep the promise pending until aborted so the channel manager task stays alive.
    return new Promise<{ server: null; bot: typeof bot; stop: () => void }>((resolve) => {
      const done = () => resolve({ server: null, bot, stop: shutdown });
      if (opts.abortSignal?.aborted) {
        done();
      } else {
        opts.abortSignal?.addEventListener("abort", done, { once: true });
      }
    });
  }

  // Standalone-server mode (default): start a dedicated HTTP listener.
  const server = createServer((req, res) => {
    if (req.url === healthPath) {
      res.writeHead(200);
      res.end("ok");
      return;
    }
    if (req.url !== path || req.method !== "POST") {
      res.writeHead(404);
      res.end();
      return;
    }
    handleWebhookRequest(req, res);
  });

  const publicUrl =
    opts.publicUrl ?? `http://${host === "0.0.0.0" ? "localhost" : host}:${port}${path}`;

  await withTelegramApiErrorLogging({
    operation: "setWebhook",
    runtime,
    fn: () =>
      bot.api.setWebhook(publicUrl, {
        secret_token: secret,
        allowed_updates: resolveTelegramAllowedUpdates(),
      }),
  });

  await new Promise<void>((resolve) => server.listen(port, host, resolve));
  runtime.log?.(`webhook listening on ${publicUrl}`);

  const shutdown = () => {
    server.close();
    void bot.stop();
    if (diagnosticsEnabled) {
      stopDiagnosticHeartbeat();
    }
  };
  if (opts.abortSignal) {
    opts.abortSignal.addEventListener("abort", shutdown, { once: true });
  }

  return { server, bot, stop: shutdown };
}
