from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from decimal import Decimal
from typing import Any, Optional
from app.marketplace_listings.repo import get_marketplace_listing_for_item

from app.marketplace_listings.repo import (
    create_or_get_marketplace_listing,
    get_marketplace_listing_for_item,
    mark_marketplace_listing_error,
    update_marketplace_listing_publish_state,
)

import requests

from app.integrations.ebay.mapper import map_ebay_inventory_response
from app.integrations.ebay.repo import (
    create_sync_run,
    deactivate_active_listing_link,
    find_item_by_id,
    find_unique_item_by_sku,
    finish_sync_run,
    get_listing_source_by_id,
    get_platform_integration,
    list_unmatched_listing_sources,
    set_platform_error,
    touch_platform_last_sync,
    update_platform_integration_tokens,
    upsert_active_listing_link,
    upsert_platform_integration,
    upsert_platform_listing_source,
)


AUTH_BASES = {
    "production": "https://auth.ebay.com/oauth2/authorize",
    "sandbox": "https://auth.sandbox.ebay.com/oauth2/authorize",
}

TOKEN_BASES = {
    "production": "https://api.ebay.com/identity/v1/oauth2/token",
    "sandbox": "https://api.sandbox.ebay.com/identity/v1/oauth2/token",
}

API_BASES = {
    "production": "https://api.ebay.com",
    "sandbox": "https://api.sandbox.ebay.com",
}


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _get_client_id() -> str:
    return _require_env("EBAY_CLIENT_ID")


def _get_client_secret() -> str:
    return _require_env("EBAY_CLIENT_SECRET")


def _get_ru_name() -> str:
    return _require_env("EBAY_REDIRECT_URI")


def _get_scopes() -> str:
    return _require_env("EBAY_OAUTH_SCOPES")


def _get_environment() -> str:
    env = os.getenv("EBAY_ENVIRONMENT", "production").strip().lower()
    if env not in {"production", "sandbox"}:
        raise RuntimeError("EBAY_ENVIRONMENT must be 'production' or 'sandbox'")
    return env


def build_oauth_state(*, business_id: str) -> str:
    nonce = secrets.token_urlsafe(18)
    return f"{business_id}:{nonce}"


def extract_business_id_from_state(state: str | None) -> str:
    if not state:
        raise RuntimeError("Missing OAuth state")

    parts = state.split(":", 1)
    if len(parts) != 2 or not parts[0].strip():
        raise RuntimeError("Invalid OAuth state")

    return parts[0].strip()


def build_connect_url(*, business_id: str) -> str:
    env = _get_environment()
    client_id = _get_client_id()
    ru_name = _get_ru_name()
    scopes = _get_scopes()
    state = build_oauth_state(business_id=business_id)

    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": ru_name,
            "response_type": "code",
            "scope": scopes,
            "state": state,
        }
    )

    return f"{AUTH_BASES[env]}?{query}"


def exchange_code_for_tokens(*, code: str) -> dict:
    env = _get_environment()
    client_id = _get_client_id()
    client_secret = _get_client_secret()
    ru_name = _get_ru_name()

    raw = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(raw).decode("utf-8")

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": ru_name,
    }

    response = requests.post(
        TOKEN_BASES[env],
        headers=headers,
        data=data,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"eBay token exchange error: {response.text}")

    return response.json()


def refresh_access_token(*, refresh_token: str) -> dict:
    env = _get_environment()
    client_id = _get_client_id()
    client_secret = _get_client_secret()

    raw = f"{client_id}:{client_secret}".encode("utf-8")
    basic_auth = base64.b64encode(raw).decode("utf-8")

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    response = requests.post(
        TOKEN_BASES[env],
        headers=headers,
        data=data,
        timeout=30,
    )

    if response.status_code != 200:
        raise Exception(f"eBay refresh token error: {response.text}")

    return response.json()


def _is_token_expired_or_near_expiry(token_expires_at: datetime | None) -> bool:
    if token_expires_at is None:
        return True

    now = datetime.now(timezone.utc)
    refresh_margin = timedelta(minutes=5)

    if token_expires_at.tzinfo is None:
        token_expires_at = token_expires_at.replace(tzinfo=timezone.utc)

    return token_expires_at <= now + refresh_margin


