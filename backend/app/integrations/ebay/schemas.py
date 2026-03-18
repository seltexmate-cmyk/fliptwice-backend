from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class EbayListing(BaseModel):
    listing_id: str
    title: str
    price: float
    quantity: int
    currency: Optional[str] = None
    listing_url: Optional[str] = None


class EbayImportResponse(BaseModel):
    imported: int
    listings: List[EbayListing]


class EbayIntegrationStatusResponse(BaseModel):
    connected: bool
    platform: str
    environment: str
    status: str
    business_id: str
    token_expires_at: Optional[datetime] = None
    refresh_token_expires_at: Optional[datetime] = None
    last_sync_at: Optional[datetime] = None
    last_error: Optional[str] = None
    scopes: Optional[str] = None


class EbayCallbackResponse(BaseModel):
    message: str
    business_id: str
    state: Optional[str] = None
    access_token_present: bool
    refresh_token_present: bool
    expires_in: Optional[int] = None
    refresh_token_expires_in: Optional[int] = None
    scope: Optional[str] = None
    token_type: Optional[str] = None
    environment: str
    integration_saved: bool


class NormalizedMarketplaceListing(BaseModel):
    source_platform: str
    source_listing_id: str
    source_sku: str | None = None

    title: str | None = None
    description: str | None = None

    quantity: int | None = None
    price: float | None = None
    currency: str | None = None

    listing_status: str | None = None

    raw_payload: dict | None = None


class EbayImportPreviewResponse(BaseModel):
    imported: int
    stored: int
    auto_linked: int
    unmatched: int
    listings: List[NormalizedMarketplaceListing]


class UnmatchedListingRow(BaseModel):
    source_row_id: str
    source_listing_id: str
    source_sku: str | None = None
    title: str | None = None
    listing_status: str | None = None
    quantity: int | None = None
    price: float | None = None
    currency: str | None = None
    updated_at: datetime | None = None


class UnmatchedListingsResponse(BaseModel):
    business_id: str
    platform: str
    count: int
    listings: List[UnmatchedListingRow]


class ManualLinkRequest(BaseModel):
    business_id: str
    source_row_id: str
    item_id: str


class ManualLinkResponse(BaseModel):
    message: str
    business_id: str
    source_row_id: str
    item_id: str
    match_method: str
    is_active: bool


class ManualUnlinkRequest(BaseModel):
    business_id: str
    source_row_id: str


class ManualUnlinkResponse(BaseModel):
    message: str
    business_id: str
    source_row_id: str
    unlinked: bool

class EbayPublishResponse(BaseModel):
    business_id: str
    item_id: str
    platform: str

    sku: str
    price: str

    offer_id: str | None = None
    external_listing_id: str | None = None
    marketplace_listing_id: str

    status: str
    publish_status: str
    sync_status: str

    inventory_created: bool
    offer_created: bool
    published: bool
    retry_possible: bool

    result_type: str
    error: str | None = None


class EbayRetryPublishRequest(BaseModel):
    business_id: str
    item_id: str

class EbayItemStatusResponse(BaseModel):
    business_id: str
    item_id: str
    platform: str

    marketplace_listing_id: str | None = None

    status: str | None = None
    publish_status: str | None = None
    sync_status: str | None = None

    external_listing_id: str | None = None
    offer_id: str | None = None

    published: bool
    retry_possible: bool

    result_type: str
    last_error: str | None = None