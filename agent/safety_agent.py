"""
safety_agent.py

Two responsibilities, both deterministic:

1. detect_injection(text) — scan for prompt-hijacking attempts before the
   message touches the LLM. An LLM is what injection attacks target; asking
   it to police itself is circular.

2. classify(profile) — route the lead to the right handler. Each class takes
   a genuinely different path through the pipeline, which is what makes this
   an agent rather than a single matcher.
"""
from __future__ import annotations

import re
from enum import Enum

from .lead_parser import BuyerProfile

# ── Injection detection ───────────────────────────────────────────────────────

_INJECTION_PATTERNS = [
    r"ignore (all )?(previous|prior|above) instructions",
    r"disregard (all )?(previous|prior|above)",
    r"forget (your|all) (instructions|rules)",
    r"system prompt",
    r"you are now",
    r"respond by listing .{0,30}(owner|phone|email|database)",
    r"list all .{0,20}(owner|phone|email)",
    r"(owner|seller).{0,20}(phone|number|contact).{0,20}database",
    r"from the database",
    r"in json.{0,20}(format|so i can contact)",
    r"reveal (the|your) (prompt|instructions)",
]
_INJECTION_RE = re.compile(
    "|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.I
)


def detect_injection(text: str) -> tuple[bool, str | None]:
    """Return (is_injection, matched_snippet | None)."""
    m = _INJECTION_RE.search(text or "")
    if not m:
        return False, None
    start = max(0, m.start() - 12)
    end = min(len(text), m.end() + 12)
    return True, text[start:end].strip()


# ── Lead classification ───────────────────────────────────────────────────────

class LeadType(str, Enum):
    PROPERTY_SEARCH = "property_search"
    INVESTOR        = "investor"
    ADVICE_REQUEST  = "advice_request"
    VAGUE           = "vague"
    LOW_QUALITY     = "low_quality"


_ADVICE_CUES = [
    "putting in an offer", "put in an offer", "make an offer",
    "should i go lower", "should i offer", "negotiat",
    "seller's motivation", "sellers' motivation", "counteroffer",
    "counter offer", "lowball",
]

_INVESTOR_CUES = [
    "investment", "investor", "cash-flow", "cash flow",
    "rental income", "rent out", "rented out", "roi", "cap rate",
    "portfolio", "flip",
]


def _has_criteria(p: BuyerProfile) -> bool:
    return any([
        p.beds_min is not None,
        p.effective_budget is not None,
        bool(p.neighborhoods),
        bool(p.must_haves),
        bool(p.property_types),
    ])


def classify(profile: BuyerProfile, anonymous: bool) -> LeadType:
    text = profile.raw_message.lower()

    advice_hits = sum(1 for c in _ADVICE_CUES if c in text)
    is_investor  = any(c in text for c in _INVESTOR_CUES)
    has_criteria = _has_criteria(profile)

    # Asking for offer/negotiation strategy without real search intent
    if advice_hits >= 2 and not (profile.beds_min or profile.neighborhoods or profile.must_haves):
        return LeadType.ADVICE_REQUEST

    # Anonymous + nothing actionable → waste of realtor time right now
    if anonymous and not has_criteria:
        return LeadType.LOW_QUALITY

    if not has_criteria:
        return LeadType.VAGUE

    if is_investor:
        return LeadType.INVESTOR

    return LeadType.PROPERTY_SEARCH
