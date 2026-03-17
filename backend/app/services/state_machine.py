"""
backend/app/services/state_machine.py

Item Status State Machine (domain-only)

Constraints:
- Pure module: no DB access, no route imports, no repo usage
- Encapsulates allowed transitions in a constant mapping

This module is intentionally small and stable because it becomes a shared
contract between API/service code and persisted DB values.
"""

from __future__ import annotations

from typing import Dict, FrozenSet


# Canonical persisted values (match current DB/service usage)
STATUS_DRAFT = "Draft"
STATUS_ACTIVE = "Active"
STATUS_SOLD = "Sold"
STATUS_ARCHIVED = "Archived"
STATUS_DELETED = "Deleted"


ALL_STATUSES: FrozenSet[str] = frozenset(
    {STATUS_DRAFT, STATUS_ACTIVE, STATUS_SOLD, STATUS_ARCHIVED, STATUS_DELETED}
)

# ---------------------------------------------------------------------------
# Allowed transitions (disallow-by-default)
#
# Baseline requirements:
#   Draft -> Active
#   Active -> Sold
#   Active -> Archived
#   Sold -> Archived
#   Archived -> Active
#
# Soft delete:
#   Draft/Active/Archived -> Deleted
#   Sold -> Deleted is DISALLOWED (accounting integrity)
#
# Restore (safe default):
#   Deleted -> Archived (ONLY)
# ---------------------------------------------------------------------------

ALLOWED_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    STATUS_DRAFT: frozenset({STATUS_ACTIVE, STATUS_DELETED}),
    STATUS_ACTIVE: frozenset({STATUS_SOLD, STATUS_ARCHIVED, STATUS_DELETED}),
    STATUS_SOLD: frozenset({STATUS_ARCHIVED}),
    STATUS_ARCHIVED: frozenset({STATUS_ACTIVE, STATUS_DELETED}),
    STATUS_DELETED: frozenset({STATUS_ARCHIVED}),  # restore path
}

# ---------------------------------------------------------------------------
# "Privileged" transitions
#
# These transitions are valid in the domain model, but must only occur via
# dedicated service operations (soft delete / restore) to preserve audit
# consistency and immutability rules.
# ---------------------------------------------------------------------------

PRIVILEGED_TARGET_STATUSES: FrozenSet[str] = frozenset({STATUS_DELETED})
PRIVILEGED_SOURCE_STATUSES: FrozenSet[str] = frozenset({STATUS_DELETED})

# When using the generic "user status change" path (e.g. update item status),
# we forbid entering or leaving Deleted. Use delete/restore operations instead.
FORBIDDEN_IN_GENERIC_STATUS_CHANGE: FrozenSet[str] = frozenset({STATUS_DELETED})


_NORMALIZATION_MAP: Dict[str, str] = {
    "draft": STATUS_DRAFT,
    "active": STATUS_ACTIVE,
    "sold": STATUS_SOLD,
    "archived": STATUS_ARCHIVED,
    "deleted": STATUS_DELETED,
}


def normalize_status(status: str | None) -> str | None:
    """Normalize status input to canonical persisted values."""
    if status is None:
        return None

    s = str(status).strip()
    if not s:
        return None

    mapped = _NORMALIZATION_MAP.get(s.casefold())
    return mapped if mapped is not None else s


def validate_status_transition(current_status: str | None, new_status: str | None) -> None:
    """Validate an item status transition (pure domain rule check).

    API contract:
    - If new_status is None: no-op (no transition requested)
    - current_status is required for validation (None is invalid)

    Raises:
        ValueError: when status is invalid or transition is not allowed.
    """
    new_norm = normalize_status(new_status)
    if new_norm is None:
        return

    current_norm = normalize_status(current_status)
    if current_norm is None:
        raise ValueError(
            "Invalid status transition: current status is missing/None; "
            f"cannot transition to {new_norm!r}."
        )

    if current_norm not in ALL_STATUSES:
        raise ValueError(
            f"Invalid status transition: unknown current status {current_norm!r} -> {new_norm!r}."
        )

    if new_norm not in ALL_STATUSES:
        raise ValueError(
            f"Invalid status transition: {current_norm!r} -> unknown new status {new_norm!r}."
        )

    allowed = ALLOWED_TRANSITIONS.get(current_norm, frozenset())
    if new_norm not in allowed:
        raise ValueError(f"Invalid status transition: {current_norm!r} -> {new_norm!r}.")


# ---------------------------------------------------------------------------
# Intent-specific validators (recommended for service-layer hardening)
# ---------------------------------------------------------------------------


def validate_user_status_change(current_status: str | None, new_status: str | None) -> None:
    """Validate a generic user-driven status change.

    This is for normal "update status" flows and intentionally forbids entering
    or leaving Deleted, because those transitions must happen via dedicated
    operations (soft delete / restore) to preserve audit consistency.

    Raises:
        ValueError: if invalid or forbidden in the generic path.
    """
    new_norm = normalize_status(new_status)
    if new_norm is None:
        return

    current_norm = normalize_status(current_status)
    if current_norm is None:
        raise ValueError("Invalid status change: current status is missing/None.")

    if current_norm in FORBIDDEN_IN_GENERIC_STATUS_CHANGE or new_norm in FORBIDDEN_IN_GENERIC_STATUS_CHANGE:
        raise ValueError(
            f"Invalid status change: {current_norm!r} -> {new_norm!r}. "
            "Use the soft-delete/restore operations for Deleted lifecycle."
        )

    # Domain transition check for non-Deleted states
    validate_status_transition(current_norm, new_norm)


def validate_soft_delete(current_status: str | None) -> None:
    """Validate whether the current status can be soft-deleted.

    Rules:
    - Sold cannot be deleted (accounting integrity).
    - Deleted cannot be deleted again.
    - Draft/Active/Archived can be deleted.

    Raises:
        ValueError: if soft delete is not permitted.
    """
    current_norm = normalize_status(current_status)
    if current_norm is None:
        raise ValueError("Invalid soft delete: current status is missing/None.")

    if current_norm not in ALL_STATUSES:
        raise ValueError(f"Invalid soft delete: unknown current status {current_norm!r}.")

    if current_norm == STATUS_SOLD:
        raise ValueError("Invalid soft delete: Sold items cannot be deleted.")

    if current_norm == STATUS_DELETED:
        raise ValueError("Invalid soft delete: item is already Deleted.")

    # Domain mapping already encodes allowed sources -> Deleted,
    # but we keep this explicit for clarity.
    validate_status_transition(current_norm, STATUS_DELETED)


def validate_restore(current_status: str | None) -> None:
    """Validate whether the current status can be restored from Deleted.

    Rules:
    - Only Deleted can be restored.
    - Restore target is Archived (enforced by domain transition map).

    Raises:
        ValueError: if restore is not permitted.
    """
    current_norm = normalize_status(current_status)
    if current_norm is None:
        raise ValueError("Invalid restore: current status is missing/None.")

    if current_norm not in ALL_STATUSES:
        raise ValueError(f"Invalid restore: unknown current status {current_norm!r}.")

    if current_norm != STATUS_DELETED:
        raise ValueError(f"Invalid restore: only Deleted items can be restored (got {current_norm!r}).")

    validate_status_transition(current_norm, STATUS_ARCHIVED)