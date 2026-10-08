// Browser checks for the two user-visible defects found in review:
//  1. the link in the invite e-mail must open the join page;
//  2. a failed receipt upload must not lead to the same expense being created twice.
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { balanceIs, uid } from "./util.mjs";
import { writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

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

try {
  const alice = await person("Алиса", "alice-r");
  const bob = await person("Боб", "bob-r");
  await register(bob);                      // Bob already has an account; the invite goes to his address
  await bob.page.getByText("Новая группа").waitFor();
  await register(alice);
  await alice.page.getByPlaceholder("Поездка в Сочи").fill("Дача");
  await alice.page.getByRole("button", { name: "Создать группу" }).click();
  await alice.page.getByRole("tab", { name: "Настройки" }).click();
  await alice.page.getByPlaceholder("friend@example.com").fill(bob.email);
  await alice.page.getByRole("button", { name: "Пригласить по e-mail" }).click();
  await alice.page.getByText(`Приглашение отправлено на ${bob.email}`).waitFor();

  // 1. Bob opens the (stubbed) mailbox, takes the link from the letter and follows it
  await bob.page.reload();
  await bob.page.getByRole("button", { name: "Письма (заглушка)" }).click();
  await bob.page.getByText("invited you to Дача").waitFor({ timeout: 5000 });
  await bob.page.getByText("invited you to Дача").click();
  const body = await bob.page.locator("details[open] pre").innerText();
  const link = body.match(/Join: (\S+)/)[1];
  assert.match(link, /\/#\/join\//, "the e-mail link must contain the hash route");
  await bob.page.goto(link.replace("http://localhost:8080", BASE));
  await bob.page.getByRole("button", { name: "Присоединиться" }).waitFor();
  await bob.page.getByRole("button", { name: "Присоединиться" }).click();
  await bob.page.getByRole("heading", { name: "Дача" }).waitFor();

  // 2. A receipt that is not a real image: the expense is saved once, the form says so, and pressing again does not duplicate it
  const dir = mkdtempSync(join(tmpdir(), "fs-"));
  const fake = join(dir, "receipt.png");
  writeFileSync(fake, "this is not an image");
  await bob.page.getByRole("button", { name: "+ Добавить расход" }).click();
  await bob.page.getByPlaceholder("Ужин").fill("Дрова");
  await bob.page.getByPlaceholder("0.00").first().fill("30");
  await bob.page.locator('input[type="file"]').setInputFiles(fake);
  await bob.page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await bob.page.getByText("Расход сохранён, но чек не загрузился").waitFor({ timeout: 5000 });
  await bob.page.getByRole("button", { name: "Сохранить" }).click();      // second press, no file now
  await bob.page.getByRole("button", { name: "+ Добавить расход" }).waitFor();
  await bob.page.getByText("Дрова").first().waitFor({ timeout: 5000 });
  await bob.page.waitForTimeout(700); // give a (wrong) duplicate time to show up before counting
  assert.equal(await bob.page.getByText("Дрова").count(), 1, "the expense must exist exactly once");
  await balanceIs(bob.page, "15,00\u00a0USD"); // counted once: Bob paid 30.00 and is owed half

  // 3. Alice sees it live, once, and cannot change Bob's expense
  await alice.page.getByRole("tab", { name: "Расходы" }).click();
  await alice.page.getByText("Дрова").waitFor({ timeout: 5000 });
  await alice.page.getByRole("button", { name: "Удалить" }).click();
  await alice.page.getByRole("alertdialog").getByRole("button", { name: "Удалить" }).click();
  await alice.page.getByText("Менять расход может только тот, кто его добавил, или плательщик").waitFor({ timeout: 5000 });
  assert.equal(await alice.page.getByText("Дрова").count(), 1, "a bystander must not be able to delete it");

  // 4. Alice pays her whole 15.00 debt, Bob confirms, then Bob edits the expense down to 10.00:
  //    Alice's payment is now bigger than her debt and the UI must say so (the numbers stay correct)
  await alice.page.getByRole("tab", { name: "Балансы" }).click();
  await alice.page.getByRole("button", { name: "Я заплатил(а)" }).click();
  await alice.page.getByRole("button", { name: "Отправить на подтверждение" }).click();
  await bob.page.getByRole("tab", { name: "Погашения" }).click();
  await bob.page.getByRole("button", { name: "Подтвердить" }).click();
  await bob.page.getByRole("tab", { name: "Расходы" }).click();
  await bob.page.getByRole("button", { name: "Изменить" }).click();
  await bob.page.getByPlaceholder("0.00").first().fill("10");
  await bob.page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await bob.page.getByText("После изменения платёж стал больше долга").waitFor({ timeout: 5000 });
  assert.match(await bob.page.getByRole("status").first().innerText(), /переплатил\(а\) 10,00/);
  await alice.page.getByRole("tab", { name: "Лента" }).click();
  await alice.page.getByText("После правки платёж стал больше долга").waitFor({ timeout: 5000 });

  console.log("E2E review fixes OK: e-mail invite link joins; failed receipt does not duplicate the expense");
} finally {
  await browser.close();
}
