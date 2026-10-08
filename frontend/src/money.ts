/** Money helpers. The API speaks integer minor units (cents); never floats. */

export function parseMoney(input: string): number | null {
  const m = input.trim().match(/^(\d{1,12})(?:[.,](\d{1,2}))?$/);
  if (!m) return null;
  const cents = (m[2] ?? "").padEnd(2, "0");
  return Number(m[1]) * 100 + Number(cents);
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
