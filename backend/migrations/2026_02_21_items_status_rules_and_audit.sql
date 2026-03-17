BEGIN;

-- 1) Fix SOLD constraint mismatch (yours currently checks 'SOLD' uppercase)
--    We want Title Case: 'Sold'
ALTER TABLE items
  DROP CONSTRAINT IF EXISTS chk_items_sold_fields;

ALTER TABLE items
  ADD CONSTRAINT chk_items_sold_fields
  CHECK (
    (status <> 'Sold') OR (sale_price IS NOT NULL AND sold_at IS NOT NULL)
  );

-- 2) Ensure status check constraint contains Draft (if not already)
ALTER TABLE items
  DROP CONSTRAINT IF EXISTS items_status_check;

ALTER TABLE items
  ADD CONSTRAINT items_status_check
  CHECK (
    status IN ('Draft', 'Active', 'Sold', 'Archived')
  );

-- 3) Add timestamps to track lifecycle (simple + useful)
ALTER TABLE items
  ADD COLUMN IF NOT EXISTS status_updated_at TIMESTAMP DEFAULT now(),
  ADD COLUMN IF NOT EXISTS active_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP;

-- 4) Audit log table: every status change is recorded
CREATE TABLE IF NOT EXISTS item_status_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id UUID NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  old_status TEXT,
  new_status TEXT NOT NULL,
  changed_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_item_status_events_item_id ON item_status_events(item_id);
CREATE INDEX IF NOT EXISTS idx_item_status_events_changed_at ON item_status_events(changed_at);

COMMIT;