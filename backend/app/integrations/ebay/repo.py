from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import psycopg2
from psycopg2 import sql
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


def _get_table_columns(table_name: str) -> set[str]:
    sql_text = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = %(table_name)s
    ;
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, {"table_name": table_name})
            rows = cur.fetchall()
    return {row[0] for row in rows}


def upsert_platform_integration(
    *,
    business_id: str,
    platform: str,
    environment: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expires_at: Optional[datetime],
    refresh_token_expires_at: Optional[datetime],
    scopes: Optional[str],
    external_account_id: Optional[str] = None,
    external_username: Optional[str] = None,
    status: str = "active",
    last_error: Optional[str] = None,
) -> Dict[str, Any]:
    sql_text = """
    INSERT INTO platform_integrations (
        id,
        business_id,
        platform,
        environment,
        external_account_id,
        external_username,
        access_token,
        refresh_token,
        token_expires_at,
        refresh_token_expires_at,
        scopes,
        status,
        last_error,
        created_at,
        updated_at
    )
    VALUES (
        %(id)s,
        %(business_id)s::uuid,
        %(platform)s,
        %(environment)s,
        %(external_account_id)s,
        %(external_username)s,
        %(access_token)s,
        %(refresh_token)s,
        %(token_expires_at)s,
        %(refresh_token_expires_at)s,
        %(scopes)s,
        %(status)s,
        %(last_error)s,
        NOW(),
        NOW()
    )
    ON CONFLICT (business_id, platform, environment)
    DO UPDATE SET
        external_account_id = EXCLUDED.external_account_id,
        external_username = EXCLUDED.external_username,
        access_token = EXCLUDED.access_token,
        refresh_token = EXCLUDED.refresh_token,
        token_expires_at = EXCLUDED.token_expires_at,
        refresh_token_expires_at = EXCLUDED.refresh_token_expires_at,
        scopes = EXCLUDED.scopes,
        status = EXCLUDED.status,
        last_error = EXCLUDED.last_error,
        updated_at = NOW()
    RETURNING
        id,
        business_id::text,
        platform,
        environment,
        external_account_id,
        external_username,
        access_token,
        refresh_token,
        token_expires_at,
        refresh_token_expires_at,
        scopes,
        status,
        last_sync_at,
        last_error,
        created_at,
        updated_at
    ;
    """

    params = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "platform": platform,
        "environment": environment,
        "external_account_id": external_account_id,
        "external_username": external_username,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "refresh_token_expires_at": refresh_token_expires_at,
        "scopes": scopes,
        "status": status,
        "last_error": last_error,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def update_platform_integration_tokens(
    *,
    integration_id: str,
    access_token: str,
    refresh_token: Optional[str],
    token_expires_at: Optional[datetime],
    refresh_token_expires_at: Optional[datetime],
    scopes: Optional[str],
    status: str = "active",
    last_error: Optional[str] = None,
) -> Dict[str, Any]:
    sql_text = """
    UPDATE platform_integrations
    SET
        access_token = %(access_token)s,
        refresh_token = COALESCE(%(refresh_token)s, refresh_token),
        token_expires_at = %(token_expires_at)s,
        refresh_token_expires_at = %(refresh_token_expires_at)s,
        scopes = %(scopes)s,
        status = %(status)s,
        last_error = %(last_error)s,
        updated_at = NOW()
    WHERE id = %(integration_id)s::uuid
    RETURNING
        id,
        business_id::text,
        platform,
        environment,
        external_account_id,
        external_username,
        access_token,
        refresh_token,
        token_expires_at,
        refresh_token_expires_at,
        scopes,
        status,
        last_sync_at,
        last_error,
        created_at,
        updated_at
    ;
    """

    params = {
        "integration_id": integration_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "refresh_token_expires_at": refresh_token_expires_at,
        "scopes": scopes,
        "status": status,
        "last_error": last_error,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def get_platform_integration(
    *,
    business_id: str,
    platform: str,
    environment: str,
) -> Optional[Dict[str, Any]]:
    sql_text = """
    SELECT
        id,
        business_id::text,
        platform,
        environment,
        external_account_id,
        external_username,
        access_token,
        refresh_token,
        token_expires_at,
        refresh_token_expires_at,
        scopes,
        status,
        last_sync_at,
        last_error,
        created_at,
        updated_at
    FROM platform_integrations
    WHERE business_id = %(business_id)s::uuid
      AND platform = %(platform)s
      AND environment = %(environment)s
    LIMIT 1
    ;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql_text,
                {
                    "business_id": business_id,
                    "platform": platform,
                    "environment": environment,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def touch_platform_last_sync(
    *,
    integration_id: str,
) -> None:
    sql_text = """
    UPDATE platform_integrations
    SET
        last_sync_at = NOW(),
        updated_at = NOW(),
        last_error = NULL
    WHERE id = %(integration_id)s::uuid
    ;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text, {"integration_id": integration_id})
        conn.commit()


