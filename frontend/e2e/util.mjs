import { randomBytes } from "node:crypto";

/** Unique per run even when several runs start in the same millisecond (parallel CI jobs, stress runs). */
export const uid = () => `${Date.now()}${randomBytes(3).toString("hex")}`;

/** Wait until the group balance shown in the page header is exactly `expected` (the page refetches asynchronously, so never read it blindly). */
export async function balanceIs(page, expected, timeout = 6000) {
  await page.waitForFunction(
    (want) => document.querySelector(".row.head .money")?.textContent === want,
    expected,
    { timeout },
  ).catch(async () => {
    const got = await page.locator(".row.head .money").innerText().catch(() => "(not found)");
    throw new Error(`balance: expected ${JSON.stringify(expected)} but the page shows ${JSON.stringify(got)}`);
  });
}
