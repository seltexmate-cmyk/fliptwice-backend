# FlipTwice Marketplace Publishing System (Batch 2E)

## Overview

FlipTwice now supports a full marketplace publishing pipeline for eBay with:

- OAuth integration
- Token refresh
- Inventory item creation
- Offer creation
- Publish attempt
- Persistent marketplace state tracking
- Idempotent retry logic
- Structured partial-success responses

---

## Core Flow

FlipTwice Item → eBay Pipeline:

1. Load item (repo)
2. Validate business + integration
3. Ensure valid access token
4. Create or reuse marketplace_listings row
5. Upsert inventory item (SKU-based)
6. Create offer (if not already created)
7. Publish offer
8. Persist result (success OR failure)

---

## Database: marketplace_listings

Tracks marketplace state per item.

### Key Fields

- `external_inventory_key` → SKU
- `external_offer_id` → eBay offer ID
- `external_listing_id` → eBay listing ID (after publish)
- `status`
- `publish_status`
- `sync_status`
- `last_error`

---

## State Behavior

### Success
- inventory_created = true
- offer_created = true
- published = true

### Partial Success (current sandbox case)
- inventory_created = true
- offer_created = true
- published = false
- retry_possible = true

### Failure
- error stored in DB
- safe retry enabled

---

## Idempotency (Important)

System now prevents duplication:

- If `external_offer_id` exists → reuse it
- Do NOT recreate offer
- Continue directly to publish

---

## Structured Response (NEW)

Instead of crashing, publish returns:

```json
{
  "platform": "ebay",
  "sku": "...",
  "offer_id": "...",
  "inventory_created": true,
  "offer_created": true,
  "published": false,
  "retry_possible": true,
  "status": "error",
  "publish_status": "failed",
  "sync_status": "sync_failed",
  "error": "eBay API error..."
}