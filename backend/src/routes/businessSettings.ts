import { Router } from "express";
import { z } from "zod";
// import { requireAuth } from "../middleware/requireAuth";
import { getBusinessSettings, upsertBusinessSettings } from "../repos/businessSettingsRepo";

const router = Router();

const BusinessSettingsSchema = z.object({
  currency: z.string().min(1).default("EUR"),
  countryFrom: z.string().min(2).max(2).default("BG"), // e.g., "BG"
  mainMarketplace: z.string().min(1).default("ebay.de"),
  defaultShippingCost: z.number().nonnegative().default(6),
  defaultPackagingCost: z.number().nonnegative().default(0.5),

  ebayFeePercent: z.number().min(0).max(100).default(13),      // 0–100
  promoPercent: z.number().min(0).max(100).default(0),         // 0–100
  targetProfit: z.number().nonnegative().default(5),

  roundingMode: z.enum(["NONE", "END_99"]).default("END_99"),  // your “.99” rounding
});

router.get("/", /*requireAuth,*/ async (req, res) => {
  const userId = (req as any).user?.id ?? "demo-user";
  const settings = await getBusinessSettings(userId);
  res.json({ settings });
});

router.put("/", /*requireAuth,*/ async (req, res) => {
  const userId = (req as any).user?.id ?? "demo-user";

  // IMPORTANT: numbers must already be numbers here (frontend will parse comma/dot).
  const parsed = BusinessSettingsSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: "Invalid payload", details: parsed.error.flatten() });
  }

  const saved = await upsertBusinessSettings(userId, parsed.data);
  res.json({ settings: saved });
});

export default router;