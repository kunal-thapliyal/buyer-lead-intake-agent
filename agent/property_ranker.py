"""
property_ranker.py

Takes the list of Listings that survived the hard filters in mls_retriever
and produces scored, annotated ScoredListing objects.

Scoring is transparent by design: every point a listing earns is captured as
a human-readable reason, and every shortfall is captured as a gap. A realtor
reading the brief can see exactly why listing A ranked above listing B.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .lead_parser import BuyerProfile
from .mls_retriever import Listing

# ── Weights ───────────────────────────────────────────────────────────────────
_W = {
    "neighborhood_exact":    30,
    "neighborhood_adjacent": 12,
    "property_type_match":   12,
    "bedroom_ideal":         15,
    "bedroom_extra":          6,
    "bathroom_adequate":      8,
    "price_sweet_spot":      18,   # 60–100 % of budget
    "price_value":            6,   # < 60 % (cheaper, but maybe small)
    "nice_to_have_feature":   8,
    "fresh_listing":          5,   # ≤ 30 days on market
}


# ── Output type ───────────────────────────────────────────────────────────────

@dataclass
class ScoredListing:
    listing: Listing
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


# ── Ranker ────────────────────────────────────────────────────────────────────

def rank(
    listings: list[Listing],
    profile: BuyerProfile,
    fallback_note: str | None = None,
) -> list[ScoredListing]:
    """Score each listing and return them sorted best-first."""
    scored = [_score(l, profile, fallback_note) for l in listings]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored


def _score(l: Listing, p: BuyerProfile, fallback_note: str | None) -> ScoredListing:
    s = ScoredListing(listing=l)

    # Neighborhood
    if p.neighborhoods:
        if l.neighborhood in p.neighborhoods:
            s.score += _W["neighborhood_exact"]
            s.reasons.append(f"In requested neighborhood ({l.neighborhood}).")
        else:
            s.score += _W["neighborhood_adjacent"]
            s.gaps.append(f"In {l.neighborhood} — adjacent to requested area.")
    else:
        s.reasons.append(f"Neighborhood: {l.neighborhood}.")

    # Property type
    if p.property_types:
        if l.property_type in p.property_types:
            s.score += _W["property_type_match"]
            s.reasons.append(f"Property type matches ({l.property_type}).")
        else:
            s.gaps.append(f"Is a {l.property_type}, not the requested type.")

    # Bedrooms
    if p.beds_min is not None and l.bedrooms is not None:
        beds = int(l.bedrooms)
        if p.beds_max and p.beds_min <= beds <= p.beds_max:
            s.score += _W["bedroom_ideal"]
            s.reasons.append(f"{beds} BR — within the {p.beds_min}–{p.beds_max} range.")
        elif beds == p.beds_min:
            s.score += _W["bedroom_ideal"]
            s.reasons.append(f"{beds} BR — meets minimum.")
        elif beds > p.beds_min:
            s.score += _W["bedroom_extra"]
            s.reasons.append(f"{beds} BR — exceeds the {p.beds_min}-BR minimum.")

    # Bathrooms
    if p.baths_min and l.bathrooms and l.bathrooms >= p.baths_min:
        s.score += _W["bathroom_adequate"]

    # Must-haves (already enforced as hard filters — confirm them)
    if p.must_haves:
        s.reasons.append("Has all must-haves: " + ", ".join(p.must_haves) + ".")

    # Nice-to-haves
    matched = [f for f in p.nice_to_haves if f in l.features]
    missing = [f for f in p.nice_to_haves if f not in l.features]
    for _ in matched:
        s.score += _W["nice_to_have_feature"]
    if matched:
        s.reasons.append("Preferred features present: " + ", ".join(matched) + ".")
    if missing:
        s.gaps.append("Missing preferred features: " + ", ".join(missing) + ".")

    # Price fit
    budget = p.effective_budget
    if budget:
        ratio = l.price / budget
        if 0.6 <= ratio <= 1.0:
            s.score += _W["price_sweet_spot"]
            s.reasons.append(f"${l.price:,} — {ratio:.0%} of budget, strong fit.")
        elif ratio < 0.6:
            s.score += _W["price_value"]
            s.reasons.append(f"${l.price:,} — well under budget; verify size meets expectations.")
        else:
            s.reasons.append(f"${l.price:,}.")

    # Freshness / negotiation signal
    dom = l.days_on_market
    if dom is not None:
        if dom <= 30:
            s.score += _W["fresh_listing"]
            s.reasons.append(f"Freshly listed ({dom} days on market).")
        elif dom >= 120:
            s.gaps.append(f"On market {dom} days — may have negotiating room.")

    # Label widened results
    if fallback_note and p.neighborhoods and l.neighborhood not in p.neighborhoods:
        s.gaps.insert(0, "OUTSIDE requested neighborhood (widened search).")

    return s
