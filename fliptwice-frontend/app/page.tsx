"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiGet } from "./lib/api";

function statusLabel(s: string) {
  return (
    {
      Active: "Active",
      Draft: "Draft",
      Sold: "Sold",
      Archived: "Archived",
    }[s] || s
  );
}

export default function Home() {
  const [settings, setSettings] = useState<any>(null);
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const base = process.env.NEXT_PUBLIC_API_URL;
        if (!base) throw new Error("NEXT_PUBLIC_API_URL is missing in .env.local");

        const settingsRes = await apiGet<any>(`${base}/business-settings`);
if (!settingsRes || !settingsRes.settings) {
  throw new Error("Backend did not return { settings: ... }");
}
setSettings(settingsRes.settings);
      } catch (e: any) {
        setError(e.message ?? "Failed to load");
      }
    })();
  }, []);

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800 }}>Fliptwice</h1>
        <div style={{ display: "flex", gap: 10 }}>
          <Link href="/items/new">Add item</Link>
          <Link href="/settings">Settings</Link>
        </div>
      </div>

      {error && (
        <div style={{ marginTop: 16, background: "#ffecec", border: "1px solid #ffbcbc", padding: 12, borderRadius: 12 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 16, padding: 12, border: "1px solid #eee", borderRadius: 12 }}>
        <div style={{ fontWeight: 700, marginBottom: 6 }}>Current settings</div>
        <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{settings ? JSON.stringify(settings, null, 2) : "Loading…"}</pre>
      </div>

      <h2 style={{ marginTop: 20, fontSize: 18, fontWeight: 800 }}>Items</h2>
      <div style={{ marginTop: 10 }}>
        {items.length === 0 ? (
          <div style={{ color: "#666" }}>No items yet.</div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {items.map((it) => (
              <Link
                key={it.item_id}
                href={`/items/${it.item_id}`}
                style={{
                  display: "block",
                  padding: 12,
                  border: "1px solid #eee",
                  borderRadius: 12,
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <div style={{ fontWeight: 800 }}>{it.title}</div>
                <div style={{ color: "#666", fontSize: 13 }}>
                  {it.category || "—"} • {statusLabel(it.status)}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}