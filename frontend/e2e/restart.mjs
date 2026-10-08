// The API process dies while people are working, then comes back. What does the user see, and is anything lost or doubled?
//   BACKEND_CONTAINER=<container name or id> BASE_URL=http://localhost:8080 node e2e/restart.mjs
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { balanceIs, uid } from "./util.mjs";

const BASE = process.env.BASE_URL ?? "http://localhost:8080";
const C = process.env.BACKEND_CONTAINER;
if (!C) throw new Error("set BACKEND_CONTAINER to the API container (docker compose ps -q backend)");
const sh = (cmd) => execSync(cmd, { stdio: ["ignore", "pipe", "pipe"] }).toString().trim();
const stamp = uid();
const browser = await chromium.launch({ channel: "chrome", headless: true });

async function person(name, slug) {
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 800 } });
  return { name, page: await ctx.newPage(), email: `${slug}${stamp}@example.com` };
}
async function register(p, url = BASE) {
  await p.page.goto(url);
  await p.page.getByText("Нет аккаунта? Зарегистрироваться").click();
  await p.page.getByLabel("Имя").fill(p.name);
  await p.page.getByLabel("E-mail").fill(p.email);
  await p.page.getByLabel("Пароль").fill("e2e-pass-123");
  await p.page.getByRole("button", { name: "Создать аккаунт" }).click();
}
async function healthy(timeoutMs) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try { if ((await fetch(`${BASE}/api/health`)).ok) return true; } catch { /* still down */ }
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

let restartPolicy = "unless-stopped";
try {
  restartPolicy = sh(`docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' ${C}`) || "no";
  const alice = await person("Алиса", "alice-k");
  const bob = await person("Боб", "bob-k");
  await register(alice);
  await alice.page.getByPlaceholder("Поездка в Сочи").fill("Ремонт");
  await alice.page.getByRole("button", { name: "Создать группу" }).click();
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  const link = await alice.page.getByLabel("Ссылка-приглашение").inputValue();
  await register(bob, link);
  await bob.page.getByRole("button", { name: "Присоединиться" }).click();
  await bob.page.getByRole("heading", { name: "Ремонт" }).waitFor();
  await alice.page.getByRole("tab", { name: "Расходы" }).click();

  // Alice starts typing an expense; the API process is killed (SIGKILL) before she presses the button
  await alice.page.getByRole("button", { name: "+ Добавить расход" }).click();
  await alice.page.getByLabel("Участвует: Боб").waitFor({ timeout: 8000 }); // Alice's page has heard that Bob joined
  await alice.page.getByPlaceholder("Ужин").fill("Краска");
  await alice.page.getByPlaceholder("0.00").first().fill("12.50");
  sh(`docker update --restart=no ${C}`);   // deterministic: we decide when it comes back (the restart policy has its own test)
  sh(`docker kill ${C}`);
  assert.equal(await healthy(1500), false, "the API must be down now");

  // 1. pressing the button while it is down: a clear Russian message, the form keeps what was typed
  await alice.page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await alice.page.getByText("Нет связи с сервером").waitFor({ timeout: 8000 });
  assert.equal(await alice.page.getByPlaceholder("0.00").first().inputValue(), "12.50");
  assert.equal(await alice.page.getByText("Failed to fetch").count(), 0, "no raw browser error");

  // 2. Bob's screen did not log him out or break while the API was gone
  await bob.page.waitForTimeout(2500);
  assert.equal(await bob.page.getByRole("heading", { name: "Ремонт" }).count(), 1, "Bob is still in the group");
  assert.equal(await bob.page.getByText("Войти").count(), 0, "Bob was not sent to the login screen");

  // 3. the process comes back (a supervisor, or here: us)
  sh(`docker start ${C}`);
  assert.equal(await healthy(60000), true, "the API must come back");

  // 4. Alice presses again: it works, exactly once
  await alice.page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await alice.page.getByRole("button", { name: "+ Добавить расход" }).waitFor({ timeout: 8000 });
  await alice.page.getByText("Краска").first().waitFor({ timeout: 8000 }); // the list refetches after the form closes: wait, do not read blindly
  await alice.page.waitForTimeout(700);                                       // give a (wrong) duplicate time to appear before counting
  assert.equal(await alice.page.getByText("Краска").count(), 1);

  // 5. Bob's page, which was not reloaded, hears about it by itself (its stream reconnected)
  await bob.page.getByText("Краска").waitFor({ timeout: 25000 });
  assert.equal(await bob.page.getByText("Краска").count(), 1, "one expense, not two");
  await balanceIs(bob.page, "−6,25 USD");
  assert.equal(await bob.page.getByText("Войти").count(), 0);

  console.log("E2E restart OK: clear message while down, nobody logged out, retry made exactly one expense, other screen caught up by itself");
} catch (e) {
  for (const [i, c] of browser.contexts().entries()) for (const [j, pg] of c.pages().entries()) await pg.screenshot({ path: `/tmp/fail-restart-${i}-${j}.png`, fullPage: true }).catch(() => {});
  throw e;
} finally {
  try { sh(`docker start ${C}`); } catch { /* already running */ }
  try { sh(`docker update --restart=${restartPolicy} ${C}`); } catch { /* ignore */ }
  await browser.close();
}
