
from __future__ import annotations

import re

from .brief_generator import LeadBrief, assemble
from .lead_parser import BuyerProfile, parse
from .mls_retriever import MLSRetriever
from .property_ranker import rank
from .reasoning_agent import (
    Priority,
    build_heads_up,
    build_next_action,
    build_priority,
    build_summary,
)
from .safety_agent import LeadType, classify, detect_injection


def process(inquiry: dict, retriever: MLSRetriever) -> LeadBrief:
    trace: list[str] = []

    # 1. Safety scan 
    raw_text = inquiry.get("message", "")
    is_injection, snippet = detect_injection(raw_text)
    if is_injection:
        trace.append("Safety: prompt-injection attempt detected and quarantined.")
    else:
        trace.append("Safety: no injection detected.")

    # 2. Parse intent (Groq) 
    profile: BuyerProfile = parse(inquiry)
    trace.append(
        f"Parser: extracted beds={profile.beds_min}–{profile.beds_max}, "
        f"budget=${profile.budget_max}, nbhd={profile.neighborhoods}, "
        f"must={profile.must_haves}, nice={profile.nice_to_haves}."
    )

    anonymous = (
        "anonymous" in profile.buyer_name.lower()
        or not inquiry.get("buyer_phone")
    )

    # 3. Classify 
    lead_type = classify(profile, anonymous=anonymous)
    trace.append(f"Classifier: {lead_type.value}.")

    # 4. Feasibility check 
    feas = retriever.feasibility(profile)
    budget_gap: int | None = None
    budget_ok = True
    if profile.effective_budget and feas["min_price"] is not None:
        if feas["min_price"] > profile.effective_budget * 1.05:
            budget_ok = False
            budget_gap = feas["min_price"]
            trace.append(
                f"Feasibility: cheapest match ${feas['min_price']:,} > "
                f"budget ${profile.effective_budget:,} — mismatch flagged."
            )
        else:
            trace.append(f"Feasibility: {feas['count']} listings meet non-price criteria.")
    else:
        trace.append(f"Feasibility: {feas['count']} listings meet non-price criteria.")

    # 5 & 6. Search + rank (only when search makes sense) 
    scored, fallback_note = [], None
    context_listing: dict | None = None

    if lead_type in (LeadType.PROPERTY_SEARCH, LeadType.INVESTOR):
        if not budget_ok:
            
            over_budget_profile = BuyerProfile(
                **{**profile.__dict__,
                   "budget_max": budget_gap,
                   "budget_stretch": None}
            )
            listings, fallback_note = retriever.search(over_budget_profile)
            scored = rank(listings, profile, fallback_note)
            if scored:
                # Label each as over-budget
                for s in scored:
                    s.gaps.insert(0, f"OVER BUDGET: ${s.listing.price:,} vs buyer's ${profile.effective_budget:,}.")
            trace.append(f"Search [budget-mismatch mode]: showing {len(scored)} closest over-budget option(s) for context.")
        else:
            listings, fallback_note = retriever.search(profile)
            scored = rank(listings, profile, fallback_note)
            trace.append(
                f"Search: {len(scored)} candidate(s)"
                + (" [widened]" if fallback_note else "") + "."
            )
    elif lead_type == LeadType.ADVICE_REQUEST:
        # Pull the specific listing the buyer referenced, if any
        context_listing = _find_referenced_listing(retriever, raw_text)
        if context_listing:
            trace.append(f"Advice: found referenced listing ({context_listing['address']}).")
        trace.append("Search: skipped — advice request routes to human.")
    elif not budget_ok:
        trace.append("Search: skipped — budget mismatch; realtor must reset expectations first.")
    else:
        trace.append(f"Search: skipped — {lead_type.value}.")

    # 7. Reason
    summary    = build_summary(profile)
    priority   = build_priority(profile, lead_type, has_matches=bool(scored), budget_ok=budget_ok)
    next_action = build_next_action(lead_type, n_matches=len(scored))
    heads_up   = build_heads_up(
        profile,
        injection=snippet if is_injection else None,
        budget_gap=budget_gap,
        anonymous=anonymous,
        fallback_note=fallback_note,
    )

    # 8. Assemble
    return assemble(
        profile=profile,
        lead_type=lead_type,
        priority=priority,
        summary=summary,
        heads_up=heads_up,
        scored=scored,
        next_action=next_action,
        trace=trace,
        context_listing=context_listing,
    )


# Helper 

def _find_referenced_listing(retriever: MLSRetriever, text: str) -> dict | None:
    m = re.search(
        r"\d{2,5}\s+[A-Z][A-Za-z]+\s+"
        r"(?:Road|Rd|Avenue|Ave|Street|St|Drive|Dr|Boulevard|Blvd|Circle|Way|Court|Ct|Lane|Terrace|Ter)",
        text,
    )
    if not m:
        return None
    results = retriever.find_by_address(m.group(0))
    if not results:
        return None
    l = results[0]
    return {
        "listing_id": l.listing_id,
        "address": l.address,
        "neighborhood": l.neighborhood,
        "price": l.price,
        "bedrooms": l.bedrooms,
        "bathrooms": l.bathrooms,
        "property_type": l.property_type,
        "status": l.listing_status,
        "days_on_market": l.days_on_market,
        "context_only": True,
        "why_it_matches": [
            f"Buyer-referenced listing. Asking ${l.price:,}, status: {l.listing_status}, "
            f"{l.days_on_market} days on market. Seller identity not shown."
        ],
        "gaps": [],
    }
