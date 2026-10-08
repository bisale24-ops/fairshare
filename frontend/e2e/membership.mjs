// Cash received, leaving a group, an error in Russian, deleting a group: the flows added after the review.
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { uid } from "./util.mjs";

const BASE = process.env.BASE_URL ?? "http://localhost:8080";
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
const status = (p) => p.page.getByRole("status").last();
const confirmDialog = (p, name) => p.page.getByRole("alertdialog").getByRole("button", { name });

try {
  const alice = await person("Алиса", "alice-m");
  const bob = await person("Боб", "bob-m");
  await register(alice);
  await alice.page.getByPlaceholder("Поездка в Сочи").fill("Квартира");
  await alice.page.getByRole("button", { name: "Создать группу" }).click();
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  const link = await alice.page.getByLabel("Ссылка-приглашение").inputValue();
  await register(bob, link);
  await bob.page.getByRole("button", { name: "Присоединиться" }).click();
  await bob.page.getByRole("heading", { name: "Квартира" }).waitFor();

  // Bob pays 20.00 for both: Alice owes him 10.00
  await bob.page.getByRole("button", { name: "+ Добавить расход" }).click();
  await bob.page.getByPlaceholder("Ужин").fill("Интернет");
  await bob.page.getByPlaceholder("0.00").first().fill("20");
  await bob.page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await bob.page.getByText("Интернет").waitFor();

  // Alice tries to leave while she owes: a clear message in Russian, not English, not raw JSON
  await alice.page.getByRole("button", { name: "Выйти из группы" }).click();
  await confirmDialog(alice, "Выйти").click();
  await alice.page.getByText("Сначала рассчитайтесь: баланс этого участника в группе не равен нулю").waitFor({ timeout: 5000 });

  // Bob received the money in cash and records it; Alice confirms
  await bob.page.getByRole("tab", { name: "Балансы" }).click();
  await bob.page.getByRole("button", { name: "Мне заплатили" }).click();
  await bob.page.getByRole("button", { name: "Отправить на подтверждение" }).click();
  await alice.page.getByRole("tab", { name: "Погашения" }).click();
  await alice.page.getByText("записал(а): Алиса").or(alice.page.getByText("записал(а): Боб")).first().waitFor({ timeout: 5000 });
  await alice.page.locator(".tag.pending").waitFor();
  assert.equal(await bob.page.getByRole("button", { name: "Подтвердить" }).count(), 0, "the one who recorded it cannot confirm it");
  await alice.page.getByRole("button", { name: "Подтвердить" }).click();
  await alice.page.locator(".tag.confirmed").waitFor({ timeout: 5000 });
  await alice.page.locator(".row.head .money", { hasText: "0,00" }).waitFor({ timeout: 5000 }); // balance follows the confirmation

  // Settled: Alice can leave; the group disappears from her list
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  await alice.page.getByRole("button", { name: "Выйти из группы" }).click();
  await confirmDialog(alice, "Выйти").click();
  await alice.page.getByText("Новая группа").waitFor({ timeout: 5000 });
  assert.equal(await alice.page.getByText("Квартира").count(), 0);

  // Bob (the creator) sees her go, closes the group, deletes it
  await bob.page.getByText("участник вышел").waitFor({ timeout: 5000 });
  await bob.page.getByRole("tab", { name: "Настройки" }).click();
  await bob.page.getByRole("button", { name: "Удалить группу" }).click();
  await confirmDialog(bob, "Удалить навсегда").click();
  await bob.page.getByText("Закройте").or(bob.page.getByText("Сначала закройте группу")).first().waitFor({ timeout: 5000 });
  await bob.page.getByRole("button", { name: "Закрыть группу и отправить итог" }).click();
  await confirmDialog(bob, "Закрыть группу").click();
  await bob.page.getByText("Итоговый отчёт").waitFor();
  await bob.page.getByRole("button", { name: "Удалить группу" }).click();
  await confirmDialog(bob, "Удалить навсегда").click();
  await bob.page.getByText("Новая группа").waitFor({ timeout: 5000 });
  assert.equal(await bob.page.getByText("Квартира").count(), 0);

  console.log("E2E membership OK: cash received, leaving, Russian error, delete group");
} catch (e) {
  for (const [i, c] of browser.contexts().entries()) for (const [j, pg] of c.pages().entries()) await pg.screenshot({ path: `/tmp/fail-${i}-${j}.png`, fullPage: true }).catch(() => {});
  throw e;
} finally {
  await browser.close();
}
