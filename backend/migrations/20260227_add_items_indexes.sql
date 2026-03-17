-- backend/migrations/20260227_add_items_indexes.sql
-- Production indexes for items table (multi-tenant SaaS)
-- Safe to run multiple times (IF NOT EXISTS).

BEGIN;

-- Always filter by business_id in SaaS:
CREATE INDEX IF NOT EXISTS idx_items_business_id
  ON items (business_id);

-- Common list filter:
CREATE INDEX IF NOT EXISTS idx_items_business_status
  ON items (business_id, status);

-- Safe-to-sell filtering:
CREATE INDEX IF NOT EXISTS idx_items_business_safe_to_sell
  ON items (business_id, safe_to_sell);

-- Sorting for list pages (created_at if present)
-- If your items table has created_at, this helps ORDER BY created_at DESC.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name='items' AND column_name='created_at'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_items_business_created_at_desc ON items (business_id, created_at DESC)';
  END IF;
END $$;

COMMIT;
