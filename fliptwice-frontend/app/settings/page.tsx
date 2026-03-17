"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet, apiPut } from "@/lib/api";
import { parseLocaleNumber } from "@/lib/number";

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

  // NEW (may not be persisted yet on backend; safe defaults used)
  demandLowMultiplier?: number;
  demandMediumMultiplier?: number;
  demandHighMultiplier?: number;
};

type SettingsResponse = { settings: BusinessSettings };

function NumInput(props: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  placeholder?: string;
}) {
  return (
    <label style={{ display: "block", marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>{props.label}</div>
      <input
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        inputMode="decimal"
        placeholder={props.placeholder ?? "e.g. 6,50"}
        style={{
          width: "100%",
          padding: "10px 12px",
          borderRadius: 10,
          border: "1px solid #ddd",
        }}
      />
      {props.hint && (
        <div style={{ fontSize: 12, color: "#666", marginTop: 6 }}>
          {props.hint}
        </div>
      )}
    </label>
  );
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Numeric fields stored as strings so the user can type "6," etc.
  const [form, setForm] = useState({
    currency: "EUR",
    countryFrom: "BG",
    mainMarketplace: "ebay.de",

    defaultShippingCost: "6",
    defaultPackagingCost: "0,50",

    ebayFeePercent: "13",
    promoPercent: "0",
    targetProfit: "5",

    roundingMode: "END_99" as "NONE" | "END_99",

    // NEW demand multipliers (defaults)
    demandLowMultiplier: "2,2",
    demandMediumMultiplier: "2,6",
    demandHighMultiplier: "3,2",
  });

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setError(null);

        const base = process.env.NEXT_PUBLIC_API_URL;
        if (!base) throw new Error("NEXT_PUBLIC_API_URL is missing in .env.local");

        const data = await apiGet<SettingsResponse>(`${base}/business-settings`);
        const s = data?.settings;
        if (!s) throw new Error("Backend did not return { settings: ... }");

        // Defaults for new fields if backend doesn't have them yet
        const lowM = s.demandLowMultiplier ?? 2.2;
        const medM = s.demandMediumMultiplier ?? 2.6;
        const highM = s.demandHighMultiplier ?? 3.2;

        setForm({
          currency: s.currency ?? "EUR",
          countryFrom: (s.countryFrom ?? "BG").toUpperCase(),
          mainMarketplace: s.mainMarketplace ?? "ebay.de",

          defaultShippingCost: String(s.defaultShippingCost ?? 6).replace(".", ","),
          defaultPackagingCost: String(s.defaultPackagingCost ?? 0.5).replace(".", ","),

          ebayFeePercent: String(s.ebayFeePercent ?? 13).replace(".", ","),
          promoPercent: String(s.promoPercent ?? 0).replace(".", ","),
          targetProfit: String(s.targetProfit ?? 5).replace(".", ","),

          roundingMode: s.roundingMode ?? "END_99",

          demandLowMultiplier: String(lowM).replace(".", ","),
          demandMediumMultiplier: String(medM).replace(".", ","),
          demandHighMultiplier: String(highM).replace(".", ","),
        });
      } catch (e: any) {
        setError(e?.message ?? "Failed to load settings");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const payload: BusinessSettings | null = useMemo(() => {
    const defaultShippingCost = parseLocaleNumber(form.defaultShippingCost);
    const defaultPackagingCost = parseLocaleNumber(form.defaultPackagingCost);

    const ebayFeePercent = parseLocaleNumber(form.ebayFeePercent);
    const promoPercent = parseLocaleNumber(form.promoPercent);
    const targetProfit = parseLocaleNumber(form.targetProfit);

    const demandLowMultiplier = parseLocaleNumber(form.demandLowMultiplier);
    const demandMediumMultiplier = parseLocaleNumber(form.demandMediumMultiplier);
    const demandHighMultiplier = parseLocaleNumber(form.demandHighMultiplier);

    if (
      defaultShippingCost === null ||
      defaultPackagingCost === null ||
      ebayFeePercent === null ||
      promoPercent === null ||
      targetProfit === null ||
      demandLowMultiplier === null ||
      demandMediumMultiplier === null ||
      demandHighMultiplier === null
    ) {
      return null;
    }

    return {
      currency: form.currency,
      countryFrom: form.countryFrom,
      mainMarketplace: form.mainMarketplace,

      defaultShippingCost,
      defaultPackagingCost,

      ebayFeePercent,
      promoPercent,
      targetProfit,

      roundingMode: form.roundingMode,

      demandLowMultiplier,
      demandMediumMultiplier,
      demandHighMultiplier,
    };
  }, [form]);

  async function onSave() {
    setError(null);
    if (!payload) {
      setError("Please fix numeric fields (comma or dot is fine).");
      return;
    }

    try {
      setSaving(true);

      const base = process.env.NEXT_PUBLIC_API_URL;
      if (!base) throw new Error("NEXT_PUBLIC_API_URL is missing in .env.local");

      await apiPut<SettingsResponse>(`${base}/business-settings`, payload);
    } catch (e: any) {
      setError(e?.message ?? "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div style={{ padding: 24 }}>Loading settings…</div>;

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 8 }}>Settings</h1>
      <p style={{ color: "#666", marginBottom: 24 }}>
        These defaults are used in Add/Edit calculations (shipping, fees, target profit, rounding, demand tiers).
      </p>

      {error && (
        <div
          style={{
            background: "#ffecec",
            border: "1px solid #ffbcbc",
            padding: 12,
            borderRadius: 12,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Currency</div>
          <select
            value={form.currency}
            onChange={(e) => setForm((f) => ({ ...f, currency: e.target.value }))}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            <option value="EUR">EUR</option>
            <option value="USD">USD</option>
            <option value="GBP">GBP</option>
          </select>
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Main marketplace</div>
          <select
            value={form.mainMarketplace}
            onChange={(e) => setForm((f) => ({ ...f, mainMarketplace: e.target.value }))}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            <option value="ebay.de">eBay.de</option>
            <option value="ebay.com">eBay.com</option>
            <option value="ebay.co.uk">eBay UK</option>
          </select>
        </label>
      </div>

      <div style={{ height: 16 }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Ship from (country code)</div>
          <input
            value={form.countryFrom}
            onChange={(e) => setForm((f) => ({ ...f, countryFrom: e.target.value.toUpperCase() }))}
            placeholder="BG"
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          />
        </label>

        <label style={{ display: "block" }}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Rounding</div>
          <select
            value={form.roundingMode}
            onChange={(e) => setForm((f) => ({ ...f, roundingMode: e.target.value as any }))}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 10, border: "1px solid #ddd" }}
          >
            <option value="END_99">End with .99</option>
            <option value="NONE">No rounding</option>
          </select>
        </label>
      </div>

      <div style={{ height: 16 }} />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <NumInput
          label="Default shipping cost"
          value={form.defaultShippingCost}
          onChange={(v) => setForm((f) => ({ ...f, defaultShippingCost: v }))}
          hint="Comma or dot accepted (e.g. 6,50)."
        />
        <NumInput
          label="Default packaging cost"
          value={form.defaultPackagingCost}
          onChange={(v) => setForm((f) => ({ ...f, defaultPackagingCost: v }))}
        />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <NumInput
          label="eBay fee %"
          value={form.ebayFeePercent}
          onChange={(v) => setForm((f) => ({ ...f, ebayFeePercent: v }))}
          hint="Example: 13 means 13%."
        />
        <NumInput
          label="Promo %"
          value={form.promoPercent}
          onChange={(v) => setForm((f) => ({ ...f, promoPercent: v }))}
        />
      </div>

      <NumInput
        label="Target profit"
        value={form.targetProfit}
        onChange={(v) => setForm((f) => ({ ...f, targetProfit: v }))}
        hint="Used when calculating suggested price."
      />

      <div style={{ height: 16 }} />

      <div style={{ fontWeight: 800, marginBottom: 8 }}>Demand tier multipliers</div>
      <p style={{ marginTop: 0, marginBottom: 12, color: "#666" }}>
        These control suggested price based on demand tier (Low / Medium / High).
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
        <NumInput
          label="Low"
          value={form.demandLowMultiplier}
          onChange={(v) => setForm((f) => ({ ...f, demandLowMultiplier: v }))}
          placeholder="e.g. 2,2"
        />
        <NumInput
          label="Medium"
          value={form.demandMediumMultiplier}
          onChange={(v) => setForm((f) => ({ ...f, demandMediumMultiplier: v }))}
          placeholder="e.g. 2,6"
        />
        <NumInput
          label="High"
          value={form.demandHighMultiplier}
          onChange={(v) => setForm((f) => ({ ...f, demandHighMultiplier: v }))}
          placeholder="e.g. 3,2"
        />
      </div>

      <button
        onClick={onSave}
        disabled={saving}
        style={{
          marginTop: 8,
          width: "100%",
          padding: "12px 14px",
          borderRadius: 12,
          border: "none",
          fontWeight: 700,
          cursor: saving ? "not-allowed" : "pointer",
        }}
      >
        {saving ? "Saving…" : "Save settings"}
      </button>

      {!payload && (
        <div style={{ marginTop: 10, fontSize: 12, color: "#a00" }}>
          Some numeric values are invalid. Use digits + comma/dot only.
        </div>
      )}
    </div>
  );
}