// Mobile layout check: no horizontal scrolling on any screen at phone width.
// Usage: BASE_URL=http://localhost:8080 node e2e/mobile.mjs
import { chromium } from "playwright-core";
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE_URL ?? "http://localhost:8080";
const SHOTS = process.env.SHOTS_DIR ?? "../docs/screenshots";
mkdirSync(SHOTS, { recursive: true });
const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 375, height: 812 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
const page = await ctx.newPage();
const problems = [];

async function noSideScroll(label) {
  const { sw, iw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: window.innerWidth }));
  if (sw > iw) problems.push(`${label}: scrollWidth ${sw} > ${iw}`);
}

try {
  await page.goto(BASE);
  await noSideScroll("login");
  await page.getByText("Нет аккаунта? Зарегистрироваться").click();
  await page.getByLabel("Имя").fill("Мобильный");
  await page.getByLabel("E-mail").fill(`mobile${Date.now()}@example.com`);
  await page.getByLabel("Пароль").fill("e2e-pass-123");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await page.getByPlaceholder("Поездка в Сочи").fill("Поездка с очень длинным названием для проверки переноса строк");
  await noSideScroll("groups");
  await page.screenshot({ path: `${SHOTS}/m1-groups.png`, fullPage: true });
  await page.getByRole("button", { name: "Создать группу" }).click();
  await page.getByRole("button", { name: "+ Добавить расход" }).click();
  await page.getByPlaceholder("Ужин").fill("Ужин в ресторане с очень длинным названием блюда");
  await page.getByPlaceholder("0.00").first().fill("1234567.89");
  await noSideScroll("expense form");
  await page.screenshot({ path: `${SHOTS}/m2-expense-form.png`, fullPage: true });
  await page.getByRole("button", { name: "Добавить расход", exact: true }).click();
  await page.getByText("Ужин в ресторане").waitFor();
  for (const tab of ["Расходы", "Балансы", "Погашения", "Лента", "Настройки"]) {
    await page.getByRole("tab", { name: tab }).click();
    await noSideScroll(`tab ${tab}`);
  }
  await page.getByRole("tab", { name: "Расходы" }).click();
  await page.screenshot({ path: `${SHOTS}/m3-expenses.png`, fullPage: true });
  await page.getByRole("tab", { name: "Настройки" }).click();
  await page.screenshot({ path: `${SHOTS}/m4-settings.png`, fullPage: true });
  assert.deepEqual(problems, [], `horizontal overflow on a phone:\n${problems.join("\n")}`);
  console.log("MOBILE OK: no horizontal scroll at 375px on", ["login", "groups", "expense form", "5 tabs"].join(", "));
} finally {
  await browser.close();
}
