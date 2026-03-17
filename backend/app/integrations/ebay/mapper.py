from __future__ import annotations

from typing import Any, Dict, List

from app.integrations.ebay.schemas import NormalizedMarketplaceListing


def map_ebay_inventory_item(item: Dict[str, Any]) -> NormalizedMarketplaceListing:
    """
    Convert a raw eBay inventory item into a normalized FlipTwice listing.
    """

    sku = item.get("sku")
    product = item.get("product", {}) or {}
    availability = item.get("availability", {}) or {}
    ship_to_location = availability.get("shipToLocationAvailability", {}) or {}

    quantity = ship_to_location.get("quantity")

    return NormalizedMarketplaceListing(
        source_platform="ebay",
        source_listing_id=str(sku or ""),
        source_sku=sku,

        title=product.get("title"),
        description=None,

        quantity=int(quantity) if quantity is not None else None,
        price=None,
        currency=None,

        listing_status="ACTIVE",

        raw_payload=item,
    )


def map_ebay_inventory_response(data: Dict[str, Any]) -> List[NormalizedMarketplaceListing]:
    """
    Map the full eBay inventory API response to normalized listings.
    """

    items = data.get("inventoryItems", []) or []

    listings: List[NormalizedMarketplaceListing] = []

    for item in items:
        listings.append(map_ebay_inventory_item(item))

    return listings