def ensure_valid_access_token(*, integration: dict) -> tuple[str, dict]:
    access_token = (integration.get("access_token") or "").strip()
    token_expires_at = integration.get("token_expires_at")

    if access_token and not _is_token_expired_or_near_expiry(token_expires_at):
        return access_token, integration

    stored_refresh_token = (integration.get("refresh_token") or "").strip()
    if not stored_refresh_token:
        raise RuntimeError("No refresh token available for eBay integration")

    refreshed = refresh_access_token(refresh_token=stored_refresh_token)

    now = datetime.now(timezone.utc)
    expires_in = refreshed.get("expires_in")
    refresh_token_expires_in = refreshed.get("refresh_token_expires_in")

    new_token_expires_at = (
        now + timedelta(seconds=int(expires_in))
        if expires_in is not None
        else None
    )
    new_refresh_token_expires_at = (
        now + timedelta(seconds=int(refresh_token_expires_in))
        if refresh_token_expires_in is not None
        else integration.get("refresh_token_expires_at")
    )

    updated_integration = update_platform_integration_tokens(
        integration_id=integration["id"],
        access_token=refreshed.get("access_token", ""),
        refresh_token=refreshed.get("refresh_token"),
        token_expires_at=new_token_expires_at,
        refresh_token_expires_at=new_refresh_token_expires_at,
        scopes=refreshed.get("scope") or integration.get("scopes"),
        status="active",
        last_error=None,
    )

    new_access_token = (updated_integration.get("access_token") or "").strip()
    if not new_access_token:
        raise RuntimeError("Refreshed eBay access token is empty")

    return new_access_token, updated_integration


def persist_oauth_tokens_from_callback(
    *,
    state: str | None,
    token_payload: dict,
) -> dict:
    business_id = extract_business_id_from_state(state)
    env = _get_environment()

    now = datetime.now(timezone.utc)
    expires_in = token_payload.get("expires_in")
    refresh_token_expires_in = token_payload.get("refresh_token_expires_in")

    token_expires_at = (
        now + timedelta(seconds=int(expires_in))
        if expires_in is not None
        else None
    )
    refresh_token_expires_at = (
        now + timedelta(seconds=int(refresh_token_expires_in))
        if refresh_token_expires_in is not None
        else None
    )

    integration = upsert_platform_integration(
        business_id=business_id,
        platform="ebay",
        environment=env,
        access_token=token_payload.get("access_token", ""),
        refresh_token=token_payload.get("refresh_token"),
        token_expires_at=token_expires_at,
        refresh_token_expires_at=refresh_token_expires_at,
        scopes=token_payload.get("scope"),
        status="active",
        last_error=None,
    )

    return {
        "business_id": business_id,
        "integration": integration,
        "environment": env,
    }


def get_ebay_integration_status(*, business_id: str) -> dict:
    env = _get_environment()
    integration = get_platform_integration(
        business_id=business_id,
        platform="ebay",
        environment=env,
    )

    if not integration:
        return {
            "connected": False,
            "platform": "ebay",
            "environment": env,
            "status": "disconnected",
            "business_id": business_id,
            "token_expires_at": None,
            "refresh_token_expires_at": None,
            "last_sync_at": None,
            "last_error": None,
            "scopes": None,
        }

    return {
        "connected": True,
        "platform": "ebay",
        "environment": env,
        "status": integration.get("status") or "active",
        "business_id": business_id,
        "token_expires_at": integration.get("token_expires_at"),
        "refresh_token_expires_at": integration.get("refresh_token_expires_at"),
        "last_sync_at": integration.get("last_sync_at"),
        "last_error": integration.get("last_error"),
        "scopes": integration.get("scopes"),
    }


def fetch_raw_inventory_response(access_token: str) -> dict:
    env = _get_environment()
    api_base = API_BASES[env]
    url = f"{api_base}/sell/inventory/v1/inventory_item"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    response = requests.get(url, headers=headers, timeout=30)

    if response.status_code != 200:
        raise Exception(f"eBay API error: {response.text}")

    return response.json()


