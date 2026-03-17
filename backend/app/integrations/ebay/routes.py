from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.integrations.ebay.schemas import (
    EbayCallbackResponse,
    EbayImportPreviewResponse,
    EbayIntegrationStatusResponse,
    ManualLinkRequest,
    ManualLinkResponse,
    ManualUnlinkRequest,
    ManualUnlinkResponse,
    UnmatchedListingsResponse,
)
from app.integrations.ebay.service import (
    build_connect_url,
    exchange_code_for_tokens,
    get_ebay_integration_status,
    get_unmatched_ebay_listings,
    import_active_listings_for_business,
    manually_link_ebay_listing,
    manually_unlink_ebay_listing,
    persist_oauth_tokens_from_callback,
)

router = APIRouter(prefix="/integrations/ebay", tags=["integrations"])


@router.get("/connect")
def connect_ebay(
    business_id: str = Query(...),
):
    try:
        url = build_connect_url(business_id=business_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return RedirectResponse(url=url, status_code=302)


@router.get("/callback", response_model=EbayCallbackResponse)
def ebay_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
):
    if error:
        raise HTTPException(
            status_code=400,
            detail=f"eBay OAuth error: {error} - {error_description or ''}".strip(),
        )

    if not code:
        raise HTTPException(status_code=400, detail="Missing eBay authorization code")

    try:
        token_payload = exchange_code_for_tokens(code=code)
        persisted = persist_oauth_tokens_from_callback(
            state=state,
            token_payload=token_payload,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "message": "eBay connected successfully",
        "business_id": persisted["business_id"],
        "state": state,
        "access_token_present": bool(token_payload.get("access_token")),
        "refresh_token_present": bool(token_payload.get("refresh_token")),
        "expires_in": token_payload.get("expires_in"),
        "refresh_token_expires_in": token_payload.get("refresh_token_expires_in"),
        "scope": token_payload.get("scope"),
        "token_type": token_payload.get("token_type"),
        "environment": persisted["environment"],
        "integration_saved": True,
    }


@router.get("/status", response_model=EbayIntegrationStatusResponse)
def ebay_status(
    business_id: str = Query(...),
):
    try:
        payload = get_ebay_integration_status(business_id=business_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return EbayIntegrationStatusResponse(**payload)


@router.post("/import-listings", response_model=EbayImportPreviewResponse)
def import_ebay_listings(
    business_id: str = Query(...),
    token: str | None = Query(default=None),
):
    try:
        payload = import_active_listings_for_business(
            business_id=business_id,
            token_override=token,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return EbayImportPreviewResponse(**payload)


@router.get("/unmatched-listings", response_model=UnmatchedListingsResponse)
def ebay_unmatched_listings(
    business_id: str = Query(...),
):
    try:
        payload = get_unmatched_ebay_listings(business_id=business_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return UnmatchedListingsResponse(**payload)


@router.post("/link-listing", response_model=ManualLinkResponse)
def ebay_link_listing(
    request: ManualLinkRequest,
):
    try:
        payload = manually_link_ebay_listing(
            business_id=request.business_id,
            source_row_id=request.source_row_id,
            item_id=request.item_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ManualLinkResponse(**payload)


@router.post("/unlink-listing", response_model=ManualUnlinkResponse)
def ebay_unlink_listing(
    request: ManualUnlinkRequest,
):
    try:
        payload = manually_unlink_ebay_listing(
            business_id=request.business_id,
            source_row_id=request.source_row_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return ManualUnlinkResponse(**payload)