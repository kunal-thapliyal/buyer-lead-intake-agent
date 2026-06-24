from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .lead_parser import BuyerProfile
from .property_ranker import ScoredListing
from .reasoning_agent import Priority
from .safety_agent import LeadType

_BADGE = {Priority.HIGH: "🔥 HIGH", Priority.MEDIUM: "🟡 MEDIUM", Priority.LOW: "⚪ LOW"}


# Data class

@dataclass
class LeadBrief:
    lead_id: str
    buyer_name: str
    channel: str
    received_at: str
    lead_type: LeadType
    priority: Priority
    summary: str
    heads_up: list[str]
    recommendations: list[dict]
    next_action: str
    trace: list[str] = field(default_factory=list)   # reasoning steps for transparency


# Assembler

def assemble(
    profile: BuyerProfile,
    lead_type: LeadType,
    priority: Priority,
    summary: str,
    heads_up: list[str],
    scored: list[ScoredListing],
    next_action: str,
    trace: list[str],
    context_listing: dict | None = None,   # for advice-request reference lookups
) -> LeadBrief:
    recs = [_render(s) for s in scored]
    if context_listing:
        recs.append(context_listing)

    return LeadBrief(
        lead_id=profile.lead_id,
        buyer_name=profile.buyer_name,
        channel=profile.channel,
        received_at=profile.received_at,
        lead_type=lead_type,
        priority=priority,
        summary=summary,
        heads_up=heads_up,
        recommendations=recs,
        next_action=next_action,
        trace=trace,
    )


def _render(s: ScoredListing) -> dict:
    l = s.listing
    return {
        "listing_id": l.listing_id,
        "mls_number": l.mls_number,
        "address": l.address,
        "neighborhood": l.neighborhood,
        "price": l.price,
        "bedrooms": l.bedrooms,
        "bathrooms": l.bathrooms,
        "sqft": l.sqft,
        "property_type": l.property_type,
        "status": l.listing_status,
        "days_on_market": l.days_on_market,
        "match_score": s.score,
        "why_it_matches": s.reasons,
        "gaps": s.gaps,
    }


# Renderers 

def to_dict(brief: LeadBrief) -> dict:
    d = asdict(brief)
    d["lead_type"] = brief.lead_type.value
    d["priority"] = brief.priority.value
    return d


def to_markdown(brief: LeadBrief) -> str:
    L: list[str] = []
    L.append(f"# Lead Brief — {brief.buyer_name}")
    L.append("")
    L.append(
        f"**Lead:** {brief.lead_id}  |  **Channel:** {brief.channel}  |  "
        f"**Received:** {brief.received_at}"
    )
    L.append(
        f"**Priority:** {_BADGE.get(brief.priority, brief.priority.value)}  |  "
        f"**Type:** {brief.lead_type.value.replace('_', ' ').title()}"
    )
    L.append("")

    L.append("## What the buyer wants")
    L.append(brief.summary)
    L.append("")

    if brief.heads_up:
        L.append("## ⚑ Before you reach out")
        for note in brief.heads_up:
            L.append(f"- {note}")
        L.append("")

    L.append("## Recommended properties")
    if not brief.recommendations:
        L.append("_No inventory matched — see next action._")
    else:
        for i, r in enumerate(brief.recommendations, 1):
            ctx = " *(reference — buyer-mentioned)*" if r.get("context_only") else ""
            beds = f"{int(r['bedrooms'])}BR" if r.get("bedrooms") else ""
            baths = f"/{r['bathrooms']}BA" if r.get("bathrooms") else ""
            sqft = f" · {r['sqft']:,} sqft" if r.get("sqft") else ""
            score_txt = f" · score {r['match_score']}" if "match_score" in r else ""
            L.append(f"### {i}. {r['address']} — ${r['price']:,}{ctx}")
            L.append(
                f"{r['neighborhood']} · {r.get('property_type', '')} · "
                f"{beds}{baths}{sqft} · {r.get('status', '')} · "
                f"{r.get('days_on_market', '?')} days on market{score_txt}"
            )
            for w in r.get("why_it_matches", []):
                L.append(f"  - ✅ {w}")
            for g in r.get("gaps", []):
                L.append(f"  - ⚠️ {g}")
            L.append("")

    L.append("## Next action")
    L.append(brief.next_action)
    L.append("")

    L.append("<details><summary>Reasoning trace</summary>")
    L.append("")
    for step in brief.trace:
        L.append(f"- {step}")
    L.append("")
    L.append("</details>")
    L.append("")
    return "\n".join(L)
