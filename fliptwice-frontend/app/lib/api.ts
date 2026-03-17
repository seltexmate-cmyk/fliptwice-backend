export async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(`GET ${url} failed`);
  return res.json();
}

export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`POST ${url} failed: ${msg}`);
  }
  return res.json();
}

export async function apiPut<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => "");
    throw new Error(`PUT ${url} failed: ${msg}`);
  }
  return res.json();
}

// ✅ Compatibility layer for older code that expects api.get/post/put
export const api = {
  get: apiGet,
  post: apiPost,
  put: apiPut,
};

export type ItemStatus = "Active" | "Draft" | "Sold" | "Archived";

export type Item = {
  item_id: string;
  title: string;
  category?: string | null;
  buy_cost: number;
  demand_tier: "Low" | "Medium" | "High";
  multiplier: number;
  status: ItemStatus;
  created_at: string;
};

export type BusinessSettings = {
  currency: string;
  countryFrom: string;
  mainMarketplace: string;
  defaultShippingCost: number;
  defaultPackagingCost: number;
  ebayFeePercent: number;
  promoPercent: number;
  targetProfit: number;
  roundingMode: "NONE" | "END_99";
};