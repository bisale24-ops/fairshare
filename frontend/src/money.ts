/** Money helpers. The API speaks integer minor units; never floats. How many digits a minor unit has depends on the currency. */
import { CURRENCY_EXPONENTS } from "./currencies";

export const exponentOf = (currency: string): number => CURRENCY_EXPONENTS[currency.toUpperCase()] ?? 2;

/** "12.34", "12,3", ".5", "1 234,50" -> minor units. Null if it is not a plain amount or exceeds the server cap (10^12 minor). */
export function parseMoney(input: string, currency = "USD"): number | null {
  const exp = exponentOf(currency);
  const m = input.replace(/[\s\u00a0]/g, "").match(new RegExp(`^(\\d{0,12})(?:[.,](\\d{1,${Math.max(exp, 1)}}))?$`));
  if (!m || (m[1] === "" && m[2] === undefined)) return null;
  if (exp === 0 && m[2] !== undefined) return null; // yen and the like have no fractional part
  const minor = Number(m[1] || "0") * 10 ** exp + Number((m[2] ?? "").padEnd(exp, "0") || "0");
  return minor <= 10 ** 12 ? minor : null;
}

export function formatMoney(minor: number, currency: string): string {
  const exp = exponentOf(currency);
  const sign = minor < 0 ? "−" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 10 ** exp).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  const frac = exp === 0 ? "" : `,${String(abs % 10 ** exp).padStart(exp, "0")}`;
  return `${sign}${whole}${frac}\u00a0${currency}`;
}

export function minorToInput(minor: number, currency = "USD"): string {
  const exp = exponentOf(currency);
  if (exp === 0) return String(minor);
  return `${Math.floor(minor / 10 ** exp)}.${String(minor % 10 ** exp).padStart(exp, "0")}`;
}

/** Russian plural: 1 расход, 2 расхода, 5 расходов, 11 расходов, 21 расход. */
export function pluralize(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  const form = m10 === 1 && m100 !== 11 ? forms[0] : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? forms[1] : forms[2];
  return `${n} ${form}`;
}
