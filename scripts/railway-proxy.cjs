#!/usr/bin/env node
// railway-proxy.js — Reverse proxy for Railway deployments.
//
// Railway exposes one public port ($PORT). This proxy sits on $PORT and routes:
//   POST /api/messages  →  msteams plugin (localhost:3978)
//   everything else     →  OpenClaw gateway (localhost:18789)
//
// Start this before the gateway:
//   node scripts/railway-proxy.js &

"use strict";
const http = require("http");

const PUBLIC_PORT = parseInt(process.env.PORT || "8080", 10);
const GATEWAY_PORT = 18789;
const MSTEAMS_PORT = 3978;

function forward(req, res, targetPort) {
  const opts = {
    hostname: "127.0.0.1",
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `127.0.0.1:${targetPort}` },
  };
  const proxy = http.request(opts, (upstream) => {
    res.writeHead(upstream.statusCode, upstream.headers);
    upstream.pipe(res, { end: true });
  });
  proxy.on("error", (err) => {
    console.error(`[proxy] upstream error (port ${targetPort}):`, err.message);
    if (!res.headersSent) {
      res.writeHead(502);
      res.end("Bad Gateway");
    }
  });
  req.pipe(proxy, { end: true });
}

const server = http.createServer((req, res) => {
  // Bot Framework webhook endpoint → msteams plugin
  if (req.url === "/api/messages" || req.url?.startsWith("/api/messages?")) {
    forward(req, res, MSTEAMS_PORT);
  } else {
    forward(req, res, GATEWAY_PORT);
  }
});

// Forward WebSocket upgrade requests (needed for OpenClaw gateway dashboard and webchat).
// Without this handler, Node.js 13+ destroys the socket silently (browser sees code=1006).
server.on("upgrade", (req, socket, head) => {
  const targetPort =
    req.url === "/api/messages" || req.url?.startsWith("/api/messages?")
      ? MSTEAMS_PORT
      : GATEWAY_PORT;
  // Use RAILWAY_PUBLIC_DOMAIN as Host so the gateway sees the real public hostname.
  // Railway's internal routing may rewrite Host to 127.0.0.1:PORT before it reaches
  // this proxy — isLocalishHost() would then treat the browser as a loopback client,
  // causing the wrong auth path and a 1006 close. Fallback to req.headers.host for
  // non-Railway environments (local dev, etc.).
  const wsHost = process.env.RAILWAY_PUBLIC_DOMAIN ?? req.headers.host;
  const opts = {
    hostname: "127.0.0.1",
    port: targetPort,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: wsHost },
  };
  const proxy = http.request(opts);
  proxy.on("upgrade", (proxyRes, proxySocket, proxyHead) => {
    const statusLine = `HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n`;
    const headers = Object.entries(proxyRes.headers)
      .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : (v ?? "")}`)
      .join("\r\n");
    socket.write(`${statusLine}${headers}\r\n\r\n`);
    if (proxyHead && proxyHead.length) {
      proxySocket.unshift(proxyHead);
    }
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
    proxySocket.on("error", () => socket.destroy());
    socket.on("error", () => proxySocket.destroy());
  });
  proxy.on("error", (err) => {
    console.error(`[proxy] WebSocket upstream error (port ${targetPort}):`, err.message);
    socket.destroy();
  });
  if (head && head.length) {
    proxy.write(head);
  }
  proxy.end();
});

server.listen(PUBLIC_PORT, "0.0.0.0", () => {
  console.log(
    `[proxy] listening on ${PUBLIC_PORT} → /api/messages:${MSTEAMS_PORT} | rest:${GATEWAY_PORT}`,
  );
});
