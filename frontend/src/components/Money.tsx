import { formatMoney } from "../money";

/** Green = they owe me, red = I owe, grey = settled. */
export function Money({ minor, currency, big }: { minor: number; currency: string; big?: boolean }) {
  const cls = minor > 0 ? "pos" : minor < 0 ? "neg" : "zero";
  return <span className={`money ${cls} ${big ? "big" : ""}`}>{formatMoney(minor, currency)}</span>;
}
