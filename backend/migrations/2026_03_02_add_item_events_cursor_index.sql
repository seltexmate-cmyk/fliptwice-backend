-- Supports GET /items/{item_id}/events cursor pagination
-- Query pattern:
--   WHERE business_id = ? AND item_id = ?
--   AND (created_at, event_id) < (?, ?)
--   ORDER BY created_at DESC, event_id DESC

CREATE INDEX IF NOT EXISTS idx_item_events_business_item_created_event
  ON item_events (business_id, item_id, created_at DESC, event_id DESC);