def import_active_listings_for_business(
    *,
    business_id: str,
    token_override: str | None = None,
) -> dict:
    env = _get_environment()
    integration = get_platform_integration(
        business_id=business_id,
        platform="ebay",
        environment=env,
    )

    integration_id = integration["id"] if integration else None

    sync_run = create_sync_run(
        integration_id=integration_id,
        business_id=business_id,
        platform="ebay",
        sync_type="import_listings",
        status="running",
        details_json={"environment": env},
    )

    try:
        access_token = (token_override or "").strip()

        if not access_token:
            if not integration:
                raise RuntimeError("No active eBay integration found for this business")

            access_token, integration = ensure_valid_access_token(
                integration=integration,
            )

        raw_data = fetch_raw_inventory_response(access_token)
        normalized_listings = map_ebay_inventory_response(raw_data)

        stored_count = 0
        auto_linked_count = 0

        if integration_id:
            for listing in normalized_listings:
                if not listing.source_listing_id:
                    continue

                source_row = upsert_platform_listing_source(
                    business_id=business_id,
                    integration_id=integration_id,
                    platform=listing.source_platform,
                    environment=env,
                    source_listing_id=listing.source_listing_id,
                    source_sku=listing.source_sku,
                    title=listing.title,
                    listing_status=listing.listing_status,
                    quantity=listing.quantity,
                    price=listing.price,
                    currency=listing.currency,
                    raw_payload=listing.raw_payload,
                )
                stored_count += 1

                source_sku = (listing.source_sku or "").strip()
                if not source_sku:
                    continue

                matched_item = find_unique_item_by_sku(
                    business_id=business_id,
                    sku=source_sku,
                )
                if not matched_item:
                    continue

                upsert_active_listing_link(
                    business_id=business_id,
                    platform_listing_source_id=source_row["id"],
                    item_id=matched_item["id"],
                    match_method="auto_sku",
                    match_confidence=1.0,
                )
                auto_linked_count += 1

        payload = {
            "imported": len(normalized_listings),
            "stored": stored_count,
            "auto_linked": auto_linked_count,
            "unmatched": max(stored_count - auto_linked_count, 0),
            "listings": [listing.model_dump() for listing in normalized_listings],
        }

        finish_sync_run(
            sync_run_id=sync_run["id"],
            status="success",
            records_found=len(normalized_listings),
            records_imported=stored_count,
            records_updated=auto_linked_count,
            error_message=None,
            details_json={
                "environment": env,
                "normalized_count": len(normalized_listings),
                "stored_count": stored_count,
                "auto_linked_count": auto_linked_count,
                "unmatched_count": max(stored_count - auto_linked_count, 0),
            },
        )

        if integration_id:
            touch_platform_last_sync(integration_id=integration_id)

        return payload

    except Exception as exc:
        finish_sync_run(
            sync_run_id=sync_run["id"],
            status="failed",
            records_found=0,
            records_imported=0,
            records_updated=0,
            error_message=str(exc),
            details_json={"environment": env},
        )

        if integration_id:
            set_platform_error(integration_id=integration_id, error_message=str(exc))

        raise


def get_unmatched_ebay_listings(*, business_id: str) -> dict:
    rows = list_unmatched_listing_sources(
        business_id=business_id,
        platform="ebay",
    )
    return {
        "business_id": business_id,
        "platform": "ebay",
        "count": len(rows),
        "listings": rows,
    }


def manually_link_ebay_listing(
    *,
    business_id: str,
    source_row_id: str,
    item_id: str,
) -> dict:
    source_row = get_listing_source_by_id(
        business_id=business_id,
        source_row_id=source_row_id,
        platform="ebay",
    )
    if not source_row:
        raise RuntimeError("Marketplace source listing not found")

    item_row = find_item_by_id(
        business_id=business_id,
        item_id=item_id,
    )
    if not item_row:
        raise RuntimeError("FlipTwice item not found")

    link_row = upsert_active_listing_link(
        business_id=business_id,
        platform_listing_source_id=source_row_id,
        item_id=item_id,
        match_method="manual",
        match_confidence=1.0,
    )

    return {
        "message": "Listing linked successfully",
        "business_id": business_id,
        "source_row_id": source_row_id,
        "item_id": item_id,
        "match_method": link_row["match_method"],
        "is_active": bool(link_row["is_active"]),
    }


