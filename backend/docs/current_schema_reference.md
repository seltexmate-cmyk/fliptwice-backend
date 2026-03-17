# FlipTwice Current Schema Reference

Last updated: 2026-03-17

## Purpose

This file is the **working source of truth** for the current live FlipTwice backend schema and key architecture rules.

It exists to reduce mistakes during development by keeping the most important structural facts in one place.

Use this file at the start of each FlipTwice work session.

---

## Source-of-truth rule

When there is a mismatch between:
- old architecture notes
- older diagrams
- PDF schema drafts
- repo assumptions
- current code

the final truth is:

1. the live database schema
2. the current working backend code
3. this file, once updated to match both

---

## Core naming rules

### Businesses
- Table: `businesses`
- Primary key: `id`

### Items
- Table: `items`
- Primary key: `item_id`
- Business ownership column: `business_id`

### Marketplace listings
- Table: `marketplace_listings`
- Primary key: `id`
- Business ownership column: `business_id`
- Item reference column: `item_id`

---

## Confirmed key table structure

## `businesses`
Primary key:
- `id`

Confirmed important columns:
- `id`
- `name`
- `country_code`
- `currency_code`
- `vat_enabled`
- `created_at`

Notes:
- `businesses.id` is the canonical business primary key.
- Any foreign key pointing to businesses must reference `businesses.id`.

---

## `items`
Primary key:
- `item_id`

Confirmed important columns:
- `item_id`
- `title`
- `category`
- `buy_cost`
- `demand_tier`
- `multiplier`
- `created_at`
- `status`
- `notes`
- `suggested_price`
- `min_price`
- `market_price`
- `estimated_profit`
- `total_fee_percent`
- `sale_price`
- `sold_at`
- `status_updated_at`
- `active_at`
- `archived_at`
- `business_id`
- `safe_to_sell`
- `safe_to_sell_reason`
- `deleted_at`
- `deleted_by`
- `restored_by`

Notes:
- `items.item_id` is the canonical item primary key.
- Do **not** assume `items.id` exists.
- Repo queries must use `item_id` in SQL.
- If legacy Python code expects `row["id"]`, it is acceptable to alias:
  - `item_id::text AS id`
- Item ownership is scoped by `items.business_id`.

---

## `marketplace_listings`
Primary key:
- `id`

Purpose:
- Stores one marketplace listing state per item per platform.
- This is the backbone for multi-marketplace publishing.

Current intended columns:
- `id`
- `business_id`
- `item_id`
- `platform`
- `marketplace_account_id`
- `external_inventory_key`
- `external_offer_id`
- `external_listing_id`
- `status`
- `publish_status`
- `sync_status`
- `last_error`
- `last_error_code`
- `raw_response`
- `published_at`
- `last_synced_at`
- `last_publish_attempt_at`
- `created_at`
- `updated_at`

Key constraints:
- foreign key: `business_id -> businesses.id`
- foreign key: `item_id -> items.item_id`
- unique: `(item_id, platform)`

Notes:
- One FlipTwice item can have one row per platform.
- Example:
  - one eBay row
  - one Vinted row
  - one Depop row

---

## Marketplace architecture rules

### Current direction
FlipTwice is being built as a marketplace orchestration backend.

Current priority:
- eBay first
- later:
  - Vinted
  - Depop
  - Vestiaire
  - Facebook Marketplace

### Important rule
Marketplace state should **not** be stored directly on `items`.

Use:
- `items` for internal item state
- `marketplace_listings` for external marketplace state

---

## Current eBay integration structure

Path:
- `backend/app/integrations/ebay`

Current files:
- `mapper.py`
- `repo.py`
- `routes.py`
- `schemas.py`
- `service.py`

Current integration capabilities:
- OAuth login
- token storage
- token refresh
- inventory API communication
- offer creation testing
- publish attempt testing

Confirmed eBay pipeline:
1. inventory item
2. offer
3. publish
4. listing/live state

Important:
- Sandbox publish may return `UNPUBLISHED`
- This does not invalidate the integration architecture

---

## Repo-layer compatibility rules

### Important historical mismatch
Some legacy repo/service code was written assuming:
- `items.id`

Current live schema uses:
- `items.item_id`

### Required fix pattern
When querying `items`, use SQL like:

```sql
SELECT item_id::text AS id
FROM items
WHERE business_id = %s::uuid
  AND item_id = %s::uuid