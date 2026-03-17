# backend/app/ledger/repo.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import text


@dataclass(frozen=True)
class InsertLedgerResult:
    entry_id: str
    inserted: bool


def _rows_as_dicts(result: Any) -> List[Dict[str, Any]]:
    try:
        return [dict(r) for r in result.mappings().all()]
    except Exception:
        keys = list(result.keys())
        rows = result.fetchall()
        return [dict(zip(keys, row)) for row in rows]


def _first_row_as_dict(result: Any) -> Dict[str, Any]:
    try:
        row = result.mappings().first()
        return dict(row) if row else {}
    except Exception:
        keys = list(result.keys())
        row = result.fetchone()
        return dict(zip(keys, row)) if row else {}


def _execute(db: Any, sql_text: str, params: Dict[str, Any]) -> Any:
    return db.execute(text(sql_text), params)


def _norm_text(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s != "" else None


# ---------------------------------------------------------------------------
# Inserts (append-only)
# ---------------------------------------------------------------------------

def insert_ledger_entry_scoped(
    db: Any,
    *,
    business_id: str,
    item_id: Optional[str],
    entry_type: str,
    amount: str,
    currency: str,
    occurred_at_iso: str,
    actor_user_id: Optional[str] = None,
    source: str = "SYSTEM",
    source_ref: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> InsertLedgerResult:
    """
    Append-only insert into ledger_entries.

    Your DB idempotency index (confirmed by screenshots):
      UNIQUE (business_id, source_ref, entry_type) WHERE source_ref IS NOT NULL

    Behavior:
      - If source_ref is present:
          INSERT ... ON CONFLICT (business_id, source_ref, entry_type) WHERE source_ref IS NOT NULL DO NOTHING RETURNING entry_id
          If insert succeeds => inserted=True
          If conflict/no-op => fetch existing row and return inserted=False
      - If source_ref is NULL/blank:
          Normal insert (no idempotency) => inserted=True
    """
    entry_id = str(uuid.uuid4())
    source_ref_norm = _norm_text(source_ref)
    details_json = json.dumps(details, default=str) if details is not None else None

    params = {
        "entry_id": entry_id,
        "business_id": business_id,
        "item_id": item_id,
        "entry_type": str(entry_type),
        "amount": str(amount),
        "currency": str(currency),
        "occurred_at": occurred_at_iso,
        "actor_user_id": actor_user_id,
        "source": str(source),
        "source_ref": source_ref_norm,
        "details": details_json,
    }

    # No source_ref => no idempotency
    if source_ref_norm is None:
        res = _execute(
            db,
            """
            INSERT INTO ledger_entries (
                entry_id,
                business_id,
                item_id,
                entry_type,
                amount,
                currency,
                occurred_at,
                created_at,
                actor_user_id,
                source,
                source_ref,
                details
            ) VALUES (
                CAST(:entry_id AS uuid),
                CAST(:business_id AS uuid),
                CAST(:item_id AS uuid),
                :entry_type,
                CAST(:amount AS numeric),
                :currency,
                CAST(:occurred_at AS timestamptz),
                NOW(),
                CAST(:actor_user_id AS uuid),
                :source,
                :source_ref,
                CAST(:details AS jsonb)
            )
            RETURNING entry_id::text AS entry_id;
            """,
            params,
        )
        row = _first_row_as_dict(res)
        returned_id = (row.get("entry_id") or "").strip()
        if not returned_id:
            raise RuntimeError("Ledger insert did not return entry_id.")
        return InsertLedgerResult(entry_id=returned_id, inserted=True)

    # source_ref present => idempotent insert
    res = _execute(
        db,
        """
        INSERT INTO ledger_entries (
            entry_id,
            business_id,
            item_id,
            entry_type,
            amount,
            currency,
            occurred_at,
            created_at,
            actor_user_id,
            source,
            source_ref,
            details
        ) VALUES (
            CAST(:entry_id AS uuid),
            CAST(:business_id AS uuid),
            CAST(:item_id AS uuid),
            :entry_type,
            CAST(:amount AS numeric),
            :currency,
            CAST(:occurred_at AS timestamptz),
            NOW(),
            CAST(:actor_user_id AS uuid),
            :source,
            :source_ref,
            CAST(:details AS jsonb)
        )
        ON CONFLICT (business_id, source_ref, entry_type)
            WHERE source_ref IS NOT NULL
        DO NOTHING
        RETURNING entry_id::text AS entry_id;
        """,
        params,
    )

    row = _first_row_as_dict(res)
    returned_id = (row.get("entry_id") or "").strip()
    if returned_id:
        return InsertLedgerResult(entry_id=returned_id, inserted=True)

    # Conflict/no-op => fetch existing
    res2 = _execute(
        db,
        """
        SELECT entry_id::text AS entry_id
        FROM ledger_entries
        WHERE business_id = CAST(:business_id AS uuid)
          AND source_ref = :source_ref
          AND entry_type = :entry_type
        ORDER BY created_at DESC
        LIMIT 1;
        """,
        {"business_id": business_id, "source_ref": source_ref_norm, "entry_type": str(entry_type)},
    )
    row2 = _first_row_as_dict(res2)
    existing_id = (row2.get("entry_id") or "").strip()
    if not existing_id:
        raise RuntimeError("Ledger conflict occurred but existing entry_id was not found.")
    return InsertLedgerResult(entry_id=existing_id, inserted=False)


# ---------------------------------------------------------------------------
# Fetching / reporting
# ---------------------------------------------------------------------------

def fetch_item_ledger_entries(
    db: Any,
    *,
    business_id: str,
    item_id: str,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    res = _execute(
        db,
        """
        SELECT
            entry_id,
            business_id,
            item_id,
            entry_type,
            amount,
            currency,
            occurred_at,
            created_at,
            actor_user_id,
            source,
            source_ref,
            details
        FROM ledger_entries
        WHERE business_id = CAST(:business_id AS uuid)
          AND item_id = CAST(:item_id AS uuid)
        ORDER BY occurred_at DESC, created_at DESC, entry_id DESC
        LIMIT :limit OFFSET :offset;
        """,
        {"business_id": business_id, "item_id": item_id, "limit": int(limit), "offset": int(offset)},
    )
    return _rows_as_dicts(res)


def fetch_item_ledger_totals(
    db: Any,
    *,
    business_id: str,
    item_id: str,
) -> Dict[str, Any]:
    res = _execute(
        db,
        """
        SELECT
            COALESCE(SUM(amount), 0)::numeric AS net_amount,
            COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0)::numeric AS total_credits,
            COALESCE(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 0)::numeric AS total_debits,
            COUNT(*)::int AS entry_count
        FROM ledger_entries
        WHERE business_id = CAST(:business_id AS uuid)
          AND item_id = CAST(:item_id AS uuid);
        """,
        {"business_id": business_id, "item_id": item_id},
    )
    return _first_row_as_dict(res)


def fetch_business_entry_type_totals(
    db: Any,
    *,
    business_id: str,
    start_iso: str,
    end_iso: str,
    entry_types: List[str],
) -> List[Dict[str, Any]]:
    res = _execute(
        db,
        """
        SELECT
          entry_type,
          COALESCE(SUM(amount), 0)::numeric AS total_amount,
          COUNT(*)::int AS entry_count
        FROM ledger_entries
        WHERE business_id = CAST(:business_id AS uuid)
          AND occurred_at >= CAST(:start AS timestamptz)
          AND occurred_at < CAST(:end AS timestamptz)
          AND entry_type = ANY(:entry_types)
        GROUP BY entry_type
        ORDER BY entry_type;
        """,
        {
            "business_id": business_id,
            "start": start_iso,
            "end": end_iso,
            "entry_types": entry_types,
        },
    )
    return _rows_as_dicts(res)


def fetch_business_sold_count(
    db: Any,
    *,
    business_id: str,
    start_iso: str,
    end_iso: str,
) -> int:
    res = _execute(
        db,
        """
        SELECT COUNT(*)::int AS sold_count
        FROM ledger_entries
        WHERE business_id = CAST(:business_id AS uuid)
          AND occurred_at >= CAST(:start AS timestamptz)
          AND occurred_at < CAST(:end AS timestamptz)
          AND entry_type = 'SALE';
        """,
        {"business_id": business_id, "start": start_iso, "end": end_iso},
    )
    row = _first_row_as_dict(res)
    return int(row.get("sold_count") or 0)