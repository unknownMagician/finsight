/**
 * Number formatting for the Indian market.
 *
 * - Indian digit grouping (lakh/crore): 12,34,56,789 via the `en-IN` locale.
 * - Statement amounts arrive as decimal strings with a `scale` (units, lakhs, crores, ...);
 *   they are shown in ₹ crore, the usual unit for Indian financial statements.
 * - Missing values render as an em dash, never as 0.
 */

export const MISSING = "—";

const SCALE_EXPONENT: Record<string, number> = {
  units: 0,
  thousands: 3,
  lakhs: 5,
  millions: 6,
  crores: 7,
  billions: 9,
};

function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function formatNumber(
  value: string | number | null | undefined,
  { maximumFractionDigits = 2, minimumFractionDigits = 0 } = {},
): string {
  const n = toNumber(value);
  if (n === null) return MISSING;
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits, minimumFractionDigits }).format(n);
}

/** ₹ with Indian grouping, e.g. ₹12,34,567.50. For prices and per-share amounts. */
export function formatINR(value: string | number | null | undefined, fractionDigits = 2): string {
  const n = toNumber(value);
  if (n === null) return MISSING;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(n);
}

/** Convert an amount expressed in `scale` to crores. Unknown scales return null (not a guess). */
export function toCrores(value: string | number | null | undefined, scale: string): number | null {
  const n = toNumber(value);
  const exponent = SCALE_EXPONENT[scale];
  if (n === null || exponent === undefined) return null;
  return n * 10 ** (exponent - 7);
}

/** A statement amount shown in ₹ crore, e.g. "₹1,05,721.90 Cr". */
export function formatCrores(
  value: string | number | null | undefined,
  scale: string,
  currency = "INR",
): string {
  const crores = toCrores(value, scale);
  if (crores === null) return MISSING;
  if (currency !== "INR") return `${currency} ${formatNumber(crores)} Cr`;
  return `${formatINR(crores)} Cr`;
}

export function formatPercent(value: string | number | null | undefined, fractionDigits = 1): string {
  const n = toNumber(value);
  if (n === null) return MISSING;
  return `${formatNumber(n * 100, { maximumFractionDigits: fractionDigits, minimumFractionDigits: fractionDigits })}%`;
}

export function formatTimes(value: string | number | null | undefined): string {
  const n = toNumber(value);
  return n === null ? MISSING : `${formatNumber(n, { maximumFractionDigits: 2 })}×`;
}

/** Indian fiscal label: FY2026 = April 2025 to March 2026. */
export function fiscalLabel(fiscalYear: number, fiscalPeriod: string): string {
  const short = `FY${String(fiscalYear).slice(-2)}`;
  return fiscalPeriod === "FY" ? short : `${fiscalPeriod} ${short}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return MISSING;
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(date.getTime())) return MISSING;
  return new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    ...(iso.length > 10 ? { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" } : { timeZone: "UTC" }),
  }).format(date);
}
