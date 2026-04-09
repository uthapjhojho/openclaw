#!/usr/bin/env node
// Railway reverse proxy
// Listens on $PORT (Railway's public port) and forwards:
//   /api/messages  → msteams plugin at 127.0.0.1:3978
//   everything else → gateway at 127.0.0.1:18789
// Supports both HTTP and WebSocket (upgrade) proxying.
//
// Forwarded-IP headers (x-forwarded-for, x-real-ip, etc.) are stripped so
// the gateway sees every connection as a local loopback request and allows
// Control UI access without interactive pairing (gateway.controlUi.allowInsecureAuth=true).
"use strict";

const http = require("http");
const net = require("net");

const PUBLIC_PORT = parseInt(process.env.PORT || "3000", 10);
const GATEWAY_PORT = 18789;
const MSTEAMS_PORT = 3978;

// Headers that would make the gateway treat the connection as remote.
const FORWARDED_HEADERS = new Set([
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-forwarded-host",
  "x-real-ip",
  "x-envoy-original-dst-host",
  "forwarded",
]);

function cleanHeaders(headers) {
  const out = {};
  for (const [k, v] of Object.entries(headers)) {
    if (!FORWARDED_HEADERS.has(k.toLowerCase())) {
      out[k] = v;
    }
  }
  return out;
}

function targetPort(url) {
  return url && url.startsWith("/api/messages") ? MSTEAMS_PORT : GATEWAY_PORT;
}

function forward(req, res, port) {
  const options = {
    hostname: "127.0.0.1",
    port,
    path: req.url,
    method: req.method,
    headers: cleanHeaders(req.headers),
  };

  const proxy = http.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxy.on("error", (err) => {
    console.error(`[railway-proxy] upstream error (port ${port}):`, err.message);
    if (!res.headersSent) {
      res.writeHead(502, { "content-type": "text/plain" });
    }
    res.end(`Bad Gateway: ${err.message}`);
  });

  req.pipe(proxy, { end: true });
}

const server = http.createServer((req, res) => {
  forward(req, res, targetPort(req.url));
});

// WebSocket proxy: tunnel the raw TCP connection to the upstream.
// Forwarded headers are stripped so the gateway treats the connection as local.
server.on("upgrade", (req, clientSocket, head) => {
  const port = targetPort(req.url);
  const cleaned = cleanHeaders(req.headers);

  const upstream = net.connect(port, "127.0.0.1", () => {
    const requestLine = `${req.method} ${req.url} HTTP/1.1\r\n`;
    const headerStr = Object.entries(cleaned)
      .map(([k, v]) => `${k}: ${String(v)}`)
      .join("\r\n");
    upstream.write(`${requestLine}${headerStr}\r\n\r\n`);
    if (head && head.length) {
      upstream.write(head);
    }
    upstream.pipe(clientSocket);
    clientSocket.pipe(upstream);
  });

  upstream.on("error", (err) => {
    console.error(`[railway-proxy] ws upstream error (port ${port}):`, err.message);
    clientSocket.destroy();
  });

  clientSocket.on("error", () => upstream.destroy());
});

server.listen(PUBLIC_PORT, "0.0.0.0", () => {
  console.log(
    `[railway-proxy] listening on port ${PUBLIC_PORT} → gateway:${GATEWAY_PORT}, msteams:${MSTEAMS_PORT}`,
  );
});

server.on("error", (err) => {
  console.error("[railway-proxy] server error:", err.message);
  process.exit(1);
});