def set_platform_error(
    *,
    integration_id: str,
    error_message: str,
) -> None:
    sql_text = """
    UPDATE platform_integrations
    SET
        last_error = %(error_message)s,
        updated_at = NOW()
    WHERE id = %(integration_id)s::uuid
    ;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql_text,
                {
                    "integration_id": integration_id,
                    "error_message": error_message,
                },
            )
        conn.commit()


def create_sync_run(
    *,
    integration_id: Optional[str],
    business_id: str,
    platform: str,
    sync_type: str,
    status: str,
    details_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sql_text = """
    INSERT INTO integration_sync_runs (
        id,
        integration_id,
        business_id,
        platform,
        sync_type,
        status,
        started_at,
        details_json,
        created_at,
        updated_at
    )
    VALUES (
        %(id)s::uuid,
        %(integration_id)s::uuid,
        %(business_id)s::uuid,
        %(platform)s,
        %(sync_type)s,
        %(status)s,
        NOW(),
        %(details_json)s,
        NOW(),
        NOW()
    )
    RETURNING
        id::text,
        integration_id::text,
        business_id::text,
        platform,
        sync_type,
        status,
        started_at,
        finished_at,
        records_found,
        records_imported,
        records_updated,
        error_message,
        details_json,
        created_at,
        updated_at
    ;
    """

    params = {
        "id": str(uuid.uuid4()),
        "integration_id": integration_id,
        "business_id": business_id,
        "platform": platform,
        "sync_type": sync_type,
        "status": status,
        "details_json": Json(details_json) if details_json is not None else None,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def finish_sync_run(
    *,
    sync_run_id: str,
    status: str,
    records_found: int = 0,
    records_imported: int = 0,
    records_updated: int = 0,
    error_message: Optional[str] = None,
    details_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    sql_text = """
    UPDATE integration_sync_runs
    SET
        status = %(status)s,
        finished_at = NOW(),
        records_found = %(records_found)s,
        records_imported = %(records_imported)s,
        records_updated = %(records_updated)s,
        error_message = %(error_message)s,
        details_json = %(details_json)s,
        updated_at = NOW()
    WHERE id = %(sync_run_id)s::uuid
    RETURNING
        id::text,
        integration_id::text,
        business_id::text,
        platform,
        sync_type,
        status,
        started_at,
        finished_at,
        records_found,
        records_imported,
        records_updated,
        error_message,
        details_json,
        created_at,
        updated_at
    ;
    """

    params = {
        "sync_run_id": sync_run_id,
        "status": status,
        "records_found": records_found,
        "records_imported": records_imported,
        "records_updated": records_updated,
        "error_message": error_message,
        "details_json": Json(details_json) if details_json is not None else None,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def upsert_platform_listing_source(
    *,
    business_id: str,
    integration_id: str,
    platform: str,
    environment: str,
    source_listing_id: str,
    source_sku: Optional[str],
    title: Optional[str],
    listing_status: Optional[str],
    quantity: Optional[int],
    price: Optional[float],
    currency: Optional[str],
    raw_payload: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    sql_text = """
    INSERT INTO platform_listing_sources (
        id,
        business_id,
        integration_id,
        platform,
        environment,
        source_listing_id,
        source_sku,
        title,
        listing_status,
        quantity,
        price,
        currency,
        raw_payload,
        first_seen_at,
        last_seen_at,
        created_at,
        updated_at
    )
    VALUES (
        %(id)s::uuid,
        %(business_id)s::uuid,
        %(integration_id)s::uuid,
        %(platform)s,
        %(environment)s,
        %(source_listing_id)s,
        %(source_sku)s,
        %(title)s,
        %(listing_status)s,
        %(quantity)s,
        %(price)s,
        %(currency)s,
        %(raw_payload)s,
        NOW(),
        NOW(),
        NOW(),
        NOW()
    )
    ON CONFLICT (business_id, platform, source_listing_id)
    DO UPDATE SET
        integration_id = EXCLUDED.integration_id,
        environment = EXCLUDED.environment,
        source_sku = EXCLUDED.source_sku,
        title = EXCLUDED.title,
        listing_status = EXCLUDED.listing_status,
        quantity = EXCLUDED.quantity,
        price = EXCLUDED.price,
        currency = EXCLUDED.currency,
        raw_payload = EXCLUDED.raw_payload,
        last_seen_at = NOW(),
        updated_at = NOW()
    RETURNING
        id::text,
        business_id::text,
        integration_id::text,
        platform,
        environment,
        source_listing_id,
        source_sku,
        title,
        listing_status,
        quantity,
        price,
        currency,
        raw_payload,
        first_seen_at,
        last_seen_at,
        linked_item_id::text,
        created_at,
        updated_at
    ;
    """

    params = {
        "id": str(uuid.uuid4()),
        "business_id": business_id,
        "integration_id": integration_id,
        "platform": platform,
        "environment": environment,
        "source_listing_id": source_listing_id,
        "source_sku": source_sku,
        "title": title,
        "listing_status": listing_status,
        "quantity": quantity,
        "price": price,
        "currency": currency,
        "raw_payload": Json(raw_payload) if raw_payload is not None else None,
    }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def find_unique_item_by_sku(
    *,
    business_id: str,
    sku: str,
) -> Optional[Dict[str, Any]]:
    sku = (sku or "").strip()
    if not sku:
        return None

    columns = _get_table_columns("items")
    if not columns:
        raise RuntimeError("Could not inspect items table columns")

    if "business_id" not in columns or "sku" not in columns or "item_id" not in columns:
        raise RuntimeError("items table must contain item_id, business_id, and sku columns")

    select_fields = [
        sql.SQL("item_id::text AS id"),
        sql.SQL("business_id::text AS business_id"),
        sql.SQL("sku"),
    ]

    if "title" in columns:
        select_fields.append(sql.SQL("title"))
    if "status" in columns:
        select_fields.append(sql.SQL("status"))

    query = sql.SQL(
        "SELECT {fields} FROM items WHERE business_id = %s::uuid AND sku = %s"
    ).format(
        fields=sql.SQL(", ").join(select_fields)
    )

    params: list[Any] = [business_id, sku]

    if "deleted_at" in columns:
        query += sql.SQL(" AND deleted_at IS NULL")
    if "is_deleted" in columns:
        query += sql.SQL(" AND COALESCE(is_deleted, FALSE) = FALSE")

    query += sql.SQL(" ORDER BY item_id LIMIT 2")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    if len(rows) != 1:
        return None

    return dict(rows[0])


def find_item_by_id(
    *,
    business_id: str,
    item_id: str,
) -> Optional[Dict[str, Any]]:
    columns = _get_table_columns("items")
    if not columns:
        raise RuntimeError("Could not inspect items table columns")

    if "business_id" not in columns or "item_id" not in columns:
        raise RuntimeError("items table must contain item_id and business_id columns")

    select_fields = [
        sql.SQL("item_id::text AS id"),
        sql.SQL("business_id::text AS business_id"),
    ]

    for optional_column in (
        "sku",
        "title",
        "status",
        "notes",
        "suggested_price",
        "min_price",
        "market_price",
        "sale_price",
        "category",
        "safe_to_sell",
    ):
        if optional_column in columns:
            select_fields.append(sql.SQL(optional_column))

    query = sql.SQL(
        "SELECT {fields} FROM items WHERE business_id = %s::uuid AND item_id = %s::uuid"
    ).format(
        fields=sql.SQL(", ").join(select_fields)
    )

    params: list[Any] = [business_id, item_id]

    if "deleted_at" in columns:
        query += sql.SQL(" AND deleted_at IS NULL")
    if "is_deleted" in columns:
        query += sql.SQL(" AND COALESCE(is_deleted, FALSE) = FALSE")

    query += sql.SQL(" LIMIT 1")

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    return dict(row) if row else None

def get_active_listing_link_by_source_id(
    *,
    platform_listing_source_id: str,
) -> Optional[Dict[str, Any]]:
    sql_text = """
    SELECT
        id::text,
        business_id::text,
        platform_listing_source_id::text,
        item_id::text,
        match_method,
        match_confidence,
        is_active,
        created_at,
        updated_at
    FROM platform_listing_links
    WHERE platform_listing_source_id = %(platform_listing_source_id)s::uuid
      AND is_active = TRUE
    LIMIT 1
    ;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql_text,
                {"platform_listing_source_id": platform_listing_source_id},
            )
            row = cur.fetchone()

    return dict(row) if row else None


