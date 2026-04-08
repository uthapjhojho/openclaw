#!/usr/bin/env node
// Railway reverse proxy
// Listens on $PORT (Railway's public port) and forwards:
//   /api/messages  → msteams plugin at 127.0.0.1:3978
//   everything else → gateway at 127.0.0.1:18789
// Supports both HTTP and WebSocket (upgrade) proxying.
"use strict";

const http = require("http");
const net = require("net");

const PUBLIC_PORT = parseInt(process.env.PORT || "3000", 10);
const GATEWAY_PORT = 18789;
const MSTEAMS_PORT = 3978;

function targetPort(url) {
  return url && url.startsWith("/api/messages") ? MSTEAMS_PORT : GATEWAY_PORT;
}

function forward(req, res, port) {
  const options = {
    hostname: "127.0.0.1",
    port,
    path: req.url,
    method: req.method,
    headers: req.headers,
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
server.on("upgrade", (req, clientSocket, head) => {
  const port = targetPort(req.url);
  const upstream = net.connect(port, "127.0.0.1", () => {
    // Replay the HTTP upgrade request to the upstream.
    const requestLine = `${req.method} ${req.url} HTTP/1.1\r\n`;
    const headers = Object.entries(req.headers)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\r\n");
    upstream.write(`${requestLine}${headers}\r\n\r\n`);
    if (head && head.length) upstream.write(head);
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
    `[railway-proxy] listening on port ${PUBLIC_PORT} → gateway:${GATEWAY_PORT}, msteams:${MSTEAMS_PORT}`
  );
});

server.on("error", (err) => {
  console.error("[railway-proxy] server error:", err.message);
  process.exit(1);
});