def manually_unlink_ebay_listing(
    *,
    business_id: str,
    source_row_id: str,
) -> dict:
    source_row = get_listing_source_by_id(
        business_id=business_id,
        source_row_id=source_row_id,
        platform="ebay",
    )
    if not source_row:
        raise RuntimeError("Marketplace source listing not found")

    unlinked = deactivate_active_listing_link(
        business_id=business_id,
        platform_listing_source_id=source_row_id,
    )

    return {
        "message": "Listing unlinked successfully" if unlinked else "No active link found",
        "business_id": business_id,
        "source_row_id": source_row_id,
        "unlinked": bool(unlinked),
    }

def _coerce_price_to_str(value: Any) -> str:
    if value is None:
        raise RuntimeError("Missing price value")

    if isinstance(value, Decimal):
        return f"{value:.2f}"

    try:
        return f"{Decimal(str(value)):.2f}"
    except Exception as exc:
        raise RuntimeError(f"Invalid price value: {value}") from exc


def _pick_ebay_price(item_row: dict) -> str:
    for key in ("suggested_price", "min_price", "market_price", "sale_price"):
        value = item_row.get(key)
        if value is not None:
            return _coerce_price_to_str(value)
    raise RuntimeError("Item does not have a usable price for eBay publish")


def _pick_ebay_sku(item_row: dict) -> str:
    sku = (item_row.get("sku") or "").strip()
    if sku:
        return sku

    item_id = (item_row.get("id") or "").strip()
    if not item_id:
        raise RuntimeError("Item is missing both sku and id")
    return f"FT-{item_id}"


def _pick_ebay_title(item_row: dict) -> str:
    title = (item_row.get("title") or "").strip()
    if not title:
        raise RuntimeError("Item title is required for eBay publish")
    return title


def _pick_ebay_description(item_row: dict) -> str:
    notes = (item_row.get("notes") or "").strip()
    title = (item_row.get("title") or "").strip()

    description = notes or title
    if not description:
        raise RuntimeError("Item description is required for eBay publish")

    return description


def _get_default_ebay_marketplace_id() -> str:
    return os.getenv("EBAY_DEFAULT_MARKETPLACE_ID", "EBAY_US").strip() or "EBAY_US"


def _get_default_ebay_category_id() -> str:
    category_id = os.getenv("EBAY_DEFAULT_CATEGORY_ID", "").strip()
    if not category_id:
        raise RuntimeError("EBAY_DEFAULT_CATEGORY_ID is not set")
    return category_id


def _get_default_merchant_location_key() -> str:
    return os.getenv("EBAY_DEFAULT_MERCHANT_LOCATION_KEY", "main").strip() or "main"


def _call_ebay_api(
    *,
    method: str,
    path: str,
    access_token: str,
    json_payload: Optional[dict] = None,
) -> dict:
    env = _get_environment()
    api_base = API_BASES[env]
    url = f"{api_base}{path}"

    headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json",
    "Content-Language": "en-US",
}

    response = requests.request(
        method=method,
        url=url,
        headers=headers,
        json=json_payload,
        timeout=30,
    )

    if response.status_code >= 400:
        response_text = response.text
        raise RuntimeError(f"eBay API error [{response.status_code}]: {response_text}")

    if not response.text.strip():
        return {"ok": True, "status_code": response.status_code}

    try:
        return response.json()
    except Exception:
        return {
            "ok": True,
            "status_code": response.status_code,
            "raw_text": response.text,
        }


def _build_ebay_inventory_payload(item_row: dict) -> dict:
    title = _pick_ebay_title(item_row)
    description = _pick_ebay_description(item_row)

    return {
        "product": {
            "title": title,
            "description": description,
        },
        "availability": {
            "shipToLocationAvailability": {
                "quantity": 1
            }
        },
        "condition": "NEW"
    }


