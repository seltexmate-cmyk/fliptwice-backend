// fliptwice-frontend/app/lib/number.ts

/**
 * Parse user numeric input that may use comma or dot.
 * Accepts: "10,5" "10.5" " 1 234,56 "
 * Returns null if invalid.
 */
export function parseLocaleNumber(raw: string): number | null {
  if (!raw) return null;
  let s = raw.trim();
  s = s.replace(/\s+/g, ""); // remove spaces
  s = s.replace(/,/g, ".");  // comma -> dot
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

/**
 * Backwards-compatible alias.
 * Old code expects NaN on invalid input.
 */
export function parseDecimalInput(value: string): number {
  const n = parseLocaleNumber(value);
  return n === null ? NaN : n;
}

export function formatEUR(value: number): string {
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(value);
}

export function roundTo99(value: number): number {
  // Example: 12.10 -> 11.99, 12.99 -> 12.99, 13.01 -> 12.99
  if (!Number.isFinite(value)) return value;
  const floored = Math.floor(value);
  const candidate = floored + 0.99;
  return candidate > value ? candidate - 1 : candidate;
}

/**
 * Old/simple suggested price calculation used on the Home page.
 * (We will later upgrade this to use fees + shipping + target profit from Settings.)
 */
export function calcSuggestedPrice(buyCost: number, multiplier: number): number {
  const raw = buyCost * multiplier;
  return roundTo99(raw);
}