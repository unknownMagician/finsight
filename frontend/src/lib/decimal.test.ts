import { describe, expect, it } from "vitest";

import { addDecimal, parseDecimal, parseDecimalList, percentToFraction, shiftDecimal, subtractDecimal } from "./decimal";

describe("decimal strings", () => {
  it("shifts the decimal point exactly", () => {
    expect(shiftDecimal("12.5", -2)).toBe("0.125");
    expect(shiftDecimal("0.1", -2)).toBe("0.001");
    expect(shiftDecimal("400000000", -7)).toBe("40");
    expect(shiftDecimal("-3", 2)).toBe("-300");
    expect(shiftDecimal("0", -2)).toBe("0");
  });

  it("parses user input without floating point", () => {
    expect(parseDecimal("1,23,456.50")).toBe("123456.50");
    expect(parseDecimal("abc")).toBeNull();
    expect(percentToFraction("11.25")).toBe("0.1125");
    expect(parseDecimalList("100, 110 121")).toEqual(["100", "110", "121"]);
    expect(parseDecimalList("12 x")).toBeNull();
    expect(parseDecimalList("12, 10", { percent: true })).toEqual(["0.12", "0.1"]);
  });

  it("adds and subtracts exactly", () => {
    expect(addDecimal("0.1", "0.2")).toBe("0.3");
    expect(subtractDecimal("100", "250.75")).toBe("-150.75");
    expect(subtractDecimal("4000000000000.0", "1300000000000.0")).toBe("2700000000000");
  });
});