def _build_ebay_offer_payload(
    *,
    item_row: dict,
    sku: str,
) -> dict:
    price_value = _pick_ebay_price(item_row)
    description = _pick_ebay_description(item_row)

    return {
        "sku": sku,
        "marketplaceId": _get_default_ebay_marketplace_id(),
        "format": "FIXED_PRICE",
        "availableQuantity": 1,
        "categoryId": _get_default_ebay_category_id(),
        "merchantLocationKey": _get_default_merchant_location_key(),
        "listingDescription": description,
        "pricingSummary": {
            "price": {
                "value": price_value,
                "currency": "USD",
            }
        },
        "listingPolicies": {
            "eBayPlusIfEligible": False
        },
        "tax": {
            "applyTax": False
        }
    }


def upsert_inventory_item_to_ebay(
    *,
    access_token: str,
    sku: str,
    item_row: dict,
) -> dict:
    payload = _build_ebay_inventory_payload(item_row)

    return _call_ebay_api(
        method="PUT",
        path=f"/sell/inventory/v1/inventory_item/{sku}",
        access_token=access_token,
        json_payload=payload,
    )


def create_offer_on_ebay(
    *,
    access_token: str,
    sku: str,
    item_row: dict,
) -> dict:
    payload = _build_ebay_offer_payload(
        item_row=item_row,
        sku=sku,
    )

    return _call_ebay_api(
        method="POST",
        path="/sell/inventory/v1/offer",
        access_token=access_token,
        json_payload=payload,
    )


def publish_offer_on_ebay(
    *,
    access_token: str,
    offer_id: str,
) -> dict:
    return _call_ebay_api(
        method="POST",
        path=f"/sell/inventory/v1/offer/{offer_id}/publish",
        access_token=access_token,
        json_payload=None,
    )


