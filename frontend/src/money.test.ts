import { describe, expect, it } from "vitest";
import { exponentOf, formatMoney, minorToInput, parseMoney, pluralize } from "./money";

describe("money", () => {
  it("parses decimals without floating point", () => {
    expect(parseMoney("12.34")).toBe(1234);
    expect(parseMoney("12,3")).toBe(1230);
    expect(parseMoney("0.07")).toBe(7);
    expect(parseMoney("19.99")).toBe(1999);
    expect(parseMoney("1.005")).toBeNull();
    expect(parseMoney("abc")).toBeNull();
    expect(parseMoney(".5")).toBe(50);
    expect(parseMoney("1 234,50")).toBe(123450);
    expect(parseMoney("1\u00a0234.5")).toBe(123450);
    expect(parseMoney("")).toBeNull();
    expect(parseMoney("99999999999")).toBeNull(); // 11 digits: above the 10^12 minor-unit cap
    expect(parseMoney("-5")).toBeNull();
  });
  it("formats and round-trips", () => {
    expect(formatMoney(123456, "USD")).toBe("1 234,56 USD");
    expect(formatMoney(-5, "EUR")).toBe("−0,05 EUR");
    expect(parseMoney(minorToInput(1999))).toBe(1999);
  });
  it("pluralizes in Russian", () => {
    const f: [string, string, string] = ["расход", "расхода", "расходов"];
    expect([1, 2, 5, 11, 12, 21, 22, 25, 111].map((n) => pluralize(n, f))).toEqual([
      "1 расход", "2 расхода", "5 расходов", "11 расходов", "12 расходов", "21 расход", "22 расхода", "25 расходов", "111 расходов",
    ]);
  });
  it("respects the number of minor digits of the currency", () => {
    expect([exponentOf("USD"), exponentOf("JPY"), exponentOf("KWD"), exponentOf("kgs")]).toEqual([2, 0, 3, 2]);
    expect(parseMoney("1000", "JPY")).toBe(1000);
    expect(parseMoney("10.5", "JPY")).toBeNull(); // no fractional yen
    expect(parseMoney("1.234", "KWD")).toBe(1234);
    expect(parseMoney("1.2345", "KWD")).toBeNull();
    expect(parseMoney("1.005", "USD")).toBeNull();
    expect(formatMoney(1234567, "JPY")).toBe("1\u00a0234\u00a0567\u00a0JPY");
    expect(formatMoney(1500, "KWD")).toBe("1,500\u00a0KWD");
    expect(minorToInput(1500, "KWD")).toBe("1.500");
    expect(minorToInput(1000, "JPY")).toBe("1000");
    expect(parseMoney(minorToInput(1999, "KWD"), "KWD")).toBe(1999);
  });
});
