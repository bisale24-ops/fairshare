// Browser end-to-end: two people in two separate browser contexts, real UI, real API.
// Usage: BASE_URL=http://localhost:8080 node e2e/two-people.mjs   (uses the installed Google Chrome)
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { balanceIs, uid } from "./util.mjs";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:8080";
const SHOTS = process.env.SHOTS_DIR ?? "../docs/screenshots";
mkdirSync(SHOTS, { recursive: true });
const stamp = uid();
const nbsp = " ";

const browser = await chromium.launch({ channel: "chrome", headless: true });

async function person(name, slug) {
  const ctx = await browser.newContext({ viewport: { width: 1000, height: 760 } });
  const page = await ctx.newPage();
  return { name, page, email: `${slug}${stamp}@example.com` };
}
async function register(p, url = BASE) {
  await p.page.goto(url);
  await p.page.getByText("Нет аккаунта? Зарегистрироваться").click();
  await p.page.getByLabel("Имя").fill(p.name);
  await p.page.getByLabel("E-mail").fill(p.email);
  await p.page.getByLabel("Пароль").fill("e2e-pass-123");
  await p.page.getByRole("button", { name: "Создать аккаунт" }).click();
}

try {
  const alice = await person("Алиса", "alice");
  const bob = await person("Боб", "bob");

  // Alice: register, create a group, take the invite link
  await register(alice);
  await alice.page.getByPlaceholder("Поездка в Сочи").fill("Поездка в Сочи");
  await alice.page.getByRole("button", { name: "Создать группу" }).click();
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  const link = await alice.page.getByLabel("Ссылка-приглашение").inputValue();
  assert.match(link, /#\/join\//);
  await alice.page.getByRole("tab", { name: "Расходы" }).click();

  // Bob: opens the link, registers, joins
  await register(bob, link);
  await bob.page.getByRole("button", { name: "Присоединиться" }).click();
  await bob.page.getByRole("heading", { name: "Поездка в Сочи" }).waitFor();

  // Bob adds 10.01 split equally: the leftover cent goes to the lower user id (Alice)
  await bob.page.getByRole("button", { name: "+ Добавить расход" }).click();
  await bob.page.getByPlaceholder("Ужин").fill("Такси");
  await bob.page.getByPlaceholder("0.00").first().fill("10.01");
  await bob.page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await bob.page.getByText("Такси").waitFor();

  // Alice's page was NOT reloaded: it must update by itself
  await alice.page.getByText("Такси").waitFor({ timeout: 5000 });
  await balanceIs(alice.page, `−5,01${nbsp}USD`);
  await balanceIs(bob.page, `5,01${nbsp}USD`);
  assert.equal(await alice.page.getByTestId("unread").innerText(), "1");
  await alice.page.screenshot({ path: `${SHOTS}/01-alice-live-update.png` });
  await bob.page.screenshot({ path: `${SHOTS}/02-bob-added-expense.png` });

  // Alice pays 2.00 (partial); it stays pending and changes nothing until Bob confirms
  await alice.page.getByRole("tab", { name: "Балансы" }).click();
  await alice.page.getByRole("button", { name: "Я заплатил(а)" }).click();
  await alice.page.getByLabel("Сумма платежа").fill("2.00");
  await alice.page.getByRole("button", { name: "Отправить на подтверждение" }).click();
  await bob.page.getByRole("tab", { name: "Погашения" }).click();
  await bob.page.locator(".tag.pending").waitFor({ timeout: 5000 }); // the status tag, not the live banner that says the same words
  await balanceIs(bob.page, `5,01${nbsp}USD`); // pending: not counted
  await bob.page.screenshot({ path: `${SHOTS}/03-bob-confirm-payment.png` });
  await bob.page.getByRole("button", { name: "Подтвердить" }).click();

  await alice.page.getByText("3,01").first().waitFor({ timeout: 5000 });
  await balanceIs(alice.page, `−3,01${nbsp}USD`);
  await balanceIs(bob.page, `3,01${nbsp}USD`);
  await alice.page.screenshot({ path: `${SHOTS}/04-alice-after-confirmation.png` });

  // Close the group: no new expenses, report is shown
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  await alice.page.getByRole("button", { name: "Закрыть группу и отправить итог" }).click();
  await alice.page.getByRole("alertdialog").getByRole("button", { name: "Закрыть группу" }).click();
  await alice.page.getByText("Итоговый отчёт").waitFor();
  await alice.page.screenshot({ path: `${SHOTS}/05-closed-report.png`, fullPage: true });
  await bob.page.getByRole("tab", { name: "Расходы" }).click();
  await bob.page.getByText("Группа закрыта: новые расходы не добавляются").waitFor({ timeout: 5000 });
  assert.equal(await bob.page.getByRole("button", { name: "+ Добавить расход" }).count(), 0);

  console.log("E2E OK: two browsers, live updates, partial payment with confirmation, close");
} finally {
  await browser.close();
}
