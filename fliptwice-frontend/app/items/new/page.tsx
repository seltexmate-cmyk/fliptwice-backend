"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiGet, apiPost } from "@/lib/api";
import { parseLocaleNumber, formatEUR, roundTo99 } from "@/lib/number";

type BusinessSettings = {
  currency: string;
  countryFrom: string;
  mainMarketplace: string;

  defaultShippingCost: number;
  defaultPackagingCost: number;

  ebayFeePercent: number;
  promoPercent: number;
  targetProfit: number;

  roundingMode: "NONE" | "END_99";

  demandLowMultiplier: number;
  demandMediumMultiplier: number;
  demandHighMultiplier: number;
};

type SettingsResponse = { settings: BusinessSettings };

type DemandTier = "Low" | "Medium" | "High";
type ItemStatus = "Active" | "Draft" | "Sold" | "Archived";

function tierMultiplier(tier: DemandTier, s: BusinessSettings): number {
  if (tier === "Low") return s.demandLowMultiplier ?? 2.2;
  if (tier === "High") return s.demandHighMultiplier ?? 3.2;
  return s.demandMediumMultiplier ?? 2.6;
}

function roundMoney(v: number, roundingMode: "NONE" | "END_99") {
  if (!Number.isFinite(v)) return v;
  if (roundingMode === "END_99") return roundTo99(v);
  return Math.round(v * 100) / 100;
}

