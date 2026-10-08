// The restart policy: when the API process dies inside its container (a crash, an OOM kill), Docker brings it back by itself.
//   BACKEND_CONTAINER=<container> BASE_URL=http://localhost:8080 node e2e/supervisor.mjs
import assert from "node:assert/strict";
import { execSync } from "node:child_process";

const BASE = process.env.BASE_URL ?? "http://localhost:8080";
const C = process.env.BACKEND_CONTAINER;
if (!C) throw new Error("set BACKEND_CONTAINER");
const sh = (cmd) => execSync(cmd, { stdio: ["ignore", "pipe", "pipe"] }).toString().trim();
const up = async () => { try { return (await fetch(`${BASE}/api/health`)).ok; } catch { return false; } };

assert.equal(sh(`docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' ${C}`), "unless-stopped", "compose must set a restart policy");
const before = Number(sh(`docker inspect -f '{{.RestartCount}}' ${C}`));
try { // the command kills the container it runs in, so it is expected to fail
  sh(`docker exec ${C} python -c "import os,glob,signal\nfor p in glob.glob('/proc/[0-9]*/cmdline'):\n    pid=int(p.split('/')[2])\n    if pid!=os.getpid() and b'uvicorn' in open(p,'rb').read(): os.kill(pid,signal.SIGKILL)"`);
} catch { /* expected */ }
const started = Date.now();
let sawDown = false;
while (Date.now() - started < 60000) {
  if (await up()) { if (sawDown || Date.now() - started > 3000) break; } else sawDown = true;
  await new Promise((r) => setTimeout(r, 200));
}
assert.equal(await up(), true, "the API did not come back by itself");
const after = Number(sh(`docker inspect -f '{{.RestartCount}}' ${C}`));
assert.ok(after > before, `Docker should have restarted the container (restart count ${before} -> ${after})`);
console.log(`E2E supervisor OK: process killed, Docker restarted it by itself (restart count ${before} -> ${after}), healthy again after ${((Date.now() - started) / 1000).toFixed(1)} s`);
