import { describe, expect, it } from "vitest";
import { formatMoney, minorToInput, parseMoney } from "./money";

describe("money", () => {
  it("parses decimals without floating point", () => {
    expect(parseMoney("12.34")).toBe(1234);
    expect(parseMoney("12,3")).toBe(1230);
    expect(parseMoney("0.07")).toBe(7);
    expect(parseMoney("19.99")).toBe(1999);
    expect(parseMoney("1.005")).toBeNull();
    expect(parseMoney("abc")).toBeNull();
    expect(parseMoney("-5")).toBeNull();
  });
  it("formats and round-trips", () => {
    expect(formatMoney(123456, "USD")).toBe("1 234,56 USD");
    expect(formatMoney(-5, "EUR")).toBe("−0,05 EUR");
    expect(parseMoney(minorToInput(1999))).toBe(1999);
  });
});
