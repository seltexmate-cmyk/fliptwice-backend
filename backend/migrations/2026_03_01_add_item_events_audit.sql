CREATE TABLE IF NOT EXISTS item_events (
  event_id UUID PRIMARY KEY,
  business_id UUID NOT NULL,
  item_id UUID NOT NULL,
  event_type TEXT NOT NULL,
  details JSONB NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_item_events_business_item_created
  ON item_events (business_id, item_id, created_at);

CREATE INDEX IF NOT EXISTS idx_item_events_business_type_created
  ON item_events (business_id, event_type, created_at);
