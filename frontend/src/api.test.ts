import { describe, expect, it } from "vitest";
import { errorText } from "./api";
import { MESSAGES } from "./messages";

describe("errorText", () => {
  it("translates API error codes", () => {
    expect(errorText({ code: "group_closed_expenses", message: "The group is closed" }, "x")).toMatch(/Группа закрыта/);
    expect(errorText({ code: "settlement_resolved", message: "x", params: { status: "confirmed" } }, "x")).toBe("Этот платёж уже подтверждён");
  });
  it("formats amounts inside messages with the group's own currency", () => {
    const text = errorText({ code: "amount_exceeds_limit", message: "x", params: { max_minor: 1500, currency: "KWD" } }, "x");
    expect(text).toContain("1,500\u00a0KWD");
    expect(errorText({ code: "amount_exceeds_limit", message: "x", params: { max_minor: 1000, currency: "JPY" } }, "x")).toContain("1\u00a0000\u00a0JPY");
  });
  it("turns field validation lists into readable Russian, never raw JSON", () => {
    const text = errorText([{ loc: ["body", "email"], msg: "value is not a valid email address", type: "value_error" }, { loc: ["body", "amount_minor"], msg: "x", type: "greater_than" }], "x");
    expect(text).toBe("E-mail: неверный адрес; Сумма: значение слишком маленькое");
    expect(text).not.toMatch(/[{}\[\]]/);
  });
  it("falls back to the server's English message for a code it does not know, and to the fallback otherwise", () => {
    expect(errorText({ code: "brand_new", message: "Something new" }, "x")).toBe("Something new");
    expect(errorText(undefined, "Bad Request")).toBe("Bad Request");
    expect(errorText("Plain", "x")).toBe("Plain");
  });
  it("has a non-empty Russian text for every code", () => {
    for (const [code, fn] of Object.entries(MESSAGES)) expect(fn({}), code).toMatch(/[А-Яа-я]/);
  });
});
