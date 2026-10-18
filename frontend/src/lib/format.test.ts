import { describe, expect, it } from "vitest";

import { fiscalLabel, formatCrores, formatINR, formatNumber, formatPercent, MISSING, toCrores } from "./format";

describe("Indian number formatting", () => {
  it("groups digits in lakhs and crores", () => {
    expect(formatNumber(123456789)).toBe("12,34,56,789");
    expect(formatINR("1234567.5")).toBe("₹12,34,567.50");
  });

  it("converts statement scales to crores", () => {
    expect(toCrores("10572190000000", "units")).toBe(1057219);
    expect(toCrores("250", "lakhs")).toBe(2.5);
    expect(toCrores("12000", "crores")).toBe(12000);
    expect(toCrores("10", "millions")).toBe(1);
    expect(toCrores("1", "furlongs")).toBeNull(); // unknown scale: no guess
    expect(formatCrores("105721900000000", "units")).toBe("₹1,05,72,190.00 Cr");
  });

  it("shows missing values as a dash, never zero", () => {
    expect(formatINR(null)).toBe(MISSING);
    expect(formatCrores(undefined, "crores")).toBe(MISSING);
    expect(formatPercent("")).toBe(MISSING);
    expect(formatPercent("0.1834")).toBe("18.3%");
  });

  it("labels Indian fiscal periods", () => {
    expect(fiscalLabel(2026, "FY")).toBe("FY26");
    expect(fiscalLabel(2027, "Q1")).toBe("Q1 FY27");
  });
});
