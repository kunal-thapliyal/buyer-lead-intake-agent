
from __future__ import annotations

from enum import Enum

from .lead_parser import BuyerProfile
from .safety_agent import LeadType


class Priority(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


# Summary

def build_summary(profile: BuyerProfile) -> str:
    name = profile.buyer_name
    if not name or "anonymous" in name.lower():
        name = "An unnamed buyer"

    spec = []
    if profile.beds_min and profile.beds_max and profile.beds_min != profile.beds_max:
        spec.append(f"{profile.beds_min}–{profile.beds_max} bedroom")
    elif profile.beds_min:
        spec.append(f"{profile.beds_min}+ bedroom")

    if profile.property_types:
        spec.append("/".join(profile.property_types))
    else:
        spec.append("home")

    line = f"{name} wants a {' '.join(spec)}"

    if profile.neighborhoods:
        line += f" in {', '.join(profile.neighborhoods)}"

    if profile.effective_budget:
        if profile.budget_stretch and profile.budget_stretch != profile.budget_max:
            line += f", budget ~${profile.budget_max:,} (can stretch to ${profile.budget_stretch:,})"
        else:
            line += f", budget up to ${profile.effective_budget:,}"
    line += "."

    extras = []
    if profile.must_haves:
        extras.append("Non-negotiables: " + ", ".join(profile.must_haves) + ".")
    if profile.nice_to_haves:
        extras.append("Preferred: " + ", ".join(profile.nice_to_haves) + ".")
    if profile.financing:
        extras.append(profile.financing + ".")
    if profile.timeline:
        extras.append(profile.timeline + ".")

    return " ".join([line] + extras)


#  Priority 

def build_priority(
    profile: BuyerProfile,
    lead_type: LeadType,
    has_matches: bool,
    budget_ok: bool,
) -> Priority:
    if lead_type in (LeadType.LOW_QUALITY, LeadType.VAGUE):
        return Priority.LOW
    if not has_matches or not budget_ok:
        return Priority.LOW

    ready = 0
    if profile.financing and "Cash" in profile.financing:
        ready += 1
    if profile.financing and "Pre-approved" in profile.financing:
        ready += 1
    if profile.timeline and any(w in profile.timeline for w in ["Urgent", "year-end", "August"]):
        ready += 1
    if profile.effective_budget and profile.neighborhoods and profile.beds_min:
        ready += 1

    return Priority.HIGH if ready >= 2 else Priority.MEDIUM


# Next action

def build_next_action(lead_type: LeadType, n_matches: int) -> str:
    if lead_type == LeadType.ADVICE_REQUEST:
        return (
            "Call to build rapport. Offer to run a CMA for the property rather "
            "than quoting an offer number cold. Do not share seller motivation "
            "in writing — discuss strategy live."
        )
    if lead_type == LeadType.VAGUE:
        return (
            "Send a short discovery note: ask for budget, bedroom count, target "
            "neighborhoods, and timeline before searching."
        )
    if lead_type == LeadType.LOW_QUALITY:
        return (
            "Send a templated reply asking for contact details and realistic "
            "criteria. Low investment until verified."
        )
    if lead_type == LeadType.INVESTOR:
        return (
            f"Position yourself as an investment-focused agent. Share the "
            f"{n_matches} candidate(s) with rent estimates and cap-rate context. "
            "Ask about target return, hold period, and whether they need management."
        )
    if n_matches == 0:
        return (
            "Nothing in inventory matches today. Call to re-scope — budget, "
            "must-haves, or area — and set up a saved search."
        )
    return (
        f"Call within 24 h. Lead with the top {n_matches} listing(s) below, "
        "confirm the unverifiable items flagged above, and offer to book showings."
    )


# Heads-up flags 

def build_heads_up(
    profile: BuyerProfile,
    *,
    injection: str | None,
    budget_gap: int | None,
    anonymous: bool,
    fallback_note: str | None,
) -> list[str]:
    notes: list[str] = []

    if injection:
        notes.append(
            f"⚠️ SECURITY: This message contained a prompt-injection attempt "
            f"(matched: \"…{injection}…\"). No owner data was exposed. The "
            "legitimate search was still processed — verify identity before "
            "sharing sensitive information."
        )
    if budget_gap:
        notes.append(
            f"💰 BUDGET MISMATCH: Cheapest matching listing is ${budget_gap:,}, "
            "above the buyer's stated budget. Reset expectations on first call."
        )
    if anonymous:
        notes.append("No contact info on file — capture name and phone before investing time.")
    if profile.unverifiable:
        notes.append(
            "Items buyer wants that can't be filtered from the MLS feed — "
            "verify manually: " + "; ".join(profile.unverifiable)
        )
    if profile.special_notes:
        notes.extend(profile.special_notes)
    if profile.missing_fields:
        notes.append("Still unknown — ask on first contact: " + ", ".join(profile.missing_fields) + ".")
    if fallback_note:
        notes.append(fallback_note)

    return notes
