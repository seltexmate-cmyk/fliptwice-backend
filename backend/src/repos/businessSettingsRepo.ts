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

// Replace with your DB (Prisma/SQL/etc.)
const inMemory = new Map<string, BusinessSettings>();

const DEFAULTS: BusinessSettings = {
  currency: "EUR",
  countryFrom: "BG",
  mainMarketplace: "ebay.de",
  defaultShippingCost: 6,
  defaultPackagingCost: 0.5,
  ebayFeePercent: 13,
  promoPercent: 0,
  targetProfit: 5,
  roundingMode: "END_99",
};

export async function getBusinessSettings(userId: string): Promise<BusinessSettings> {
  return inMemory.get(userId) ?? DEFAULTS;
}

export async function upsertBusinessSettings(
  userId: string,
  input: BusinessSettings
): Promise<BusinessSettings> {
  inMemory.set(userId, input);
  return input;
}