export default function NewItemPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [settings, setSettings] = useState<BusinessSettings | null>(null);

  // Form fields (strings for numeric inputs)
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [buyCostRaw, setBuyCostRaw] = useState("");
  const [demandTier, setDemandTier] = useState<DemandTier>("Medium");
  const [status, setStatus] = useState<ItemStatus>("Active");

  // allow overriding shipping/packaging per item (defaults from settings)
  const [shippingRaw, setShippingRaw] = useState("");
  const [packagingRaw, setPackagingRaw] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);

        const base = process.env.NEXT_PUBLIC_API_URL;
        if (!base) throw new Error("NEXT_PUBLIC_API_URL is missing in .env.local");

        const res = await apiGet<SettingsResponse>(`${base}/business-settings`);
        if (!res?.settings) throw new Error("Backend did not return { settings: ... }");

        setSettings(res.settings);

        // prefill shipping/packaging from settings (as comma-friendly strings)
        setShippingRaw(String(res.settings.defaultShippingCost).replace(".", ","));
        setPackagingRaw(String(res.settings.defaultPackagingCost).replace(".", ","));
      } catch (e: any) {
        setError(e?.message ?? "Failed to load settings");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const buyCost = useMemo(() => parseLocaleNumber(buyCostRaw), [buyCostRaw]);
  const shippingCost = useMemo(() => parseLocaleNumber(shippingRaw), [shippingRaw]);
  const packagingCost = useMemo(() => parseLocaleNumber(packagingRaw), [packagingRaw]);

  const computed = useMemo(() => {
    if (!settings) return null;

    const mult = tierMultiplier(demandTier, settings);

    const feeRate = (settings.ebayFeePercent + settings.promoPercent) / 100;
    const denom = 1 - feeRate;

    const canComputeMin =
      buyCost !== null &&
      shippingCost !== null &&
      packagingCost !== null &&
      denom > 0;

    // A) Market-based (tier multiplier)
    const marketRaw = buyCost !== null ? buyCost * mult : NaN;
    const marketSuggested = roundMoney(marketRaw, settings.roundingMode);

    // B) Profit-floor price (covers shipping/packaging/fees + target profit)
    const totalCost =
      canComputeMin ? buyCost! + shippingCost! + packagingCost! : null;

    const minRaw =
      canComputeMin ? (totalCost! + settings.targetProfit) / denom : null;

    const minSuggested =
      minRaw !== null ? roundMoney(minRaw, settings.roundingMode) : null;

    // Final suggestion: choose the higher of the two (safe + market-aware)
    const finalSuggested =
      minSuggested !== null && Number.isFinite(marketSuggested)
        ? Math.max(minSuggested, marketSuggested)
        : Number.isFinite(marketSuggested)
          ? marketSuggested
          : minSuggested;

    // Estimate fees & profit at finalSuggested
    const feeAmount =
      finalSuggested !== null && totalCost !== null
        ? finalSuggested * feeRate
        : null;

    const profit =
      finalSuggested !== null && totalCost !== null && feeAmount !== null
        ? finalSuggested - totalCost - feeAmount
        : null;

    return {
      mult,
      feeRate,
      totalCost,
      marketRaw,
      marketSuggested,
      minRaw,
      minSuggested,
      finalSuggested,
      feeAmount,
      profit,
    };
  }, [settings, demandTier, buyCost, shippingCost, packagingCost]);

  async function onCreate() {
    setError(null);

    if (!settings) {
      setError("Settings not loaded yet.");
      return;
    }

    const base = process.env.NEXT_PUBLIC_API_URL;
    if (!base) {
      setError("NEXT_PUBLIC_API_URL is missing in .env.local");
      return;
    }

    const buy = parseLocaleNumber(buyCostRaw);
    const ship = parseLocaleNumber(shippingRaw);
    const pack = parseLocaleNumber(packagingRaw);

    if (!title.trim() || title.trim().length < 3) {
      setError("Title must be at least 3 characters.");
      return;
    }
    if (buy === null) {
      setError("Buy cost is invalid (comma or dot is fine).");
      return;
    }
    if (ship === null) {
      setError("Shipping cost is invalid (comma or dot is fine).");
      return;
    }
    if (pack === null) {
      setError("Packaging cost is invalid (comma or dot is fine).");
      return;
    }

    const mult = tierMultiplier(demandTier, settings);

    try {
      setSaving(true);

      // Backend currently stores only item fields; suggested price is computed client-side.
      const created = await apiPost<any>(`${base}/items`, {
        title: title.trim(),
        category: category.trim() ? category.trim() : null,
        buy_cost: buy,
        demand_tier: demandTier,
        multiplier: mult,
        status,
      });

      // Navigate to the item page
      if (created?.item_id) router.push(`/items/${created.item_id}`);
      else router.push(`/`);
    } catch (e: any) {
      setError(e?.message ?? "Failed to create item");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div style={{ padding: 24 }}>Loading…</div>;

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, margin: 0 }}>Add item</h1>
        <div style={{ display: "flex", gap: 12 }}>
          <Link href="/" style={{ textDecoration: "none" }}>Home</Link>
          <Link href="/settings" style={{ textDecoration: "none" }}>Settings</Link>
        </div>
      </div>

      <p style={{ color: "#666", marginTop: 8 }}>
        Demand tier automatically applies your saved multipliers. Suggested price uses shipping + packaging + fees + target profit + rounding.
      </p>

      {error && (
        <div style={{ background: "#ffecec", border: "1px solid #ffbcbc", padding: 12, borderRadius: 12, marginTop: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Title</div>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Levi’s 512 Slim Taper Jeans"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Category (optional)</div>
          <input
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="e.g. Jeans"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
        </label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginTop: 16 }}>
        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Buy cost (€)</div>
          <input
            type="text"
            inputMode="decimal"
            value={buyCostRaw}
            onChange={(e) => setBuyCostRaw(e.target.value)}
            placeholder="e.g. 10,50"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
          {buyCostRaw && buyCost === null && (
            <div style={{ fontSize: 12, color: "#a00", marginTop: 6 }}>Invalid number (comma or dot is fine)</div>
          )}
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Demand tier</div>
          <select
            value={demandTier}
            onChange={(e) => setDemandTier(e.target.value as DemandTier)}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            <option value="Low">Low</option>
            <option value="Medium">Medium</option>
            <option value="High">High</option>
          </select>
          <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
            Auto multiplier: <b>{settings ? tierMultiplier(demandTier, settings).toFixed(2) : "—"}</b>
          </div>
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Status</div>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ItemStatus)}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            <option value="Active">Active</option>
            <option value="Draft">Draft</option>
            <option value="Sold">Sold</option>
            <option value="Archived">Archived</option>
          </select>
        </label>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 16 }}>
        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Shipping cost (default from Settings)</div>
          <input
            type="text"
            inputMode="decimal"
            value={shippingRaw}
            onChange={(e) => setShippingRaw(e.target.value)}
            placeholder="e.g. 5,00"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
          {shippingRaw && shippingCost === null && (
            <div style={{ fontSize: 12, color: "#a00", marginTop: 6 }}>Invalid number</div>
          )}
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>Packaging cost (default from Settings)</div>
          <input
            type="text"
            inputMode="decimal"
            value={packagingRaw}
            onChange={(e) => setPackagingRaw(e.target.value)}
            placeholder="e.g. 0,50"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
          {packagingRaw && packagingCost === null && (
            <div style={{ fontSize: 12, color: "#a00", marginTop: 6 }}>Invalid number</div>
          )}
        </label>
      </div>

      <div style={{ marginTop: 18, padding: 14, border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ fontWeight: 900, marginBottom: 6 }}>Suggested price</div>

        {!settings ? (
          <div style={{ color: "#666" }}>Loading settings…</div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ color: "#666", fontSize: 12 }}>Market (tier multiplier)</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>
                  {computed && Number.isFinite(computed.marketSuggested)
                    ? formatEUR(computed.marketSuggested)
                    : "—"}
                </div>
              </div>

              <div>
                <div style={{ color: "#666", fontSize: 12 }}>Min to hit target profit</div>
                <div style={{ fontSize: 18, fontWeight: 800 }}>
                  {computed?.minSuggested !== null && computed?.minSuggested !== undefined
                    ? formatEUR(computed.minSuggested)
                    : "—"}
                </div>
              </div>
            </div>

            <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px dashed #eee" }}>
              <div style={{ color: "#666", fontSize: 12 }}>Final suggested (max of the two)</div>
              <div style={{ fontSize: 26, fontWeight: 900 }}>
                {computed?.finalSuggested !== null && computed?.finalSuggested !== undefined
                  ? formatEUR(computed.finalSuggested)
                  : "—"}
              </div>

              <div style={{ marginTop: 8, color: "#666", fontSize: 13 }}>
                Fees rate: <b>{settings.ebayFeePercent + settings.promoPercent}%</b> • Target profit:{" "}
                <b>{formatEUR(settings.targetProfit)}</b> • Rounding: <b>{settings.roundingMode}</b>
              </div>

              {computed?.totalCost !== null && computed?.totalCost !== undefined && (
                <div style={{ marginTop: 6, color: "#666", fontSize: 13 }}>
                  Total costs (buy + ship + pack): <b>{formatEUR(computed.totalCost)}</b>
                  {computed.feeAmount !== null && computed.profit !== null && (
                    <>
                      {" "}• Fee est.: <b>{formatEUR(computed.feeAmount)}</b> • Profit est.:{" "}
                      <b>{formatEUR(computed.profit)}</b>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      <button
        onClick={onCreate}
        disabled={saving}
        style={{
          marginTop: 16,
          width: "100%",
          padding: "12px 14px",
          borderRadius: 12,
          border: "none",
          fontWeight: 800,
          cursor: saving ? "not-allowed" : "pointer",
        }}
      >
        {saving ? "Creating…" : "Create item"}
      </button>

      <div style={{ marginTop: 10, fontSize: 12, color: "#666" }}>
        Tip: You can tune the multipliers in <Link href="/settings">Settings</Link>.
      </div>
    </div>
  );
}