#!/usr/bin/env node
// Railway reverse proxy
// Listens on $PORT (Railway's public port) and forwards:
//   /api/messages  → msteams plugin at 127.0.0.1:3978
//   everything else → gateway at 127.0.0.1:18789
"use strict";

const http = require("http");

const PUBLIC_PORT = parseInt(process.env.PORT || "3000", 10);
const GATEWAY_PORT = 18789;
const MSTEAMS_PORT = 3978;

function forward(req, res, targetPort) {
  const options = {
    hostname: "127.0.0.1",
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: req.headers,
  };

  const proxy = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on("error", (err) => {
    console.error(`[railway-proxy] upstream error (port ${targetPort}):`, err.message);
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain" });
    }
    res.end(`Bad Gateway: ${err.message}`);
  });

  req.pipe(proxy, { end: true });
}

const server = http.createServer((req, res) => {
  if (req.url && req.url.startsWith("/api/messages")) {
    forward(req, res, MSTEAMS_PORT);
  } else {
    forward(req, res, GATEWAY_PORT);
  }
});

server.listen(PUBLIC_PORT, "0.0.0.0", () => {
  console.log(
    `[railway-proxy] listening on port ${PUBLIC_PORT} → gateway:${GATEWAY_PORT}, msteams:${MSTEAMS_PORT}`
  );
});

server.on("error", (err) => {
  console.error("[railway-proxy] server error:", err.message);
  process.exit(1);
});
