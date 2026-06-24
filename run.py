#!/usr/bin/env python3
"""
run.py — generate Lead Briefs for all inquiries.

Usage:
    python run.py
    python run.py --inquiries data/sample_buyer_inquiries.json
    python run.py --mls data/miami_mls_listings.csv --out output/

Requires:
    GROQ_API_KEY set in environment (or in a .env file).
"""
import argparse
import csv
import json
import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

if not os.environ.get("GROQ_API_KEY"):
    sys.exit("Error: GROQ_API_KEY not set. Copy .env.example to .env and add your key.")

from agent.brief_generator import to_dict, to_markdown
from agent.mls_retriever import MLSRetriever, load_listings
from agent.pipeline import process

ROOT = os.path.dirname(__file__)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--inquiries",
        default=os.path.join(ROOT, "data", "sample_buyer_inquiries.json")
    )
    ap.add_argument(
        "--mls",
        default=os.path.join(ROOT, "data", "miami_mls_listings.csv")
    )
    ap.add_argument(
        "--out",
        default=os.path.join(ROOT, "output")
    )

    args = ap.parse_args()

    os.makedirs(os.path.join(args.out, "json"), exist_ok=True)
    os.makedirs(os.path.join(args.out, "md"), exist_ok=True)

    listings = load_listings(args.mls)
    retriever = MLSRetriever(listings)

    with open(args.inquiries, encoding="utf-8") as f:
        inquiries = json.load(f)

    all_md = []
    summary_rows = []

    print(
        f"\nProcessing {len(inquiries)} leads via Groq "
        f"(llama-3.3-70b-versatile)...\n"
    )

    for inq in inquiries:

        brief = process(inq, retriever)

        d = to_dict(brief)
        md = to_markdown(brief)

        # JSON output
        with open(
            os.path.join(args.out, "json", f"{brief.lead_id}.json"),
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                d,
                f,
                indent=2,
                ensure_ascii=False
            )

        # Markdown output
        with open(
            os.path.join(args.out, "md", f"{brief.lead_id}.md"),
            "w",
            encoding="utf-8"
        ) as f:
            f.write(md)

        all_md.append(md)
        all_md.append("\n---\n")

        n_recs = len(
            [
                r
                for r in brief.recommendations
                if not r.get("context_only")
            ]
        )

        summary_rows.append({
            "lead_id": brief.lead_id,
            "buyer": brief.buyer_name,
            "type": brief.lead_type.value,
            "priority": brief.priority.value,
            "recommendations": n_recs,
            "heads_up_flags": len(brief.heads_up),
        })

        print(
            f"  {brief.lead_id}  "
            f"{brief.lead_type.value:<16}  "
            f"{brief.priority.value:<7}  "
            f"{n_recs} rec(s)"
        )

        time.sleep(0.3)


    with open(
        os.path.join(args.out, "all_briefs.md"),
        "w",
        encoding="utf-8"
    ) as f:
        f.write("\n".join(all_md))

    # Summary CSV
    with open(
        os.path.join(args.out, "summary.csv"),
        "w",
        newline="",
        encoding="utf-8"
    ) as f:
        wr = csv.DictWriter(
            f,
            fieldnames=list(summary_rows[0].keys())
        )
        wr.writeheader()
        wr.writerows(summary_rows)

    print(f"\nDone. Briefs written to {args.out}/")


if __name__ == "__main__":
    main()