def publish_item_to_ebay(
    *,
    business_id: str,
    item_id: str,
) -> dict:
    env = _get_environment()

    integration = get_platform_integration(
        business_id=business_id,
        platform="ebay",
        environment=env,
    )
    if not integration:
        raise RuntimeError("No active eBay integration found for this business")

    item_row = find_item_by_id(
        business_id=business_id,
        item_id=item_id,
    )
    if not item_row:
        raise RuntimeError("FlipTwice item not found")

    status = (item_row.get("status") or "").strip().lower()
    if status == "sold":
        raise RuntimeError("Sold items cannot be published to eBay")
    if status == "deleted":
        raise RuntimeError("Deleted items cannot be published to eBay")

    _pick_ebay_title(item_row)
    _pick_ebay_description(item_row)
    price_value = _pick_ebay_price(item_row)
    sku = _pick_ebay_sku(item_row)

    listing_row = create_or_get_marketplace_listing(
        business_id=business_id,
        item_id=item_id,
        platform="ebay",
        external_inventory_key=sku,
        status="draft",
        publish_status="not_started",
        sync_status="pending",
    )

    offer_id = (listing_row.get("external_offer_id") or "").strip() or None
    listing_id_external = (listing_row.get("external_listing_id") or "").strip() or None
    inventory_created = bool(listing_row.get("external_inventory_key"))
    offer_created = bool(offer_id)

    try:
        access_token, _updated_integration = ensure_valid_access_token(
            integration=integration,
        )

        inventory_response = upsert_inventory_item_to_ebay(
            access_token=access_token,
            sku=sku,
            item_row=item_row,
        )
        inventory_created = True

        update_marketplace_listing_publish_state(
            listing_id=listing_row["id"],
            status="submitted",
            publish_status="in_progress",
            sync_status="pending",
            external_inventory_key=sku,
            raw_response={
                "step": "inventory_upsert",
                "response": inventory_response,
            },
            last_publish_attempt_at_now=True,
            clear_error=True,
        )

        existing_offer_id = (listing_row.get("external_offer_id") or "").strip()

        if existing_offer_id:
            offer_id = existing_offer_id
            offer_response = {
                "reused_existing_offer": True,
                "offerId": offer_id,
            }
            offer_created = True
        else:
            offer_response = create_offer_on_ebay(
                access_token=access_token,
                sku=sku,
                item_row=item_row,
            )

            offer_id = (
                offer_response.get("offerId")
                or offer_response.get("offer_id")
                or ""
            ).strip()

            if not offer_id:
                raise RuntimeError(f"eBay offer creation did not return offerId: {offer_response}")

            update_marketplace_listing_publish_state(
                listing_id=listing_row["id"],
                status="submitted",
                publish_status="in_progress",
                sync_status="pending",
                external_inventory_key=sku,
                external_offer_id=offer_id,
                raw_response={
                    "step": "offer_create",
                    "response": offer_response,
                },
                last_publish_attempt_at_now=True,
                clear_error=True,
            )
            offer_created = True

        publish_response = publish_offer_on_ebay(
            access_token=access_token,
            offer_id=offer_id,
        )

        listing_id_external = (
            publish_response.get("listingId")
            or publish_response.get("listing_id")
            or ""
        ).strip() or None

        publish_status = "published"
        listing_status = "live"

        if "UNPUBLISHED" in str(publish_response).upper():
            publish_status = "unpublished"
            listing_status = "submitted"

        final_row = update_marketplace_listing_publish_state(
            listing_id=listing_row["id"],
            status=listing_status,
            publish_status=publish_status,
            sync_status="synced",
            external_inventory_key=sku,
            external_offer_id=offer_id,
            external_listing_id=listing_id_external,
            raw_response={
                "step": "offer_publish",
                "response": publish_response,
            },
            published_at_now=(publish_status == "published"),
            last_synced_at_now=True,
            last_publish_attempt_at_now=True,
            clear_error=True,
        )

        return {
            "business_id": business_id,
            "item_id": item_id,
            "platform": "ebay",
            "sku": sku,
            "price": price_value,
            "offer_id": offer_id,
            "external_listing_id": listing_id_external,
            "marketplace_listing_id": final_row.get("id"),
            "status": final_row.get("status"),
            "publish_status": final_row.get("publish_status"),
            "sync_status": final_row.get("sync_status"),
            "inventory_created": inventory_created,
            "offer_created": offer_created,
            "published": publish_status == "published",
            "retry_possible": publish_status != "published",
            "result_type": "published" if publish_status == "published" else "partial_success",
            "error": None,
        }

    except Exception as exc:
        error_row = mark_marketplace_listing_error(
            listing_id=listing_row["id"],
            status="error",
            publish_status="failed",
            sync_status="sync_failed",
            error_message=str(exc),
            raw_response={
                "step": "publish_item_to_ebay",
                "error": str(exc),
            },
            last_publish_attempt_at_now=True,
        )

        return {
            "business_id": business_id,
            "item_id": item_id,
            "platform": "ebay",
            "sku": sku,
            "price": price_value,
            "offer_id": offer_id,
            "external_listing_id": listing_id_external,
            "marketplace_listing_id": error_row["id"],
            "status": error_row.get("status"),
            "publish_status": error_row.get("publish_status"),
            "sync_status": error_row.get("sync_status"),
            "inventory_created": inventory_created,
            "offer_created": offer_created,
            "published": False,
            "retry_possible": True,
            "result_type": "partial_success" if inventory_created or offer_created else "failed",
            "error": str(exc),
        }
    
def get_ebay_item_status(
    *,
    business_id: str,
    item_id: str,
) -> dict:
    row = get_marketplace_listing_for_item(
        business_id=business_id,
        item_id=item_id,
        platform="ebay",
    )

    if not row:
        return {
            "business_id": business_id,
            "item_id": item_id,
            "platform": "ebay",
            "marketplace_listing_id": None,
            "status": None,
            "publish_status": None,
            "sync_status": None,
            "external_listing_id": None,
            "offer_id": None,
            "published": False,
            "retry_possible": False,
            "result_type": "not_started",
            "last_error": None,
        }

    publish_status = row.get("publish_status")

    published = publish_status == "published"
    retry_possible = publish_status in ("failed", "unpublished")

    if published:
        result_type = "published"
    elif retry_possible:
        result_type = "partial_success"
    else:
        result_type = "in_progress"

    return {
        "business_id": business_id,
        "item_id": item_id,
        "platform": "ebay",
        "marketplace_listing_id": row.get("id"),
        "status": row.get("status"),
        "publish_status": publish_status,
        "sync_status": row.get("sync_status"),
        "external_listing_id": row.get("external_listing_id"),
        "offer_id": row.get("external_offer_id"),
        "published": published,
        "retry_possible": retry_possible,
        "result_type": result_type,
        "last_error": row.get("last_error"),
    }