/** Money helpers. The API speaks integer minor units (cents); never floats. */

/** "12.34", "12,3", ".5", "1 234,50" -> minor units. Null if it is not a plain amount or exceeds the server cap (10^12 minor). */
export function parseMoney(input: string): number | null {
  const m = input.replace(/[\s\u00a0]/g, "").match(/^(\d{0,10})(?:[.,](\d{1,2}))?$/);
  if (!m || (m[1] === "" && m[2] === undefined)) return null;
  const cents = (m[2] ?? "").padEnd(2, "0");
  return Number(m[1] || "0") * 100 + Number(cents);
}

export function formatMoney(minor: number, currency: string): string {
  const sign = minor < 0 ? "−" : "";
  const abs = Math.abs(minor);
  const whole = Math.floor(abs / 100).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${whole},${String(abs % 100).padStart(2, "0")} ${currency}`;
}

export function minorToInput(minor: number): string {
  return `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, "0")}`;
}

/** Russian plural: 1 расход, 2 расхода, 5 расходов, 11 расходов, 21 расход. */
export function pluralize(n: number, forms: [string, string, string]): string {
  const m10 = n % 10;
  const m100 = n % 100;
  const form = m10 === 1 && m100 !== 11 ? forms[0] : m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14) ? forms[1] : forms[2];
  return `${n} ${form}`;
}
