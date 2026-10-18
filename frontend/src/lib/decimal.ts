/**
 * Exact decimal-string helpers for form inputs. The backend computes in Decimal and accepts
 * numbers as strings, so user input is never routed through binary floating point.
 */

const DECIMAL_RE = /^-?\d+(\.\d+)?$/;

export function isDecimal(text: string): boolean {
  return DECIMAL_RE.test(text.trim().replace(/,/g, ""));
}

/** Normalize user input ("1,23,456.50" -> "123456.50"); null if not a decimal number. */
export function parseDecimal(text: string): string | null {
  const cleaned = text.trim().replace(/,/g, "");
  return DECIMAL_RE.test(cleaned) ? cleaned : null;
}

/** Multiply a decimal string by 10^exponent without floating point. */
export function shiftDecimal(value: string, exponent: number): string {
  const negative = value.startsWith("-");
  const unsigned = negative ? value.slice(1) : value;
  const [intPart = "0", fracPart = ""] = unsigned.split(".");
  let digits = intPart + fracPart;
  let point = intPart.length + exponent;
  if (point <= 0) {
    digits = "0".repeat(1 - point) + digits;
    point = 1;
  } else if (point > digits.length) {
    digits = digits + "0".repeat(point - digits.length);
  }
  let whole = digits.slice(0, point).replace(/^0+(?=\d)/, "");
  const frac = digits.slice(point).replace(/0+$/, "");
  if (whole === "") whole = "0";
  const result = frac ? `${whole}.${frac}` : whole;
  return negative && /[1-9]/.test(result) ? `-${result}` : result;
}

/** "12.5" (percent) -> "0.125" (fraction). Null when the input is not a number. */
export function percentToFraction(text: string): string | null {
  const parsed = parseDecimal(text);
  return parsed === null ? null : shiftDecimal(parsed, -2);
}

/**
 * List of decimals separated by commas, semicolons or spaces ("100, 110, 121"). Digit-grouping
 * commas are not allowed inside list items.
 */
export function parseDecimalList(text: string, { percent = false } = {}): string[] | null {
  const parts = text
    .split(/[,;\s]+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (parts.length === 0) return null;
  const out: string[] = [];
  for (const part of parts) {
    const value = percent ? percentToFraction(part) : parseDecimal(part);
    if (value === null) return null;
    out.push(value);
  }
  return out;
}

function toScaled(value: string, digits: number): bigint {
  const negative = value.startsWith("-");
  const [i = "0", f = ""] = (negative ? value.slice(1) : value).split(".");
  const n = BigInt(i + f.padEnd(digits, "0"));
  return negative ? -n : n;
}

function fracDigits(value: string): number {
  return value.split(".")[1]?.length ?? 0;
}

/** Exact a + b for decimal strings. */
export function addDecimal(a: string, b: string): string {
  const digits = Math.max(fracDigits(a), fracDigits(b));
  const sum = toScaled(a, digits) + toScaled(b, digits);
  const negative = sum < 0n;
  const text = (negative ? -sum : sum).toString().padStart(digits + 1, "0");
  const raw = digits ? `${text.slice(0, -digits)}.${text.slice(-digits)}` : text;
  return shiftDecimal(negative ? `-${raw}` : raw, 0);
}

export function subtractDecimal(a: string, b: string): string {
  return addDecimal(a, b.startsWith("-") ? b.slice(1) : `-${b}`);
}
