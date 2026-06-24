
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .lead_parser import BuyerProfile

# Constants


_MARKET_GROUPS: list[list[str]] = [
    ["Brickell", "Downtown Miami", "Edgewater", "Wynwood"],
    ["Miami Beach", "South Beach", "Mid-Beach", "North Beach", "Bal Harbour", "Key Biscayne"],
    ["Coral Gables", "Coconut Grove", "Pinecrest"],
    ["Aventura", "North Miami"],
    ["Doral"],
]

RECOMMENDABLE_STATUSES = ["Active"]
MAX_RESULTS = 4
MAX_SANE_PRICE = 60_000_000   # excludes the single $250M data outlier


# Data model

@dataclass
class Listing:
    listing_id: str
    mls_number: str
    address: str
    neighborhood: str
    city: str
    price: int
    bedrooms: Optional[float]
    bathrooms: Optional[float]
    sqft: Optional[int]
    year_built: Optional[int]
    property_type: str
    listing_status: str
    days_on_market: Optional[int]
    description: str
    features: set[str] = field(default_factory=set)
    
# Loader 

def _to_int(v) -> Optional[int]:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _parse_features(raw) -> set[str]:
    if not isinstance(raw, str):
        return set()
    return {t.strip() for t in raw.split(";") if t.strip()}


def load_listings(csv_path: str) -> list[Listing]:
    df = pd.read_csv(csv_path)
    out: list[Listing] = []
    for _, r in df.iterrows():
        out.append(Listing(
            listing_id=str(r["listing_id"]),
            mls_number=str(r["mls_number"]),
            address=str(r["address"]),
            neighborhood=str(r["neighborhood"]).strip(),
            city=str(r["city"]).strip(),
            price=_to_int(r["price"]) or 0,
            bedrooms=None if pd.isna(r["bedrooms"]) else float(r["bedrooms"]),
            bathrooms=None if pd.isna(r["bathrooms"]) else float(r["bathrooms"]),
            sqft=_to_int(r["sqft"]),
            year_built=_to_int(r["year_built"]),
            property_type=str(r["property_type"]).strip(),
            listing_status=str(r["listing_status"]).strip(),
            days_on_market=_to_int(r["days_on_market"]),
            description=str(r.get("description", "")),
            features=_parse_features(r.get("features")),
        ))
    return out


# Retriever 

class MLSRetriever:
    def __init__(self, listings: list[Listing]):
        self._all = listings

    def _active(self) -> list[Listing]:
        return [l for l in self._all
                if l.listing_status in RECOMMENDABLE_STATUSES
                and 0 < l.price <= MAX_SANE_PRICE]

    def _apply_filters(
        self,
        pool: list[Listing],
        profile: BuyerProfile,
        neighborhoods: list[str],
    ) -> list[Listing]:
        out = []
        for l in pool:
            if profile.beds_min and (l.bedrooms is None or l.bedrooms < profile.beds_min):
                continue
            if profile.baths_min and (l.bathrooms is None or l.bathrooms < profile.baths_min):
                continue
            if profile.property_types and l.property_type not in profile.property_types:
                continue
            if profile.must_haves and not set(profile.must_haves).issubset(l.features):
                continue
            if neighborhoods and l.neighborhood not in neighborhoods:
                continue
            out.append(l)
        return out

    def feasibility(self, profile: BuyerProfile) -> dict:
        """How many Active listings satisfy non-price constraints? What's cheapest?"""
        pool = self._apply_filters(self._active(), profile, profile.neighborhoods)
        min_price = min((l.price for l in pool), default=None)
        return {"count": len(pool), "min_price": min_price}

    def search(self, profile: BuyerProfile) -> tuple[list[Listing], str | None]:
        
        budget = profile.effective_budget
        active = self._active()
        pool = [l for l in active if not budget or l.price <= budget]

        # Rung 1 — strict
        results = self._apply_filters(pool, profile, profile.neighborhoods)
        if results:
            return results[:MAX_RESULTS], None

        # Rung 2 — widen neighborhood
        if profile.neighborhoods:
            widened = self._adjacent(profile.neighborhoods)
            results = self._apply_filters(pool, profile, widened)
            if results:
                added = sorted(set(widened) - set(profile.neighborhoods))
                note = (
                    f"No exact matches; widened to adjacent submarkets "
                    f"({', '.join(added)}). Results are labeled below."
                )
                return results[:MAX_RESULTS], note

        # Rung 3 — drop property-type constraint, keep everything else
        if profile.property_types:
            saved_types = profile.property_types
            profile.property_types = []
            results = self._apply_filters(pool, profile, profile.neighborhoods)
            profile.property_types = saved_types
            if results:
                note = (
                    f"No {'/'.join(saved_types)} in budget; showing other property "
                    "types that otherwise fit. Results are labeled below."
                )
                return results[:MAX_RESULTS], note

        return [], None

    def find_by_address(self, fragment: str) -> list[Listing]:
        frag = fragment.lower()
        return [l for l in self._all if frag in l.address.lower()]

    @staticmethod
    def _adjacent(neighborhoods: list[str]) -> list[str]:
        expanded = set(neighborhoods)
        for group in _MARKET_GROUPS:
            if any(n in group for n in neighborhoods):
                expanded.update(group)
        return sorted(expanded)
