import { describe, expect, it } from "vitest";
import { errorText } from "./api";

describe("errorText", () => {
  it("turns FastAPI validation lists into one readable line", () => {
    const detail = [{ loc: ["body", "email"], msg: "Value error, bad address" }];
    expect(errorText(detail, "x")).toBe("E-mail: bad address");
  });
  it("passes plain strings through and falls back", () => {
    expect(errorText("Group is closed", "x")).toBe("Group is closed");
    expect(errorText(undefined, "Bad Request")).toBe("Bad Request");
  });
});
