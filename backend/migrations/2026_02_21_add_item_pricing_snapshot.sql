BEGIN;

ALTER TABLE items
  ADD COLUMN IF NOT EXISTS suggested_price      NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS min_price            NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS market_price         NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS estimated_profit     NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS total_fee_percent    NUMERIC(6,3),
  ADD COLUMN IF NOT EXISTS sale_price           NUMERIC(10,2),
  ADD COLUMN IF NOT EXISTS sold_at              TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_items_status  ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_sold_at ON items(sold_at);

ALTER TABLE items
  DROP CONSTRAINT IF EXISTS chk_items_sold_fields;

ALTER TABLE items
  ADD CONSTRAINT chk_items_sold_fields
  CHECK (
    (status <> 'SOLD') OR (sale_price IS NOT NULL AND sold_at IS NOT NULL)
  );

COMMIT;