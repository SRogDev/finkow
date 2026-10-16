/**
 * Display-only money formatting.
 *
 * The API sends all money as decimal STRINGS. We never do arithmetic here —
 * these helpers only turn the string into a readable label. All math happens
 * server-side.
 */

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function toNumber(value: string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

/** "$100,000.00" — falls back to "—" when the value is missing. */
export function formatMoney(value: string | null | undefined): string {
  const n = toNumber(value);
  return n === null ? "—" : usd.format(n);
}

/** "+$12.50" / "-$12.50" — zero renders without a sign. */
export function formatSignedMoney(value: string | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  if (n === 0) return usd.format(0);
  const abs = usd.format(Math.abs(n));
  return n > 0 ? `+${abs}` : `-${abs}`;
}

/** "3.00%" */
export function formatPercent(value: string | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  return `${n.toFixed(2)}%`;
}

/** "+3.00%" / "-1.25%" */
export function formatSignedPercent(value: string | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return "—";
  const abs = `${Math.abs(n).toFixed(2)}%`;
  if (n === 0) return abs;
  return n > 0 ? `+${abs}` : `-${abs}`;
}

/** Trims cosmetic trailing zeros: "10.0000" → "10". Display only. */
export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const trimmed = value.trim();
  if (trimmed === "") return "—";
  if (!trimmed.includes(".")) return trimmed;
  return trimmed.replace(/\.?0+$/, "");
}

/** "2026-09-26T18:00:00Z" → readable local date/time. */
export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(d);
}
