"use strict";

// Candidate stdout capture for OpenClaw's JSON result. This is not an OS
// isolation boundary and cannot establish the provenance of output bytes.
// The future launcher must supply a project-local path in a verified sandbox.
const fs = require("node:fs");
const target = process.env.CONTENTOPS_CAPTURE_FILE;
if (!target) throw new Error("CONTENTOPS_CAPTURE_FILE is required");
const fd = fs.openSync(target, "wx", 0o600);
const limit = 2 * 1024 * 1024;
let size = 0;
let closed = false;

process.stdout.write = function (chunk, encoding, callback) {
  if (typeof encoding === "function") {
    callback = encoding;
    encoding = undefined;
  }
  const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk, encoding);
  if (closed || size + bytes.length > limit) {
    process.exitCode = 1;
    throw new Error("candidate output exceeds its limit or capture is closed");
  }
  let written = 0;
  while (written < bytes.length) {
    const count = fs.writeSync(fd, bytes, written, bytes.length - written);
    if (count <= 0) throw new Error("candidate output write failed");
    written += count;
  }
  size += bytes.length;
  if (typeof callback === "function") process.nextTick(callback);
  return true;
};

// Avoid forwarding diagnostic output, which may contain host-specific details.
process.stderr.write = function (_chunk, encoding, callback) {
  if (typeof encoding === "function") callback = encoding;
  if (typeof callback === "function") process.nextTick(callback);
  return true;
};

process.once("exit", () => {
  if (!closed) {
    closed = true;
    fs.closeSync(fd);
  }
});
