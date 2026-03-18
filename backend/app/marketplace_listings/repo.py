from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor


def _normalize_database_url(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("postgresql+psycopg2://"):
        return raw.replace("postgresql+psycopg2://", "postgresql://", 1)
    return raw


def _get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    return _normalize_database_url(database_url)


def get_conn():
    return psycopg2.connect(_get_database_url())


def get_marketplace_listing_by_item_and_platform(
    *,
    business_id: str,
    item_id: str,
    platform: str,
) -> Optional[Dict[str, Any]]:
    sql_text = """
    SELECT
        id::text,
        business_id::text,
        item_id::text,
        platform,
        marketplace_account_id::text,
        external_inventory_key,
        external_offer_id,
        external_listing_id,
        status,
        publish_status,
        sync_status,
        last_error,
        last_error_code,
        raw_response,
        published_at,
        last_synced_at,
        last_publish_attempt_at,
        created_at,
        updated_at
    FROM marketplace_listings
    WHERE business_id = %(business_id)s::uuid
      AND item_id = %(item_id)s::uuid
      AND platform = %(platform)s
    LIMIT 1
    ;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql_text,
                {
                    "business_id": business_id,
                    "item_id": item_id,
                    "platform": platform,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def create_marketplace_listing(
    *,
    business_id: str,
    item_id: str,
    platform: str,
    marketplace_account_id: Optional[str] = None,
    external_inventory_key: Optional[str] = None,
    external_offer_id: Optional[str] = None,
    external_listing_id: Optional[str] = None,
    status: str = "draft",
    publish_status: str = "not_started",
    sync_status: str = "pending",
    last_error: Optional[str] = None,
    last_error_code: Optional[str] = None,
    raw_response: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sql_text = """
    INSERT INTO marketplace_listings (
        id,
        business_id,
        item_id,
        platform,
        marketplace_account_id,
        external_inventory_key,
        external_offer_id,
        external_listing_id,
        status,
        publish_status,
        sync_status,
        last_error,
        last_error_code,
        raw_response,
        created_at,
        updated_at
    )
    VALUES (
        %(id)s::uuid,
        %(business_id)s::uuid,
        %(item_id)s::uuid,
        %(platform)s,
        %(marketplace_account_id)s::uuid,
        %(external_inventory_key)s,
        %(external_offer_id)s,
        %(external_listing_id)s,
        %(status)s,
        %(publish_status)s,
        %(sync_status)s,
        %(last_error)s,
        %(last_error_code)s,
        %(raw_response)s,
        NOW(),
        NOW()
    )
    RETURNING
        id::text,
        business_id::text,
        item_id::text,
        platform,
        marketplace_account_id::text,
        external_inventory_key,
        external_offer_id,
        external_listing_id,
        status,
        publish_status,
        sync_status,
        last_error,
        last_error_code,
        raw_response,
        published_at,
        last_synced_at,
        last_publish_attempt_at,
        created_at,
        updated_at
    ;
    """

    params = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "item_id": item_id,
        "platform": platform,
        "marketplace_account_id": marketplace_account_id,
        "external_inventory_key": external_inventory_key,
        "external_offer_id": external_offer_id,
        "external_listing_id": external_listing_id,
        "status": status,
        "publish_status": publish_status,
        "sync_status": sync_status,
        "last_error": last_error,
        "last_error_code": last_error_code,
        "raw_response": Json(raw_response) if raw_response is not None else None,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def create_or_get_marketplace_listing(
    *,
    business_id: str,
    item_id: str,
    platform: str,
    marketplace_account_id: Optional[str] = None,
    external_inventory_key: Optional[str] = None,
    status: str = "draft",
    publish_status: str = "not_started",
    sync_status: str = "pending",
) -> Dict[str, Any]:
    existing = get_marketplace_listing_by_item_and_platform(
        business_id=business_id,
        item_id=item_id,
        platform=platform,
    )
    if existing:
        return existing

    return create_marketplace_listing(
        business_id=business_id,
        item_id=item_id,
        platform=platform,
        marketplace_account_id=marketplace_account_id,
        external_inventory_key=external_inventory_key,
        status=status,
        publish_status=publish_status,
        sync_status=sync_status,
    )


def update_marketplace_listing_publish_state(
    *,
    listing_id: str,
    status: Optional[str] = None,
    publish_status: Optional[str] = None,
    sync_status: Optional[str] = None,
    external_inventory_key: Optional[str] = None,
    external_offer_id: Optional[str] = None,
    external_listing_id: Optional[str] = None,
    raw_response: Optional[Dict[str, Any]] = None,
    published_at_now: bool = False,
    last_synced_at_now: bool = False,
    last_publish_attempt_at_now: bool = True,
    clear_error: bool = False,
) -> Dict[str, Any]:
    sql_text = """
    UPDATE marketplace_listings
    SET
        status = COALESCE(%(status)s, status),
        publish_status = COALESCE(%(publish_status)s, publish_status),
        sync_status = COALESCE(%(sync_status)s, sync_status),
        external_inventory_key = COALESCE(%(external_inventory_key)s, external_inventory_key),
        external_offer_id = COALESCE(%(external_offer_id)s, external_offer_id),
        external_listing_id = COALESCE(%(external_listing_id)s, external_listing_id),
        raw_response = COALESCE(%(raw_response)s, raw_response),
        published_at = CASE
            WHEN %(published_at_now)s THEN NOW()
            ELSE published_at
        END,
        last_synced_at = CASE
            WHEN %(last_synced_at_now)s THEN NOW()
            ELSE last_synced_at
        END,
        last_publish_attempt_at = CASE
            WHEN %(last_publish_attempt_at_now)s THEN NOW()
            ELSE last_publish_attempt_at
        END,
        last_error = CASE
            WHEN %(clear_error)s THEN NULL
            ELSE last_error
        END,
        last_error_code = CASE
            WHEN %(clear_error)s THEN NULL
            ELSE last_error_code
        END,
        updated_at = NOW()
    WHERE id = %(listing_id)s::uuid
    RETURNING
        id::text,
        business_id::text,
        item_id::text,
        platform,
        marketplace_account_id::text,
        external_inventory_key,
        external_offer_id,
        external_listing_id,
        status,
        publish_status,
        sync_status,
        last_error,
        last_error_code,
        raw_response,
        published_at,
        last_synced_at,
        last_publish_attempt_at,
        created_at,
        updated_at
    ;
    """

    params = {
        "listing_id": listing_id,
        "status": status,
        "publish_status": publish_status,
        "sync_status": sync_status,
        "external_inventory_key": external_inventory_key,
        "external_offer_id": external_offer_id,
        "external_listing_id": external_listing_id,
        "raw_response": Json(raw_response) if raw_response is not None else None,
        "published_at_now": published_at_now,
        "last_synced_at_now": last_synced_at_now,
        "last_publish_attempt_at_now": last_publish_attempt_at_now,
        "clear_error": clear_error,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise RuntimeError("Marketplace listing not found")

    return dict(row)


def mark_marketplace_listing_error(
    *,
    listing_id: str,
    status: str = "error",
    publish_status: str = "failed",
    sync_status: Optional[str] = None,
    error_message: str,
    error_code: Optional[str] = None,
    raw_response: Optional[Dict[str, Any]] = None,
    last_publish_attempt_at_now: bool = True,
) -> Dict[str, Any]:
    sql_text = """
    UPDATE marketplace_listings
    SET
        status = %(status)s,
        publish_status = %(publish_status)s,
        sync_status = COALESCE(%(sync_status)s, sync_status),
        last_error = %(error_message)s,
        last_error_code = %(error_code)s,
        raw_response = COALESCE(%(raw_response)s, raw_response),
        last_publish_attempt_at = CASE
            WHEN %(last_publish_attempt_at_now)s THEN NOW()
            ELSE last_publish_attempt_at
        END,
        updated_at = NOW()
    WHERE id = %(listing_id)s::uuid
    RETURNING
        id::text,
        business_id::text,
        item_id::text,
        platform,
        marketplace_account_id::text,
        external_inventory_key,
        external_offer_id,
        external_listing_id,
        status,
        publish_status,
        sync_status,
        last_error,
        last_error_code,
        raw_response,
        published_at,
        last_synced_at,
        last_publish_attempt_at,
        created_at,
        updated_at
    ;
    """

    params = {
        "listing_id": listing_id,
        "status": status,
        "publish_status": publish_status,
        "sync_status": sync_status,
        "error_message": error_message,
        "error_code": error_code,
        "raw_response": Json(raw_response) if raw_response is not None else None,
        "last_publish_attempt_at_now": last_publish_attempt_at_now,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    if not row:
        raise RuntimeError("Marketplace listing not found")

    return dict(row)

def get_marketplace_listing_for_item(
    *,
    business_id: str,
    item_id: str,
    platform: str,
) -> Optional[Dict[str, Any]]:
    sql_text = """
    SELECT
        id::text,
        business_id::text,
        item_id::text,
        platform,
        status,
        publish_status,
        sync_status,
        external_listing_id,
        external_offer_id,
        last_error
    FROM marketplace_listings
    WHERE business_id = %(business_id)s::uuid
      AND item_id = %(item_id)s::uuid
      AND platform = %(platform)s
    LIMIT 1
    ;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql_text,
                {
                    "business_id": business_id,
                    "item_id": item_id,
                    "platform": platform,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None