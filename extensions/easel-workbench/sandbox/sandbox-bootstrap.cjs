"use strict";

// A startup tripwire, not proof of isolation. The launcher must clear the
// environment before the preload is installed, and the runtime must be trusted.
const fs = require("node:fs");
let status = "";
try { status = fs.readFileSync("/proc/self/status", "utf8"); } catch { /* fail closed */ }
const installed = process.env.CONTENTOPS_SECCOMP_INSTALLED === "1";
delete process.env.CONTENTOPS_SECCOMP_INSTALLED;
if (!installed || !/^Seccomp:\s*2\s*$/m.test(status)) {
  process.stderr.write("candidate sandbox filter was not confirmed at startup\n");
  process.exit(126);
}
