import { describe, expect, it } from "vitest";

import {
  EMPTY_VALUE,
  formatBoolean,
  formatDateTime,
  formatNumber,
  formatValueWithUnit,
} from "./format";

describe("display format conventions", () => {
  it("formats numbers and units consistently", () => {
    expect(formatNumber(1234.5678912)).toBe("1,234.567891");
    expect(formatValueWithUnit(500.25, "nm")).toBe("500.25\u00a0nm");
  });

  it("formats booleans and missing values", () => {
    expect(formatBoolean(true)).toBe("Yes");
    expect(formatBoolean(false)).toBe("No");
    expect(formatBoolean(null)).toBe(EMPTY_VALUE);
    expect(formatNumber(Number.NaN)).toBe(EMPTY_VALUE);
  });

  it("formats dates with an explicitly testable timezone", () => {
    expect(formatDateTime("2026-08-26T16:00:00Z", { timeZone: "UTC" })).toContain("2026");
    expect(formatDateTime("not-a-date")).toBe(EMPTY_VALUE);
  });
});
