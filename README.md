# Buyer Lead Intake Agent

A small agent that reads a free-text buyer inquiry, understands what they want,
checks it against live MLS inventory, and produces a **Lead Brief** a realtor
can read in 30 seconds before calling back.

Built as a take-home assessment for AgentMira. Stack: Python + Groq
(`llama-3.3-70b-versatile`) + pandas. Runs in ~15 seconds for all 12 leads.

## Setup

```bash
git clone <repo>
cd buyer-lead-intake-agent
pip install -r requirements.txt
cp .env.example .env        # add your GROQ_API_KEY
python run.py
```

Get a free Groq API key at https://console.groq.com

## What it does

Each inquiry goes through a pipeline:

```
message
  │
  ├─ 1. safety_agent     detect prompt injection (deterministic, pre-LLM)
  ├─ 2. lead_parser      Groq extracts structured BuyerProfile
  ├─ 3. safety_agent     classify lead type (search / investor / advice / vague)
  ├─ 4. mls_retriever    feasibility probe: is the budget realistic?
  ├─ 5. mls_retriever    search: hard-filter + single neighborhood-widen fallback
  ├─ 6. property_ranker  score and sort candidates with explainable reasons
  ├─ 7. reasoning_agent  summary · heads-up flags · priority · next action
  └─ 8. brief_generator  render PII-free brief (JSON + Markdown)
```

## Output

```
output/
  md/   LEAD-2026-001.md … LEAD-2026-012.md   (realtor-facing, read these)
  json/ LEAD-2026-001.json … LEAD-2026-012.json
  all_briefs.md
  summary.csv
```

## Tests

```bash
python tests/test_pipeline.py   # 12 tests, no API key needed
```

Tests cover injection detection, routing, MLS filtering, the feasibility probe,
ranking, the neighborhood-widen fallback, and the PII guarantee.

## Module map

| File | Responsibility |
|---|---|
| `agent/lead_parser.py` | Groq call → structured `BuyerProfile` |
| `agent/safety_agent.py` | Injection detection + lead classification |
| `agent/mls_retriever.py` | Load CSV · feasibility · search (hard-filter + fallback) |
| `agent/property_ranker.py` | Score and rank candidates |
| `agent/reasoning_agent.py` | Summary · heads-up · priority · next action |
| `agent/brief_generator.py` | Assemble + render `LeadBrief` |
| `agent/pipeline.py` | Orchestration loop |
| `run.py` | Entry point |