def upsert_active_listing_link(
    *,
    business_id: str,
    platform_listing_source_id: str,
    item_id: str,
    match_method: str,
    match_confidence: float = 1.0,
) -> Dict[str, Any]:
    existing = get_active_listing_link_by_source_id(
        platform_listing_source_id=platform_listing_source_id,
    )

    if existing:
        sql_text = """
        UPDATE platform_listing_links
        SET
            item_id = %(item_id)s::uuid,
            match_method = %(match_method)s,
            match_confidence = %(match_confidence)s,
            is_active = TRUE,
            updated_at = NOW()
        WHERE id = %(id)s::uuid
        RETURNING
            id::text,
            business_id::text,
            platform_listing_source_id::text,
            item_id::text,
            match_method,
            match_confidence,
            is_active,
            created_at,
            updated_at
        ;
        """
        params = {
            "id": existing["id"],
            "item_id": item_id,
            "match_method": match_method,
            "match_confidence": match_confidence,
        }
    else:
        sql_text = """
        INSERT INTO platform_listing_links (
            id,
            business_id,
            platform_listing_source_id,
            item_id,
            match_method,
            match_confidence,
            is_active,
            created_at,
            updated_at
        )
        VALUES (
            %(id)s::uuid,
            %(business_id)s::uuid,
            %(platform_listing_source_id)s::uuid,
            %(item_id)s::uuid,
            %(match_method)s,
            %(match_confidence)s,
            TRUE,
            NOW(),
            NOW()
        )
        RETURNING
            id::text,
            business_id::text,
            platform_listing_source_id::text,
            item_id::text,
            match_method,
            match_confidence,
            is_active,
            created_at,
            updated_at
        ;
        """
        params = {
            "id": str(uuid.uuid4()),
            "business_id": business_id,
            "platform_listing_source_id": platform_listing_source_id,
            "item_id": item_id,
            "match_method": match_method,
            "match_confidence": match_confidence,
        }

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql_text, params)
            row = cur.fetchone()
        conn.commit()

    return dict(row)


