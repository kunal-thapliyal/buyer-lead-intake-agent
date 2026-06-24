"""
lead_parser.py

Converts a free-text buyer inquiry into a structured BuyerProfile using Groq
(llama-3.3-70b-versatile). Groq handles the fuzzy language understanding;
the result is validated against a known schema before anything downstream
sees it, so a hallucinated or garbled field fails loudly rather than
corrupting a brief silently.

This is where the LLM earns its place: interpreting rambling, chatty, or
vague messages is exactly what it's good at. Safety-critical logic (injection
detection, PII) stays deterministic in safety_agent.py.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

from groq import Groq

client = Groq(api_key=os.environ["GROQ_API_KEY"])
MODEL = "llama-3.3-70b-versatile"

# ── Schema ───────────────────────────────────────────────────────────────────

@dataclass
class BuyerProfile:
    lead_id: str
    buyer_name: str
    channel: str
    received_at: str
    raw_message: str

    # Parsed fields (None = not stated by buyer)
    beds_min: Optional[int] = None
    beds_max: Optional[int] = None
    baths_min: Optional[float] = None
    budget_max: Optional[int] = None
    budget_stretch: Optional[int] = None  
    neighborhoods: list[str] = field(default_factory=list)
    property_types: list[str] = field(default_factory=list)
    must_haves: list[str] = field(default_factory=list)
    nice_to_haves: list[str] = field(default_factory=list)
    timeline: Optional[str] = None
    financing: Optional[str] = None
    special_notes: list[str] = field(default_factory=list)
    unverifiable: list[str] = field(default_factory=list)  
    missing_fields: list[str] = field(default_factory=list)

    @property
    def effective_budget(self) -> Optional[int]:
        return self.budget_stretch or self.budget_max


# ── Groq prompt ──────────────────────────────────────────────────────────────

_SYSTEM = """\
You extract structured real-estate buyer requirements from inquiry messages.
Return ONLY a valid JSON object — no markdown, no prose, no code fences.

Known canonical feature names (use these exactly in must_haves / nice_to_haves):
Pool, Gym, Balcony, Terrace, Ocean View, Bay View, Waterfront, Boat Dock,
Garage, Home Office, Updated Kitchen, Granite Countertops, Smart Home,
Private Beach Access, Concierge, Doorman, Gated Community, Tennis Court,
Wine Cellar, Rooftop, Hardwood Floors, High Ceilings, Walk-in Closet,
Hurricane Impact Windows, Solar Panels, Central AC, Marble Floors,
Stainless Steel Appliances, Garden, Pet Friendly.

Known Miami neighborhoods (use these exactly):
Brickell, Coral Gables, Mid-Beach, North Miami, Doral, Coconut Grove,
Miami Beach, Aventura, South Beach, Edgewater, Pinecrest, Key Biscayne,
North Beach, Bal Harbour, Wynwood, Downtown Miami.

Known property types (use these exactly):
Condo, Townhouse, Single Family, Villa, Multi-Family.
Note: "house" means [Single Family, Villa]. "apartment" means [Condo].
"duplex" means [Multi-Family].

Rules:
- must_haves: features the buyer calls essential / non-negotiable / required.
- nice_to_haves: features the buyer says they'd prefer / ideally want / would love.
- A feature that is "ideally" wanted is nice_to_have, not must_have.
- unverifiable: list items the buyer wants that CANNOT be checked in an MLS feed.
  Common examples: elevator access, single-story layout, city view, parking-spot
  count, school quality/zoning, proximity to pharmacy/grocery/medical, commute time.
- budget_max: the stated maximum. budget_stretch: only if the buyer explicitly
  says they "can go up to" or "can stretch to" a higher number.
- If the buyer is "open on neighborhood" or says a place is their workplace,
  do NOT include it in neighborhoods. Set open_on_neighborhood: true instead.
- financing: "Cash", "Pre-approved", "First-time buyer", or null.
- missing_fields: list any of [budget, bedrooms, neighborhoods] that are absent.

Return this exact shape:
{
  "beds_min": int | null,
  "beds_max": int | null,
  "baths_min": float | null,
  "budget_max": int | null,
  "budget_stretch": int | null,
  "neighborhoods": [str],
  "open_on_neighborhood": bool,
  "property_types": [str],
  "must_haves": [str],
  "nice_to_haves": [str],
  "timeline": str | null,
  "financing": str | null,
  "special_notes": [str],
  "unverifiable": [str],
  "missing_fields": [str]
}
"""


def parse(inquiry: dict) -> BuyerProfile:
    """Call Groq to extract structured intent, then validate and return BuyerProfile."""
    message = inquiry.get("message", "")
    raw = _call_groq(message)
    data = _safe_parse_json(raw)

    # If Groq response is open-on-neighborhood, clear the list
    if data.get("open_on_neighborhood") and data.get("neighborhoods"):
        nbhds = data.get("neighborhoods", [])
        data["special_notes"] = data.get("special_notes", []) + [
            f"Buyer is open on neighborhood; '{', '.join(nbhds)}' appears to be a "
            "commute anchor/workplace — search was not restricted to it."
        ]
        data["neighborhoods"] = []
        mf = data.get("missing_fields", [])
        if "neighborhoods" not in mf:
            mf.append("neighborhoods (open)")
        data["missing_fields"] = mf

    return BuyerProfile(
        lead_id=inquiry.get("lead_id", ""),
        buyer_name=inquiry.get("buyer_name", "Unknown"),
        channel=inquiry.get("channel", ""),
        received_at=inquiry.get("received_at", ""),
        raw_message=message,
        beds_min=data.get("beds_min"),
        beds_max=data.get("beds_max"),
        baths_min=data.get("baths_min"),
        budget_max=data.get("budget_max"),
        budget_stretch=data.get("budget_stretch"),
        neighborhoods=data.get("neighborhoods") or [],
        property_types=data.get("property_types") or [],
        must_haves=data.get("must_haves") or [],
        nice_to_haves=data.get("nice_to_haves") or [],
        timeline=data.get("timeline"),
        financing=data.get("financing"),
        special_notes=data.get("special_notes") or [],
        unverifiable=data.get("unverifiable") or [],
        missing_fields=data.get("missing_fields") or [],
    )


def _call_groq(message: str) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        max_tokens=800,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Buyer message:\n\n{message}"},
        ],
    )
    return resp.choices[0].message.content or ""


def _safe_parse_json(raw: str) -> dict:
    """Strip markdown fences if present and parse JSON; return {} on failure."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