def deactivate_active_listing_link(
    *,
    business_id: str,
    platform_listing_source_id: str,
) -> bool:
    sql_text = """
    UPDATE platform_listing_links
    SET
        is_active = FALSE,
        updated_at = NOW()
    WHERE business_id = %(business_id)s::uuid
      AND platform_listing_source_id = %(platform_listing_source_id)s::uuid
      AND is_active = TRUE
    ;
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql_text,
                {
                    "business_id": business_id,
                    "platform_listing_source_id": platform_listing_source_id,
                },
            )
            rowcount = cur.rowcount
        conn.commit()

    return rowcount > 0


def get_listing_source_by_id(
    *,
    business_id: str,
    source_row_id: str,
    platform: str = "ebay",
) -> Optional[Dict[str, Any]]:
    sql_text = """
    SELECT
        id::text,
        business_id::text,
        integration_id::text,
        platform,
        environment,
        source_listing_id,
        source_sku,
        title,
        listing_status,
        quantity,
        price,
        currency,
        raw_payload,
        first_seen_at,
        last_seen_at,
        linked_item_id::text,
        created_at,
        updated_at
    FROM platform_listing_sources
    WHERE business_id = %(business_id)s::uuid
      AND id = %(source_row_id)s::uuid
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
                    "source_row_id": source_row_id,
                    "platform": platform,
                },
            )
            row = cur.fetchone()

    return dict(row) if row else None


def list_unmatched_listing_sources(
    *,
    business_id: str,
    platform: str = "ebay",
) -> list[Dict[str, Any]]:
    sql_text = """
    SELECT
        pls.id::text AS source_row_id,
        pls.source_listing_id,
        pls.source_sku,
        pls.title,
        pls.listing_status,
        pls.quantity,
        pls.price,
        pls.currency,
        pls.updated_at
    FROM platform_listing_sources pls
    LEFT JOIN platform_listing_links pll
      ON pll.platform_listing_source_id = pls.id
     AND pll.is_active = TRUE
    WHERE pls.business_id = %(business_id)s::uuid
      AND pls.platform = %(platform)s
      AND pll.id IS NULL
    ORDER BY pls.updated_at DESC
    ;
    """

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                sql_text,
                {
                    "business_id": business_id,
                    "platform": platform,
                },
            )
            rows = cur.fetchall()

    return [dict(row) for row in rows]