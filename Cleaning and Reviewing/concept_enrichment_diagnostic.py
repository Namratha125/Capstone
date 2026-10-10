"""
concept_enrichment_diagnostic.py

The dissertation's legal_concepts field is often empty ([]). This measures
how much a supplementary keyword extraction pass over reasoning.principles
actually recovers, so you know whether APPLIES_CONCEPT will be a real graph
layer or still mostly empty even after enrichment.
"""

import json
import os
import argparse
from collections import Counter

# Same 30-keyword-style vocabulary idea from the dissertation. Extend based
# on what your corpus's `principles` text actually contains.
CONCEPT_VOCAB = {
    "natural justice": "natural_justice",
    "res judicata": "res_judicata",
    "mens rea": "mens_rea",
    "estoppel": "estoppel",
    "fundamental rights": "fundamental_rights",
    "due process": "due_process",
    "audi alteram partem": "audi_alteram_partem",
    "burden of proof": "burden_of_proof",
    "vicarious liability": "vicarious_liability",
    "doctrine of merger": "doctrine_of_merger",
    "locus standi": "locus_standi",
    "ultra vires": "ultra_vires",
    "promissory estoppel": "promissory_estoppel",
    "quasi-judicial": "quasi_judicial",
    "principles of natural justice": "natural_justice",
}


def extract_concepts_from_text(text: str) -> set:
    text = (text or "").lower()
    return {cid for phrase, cid in CONCEPT_VOCAB.items() if phrase in text}


def diagnose(folder: str, sample_size: int | None):
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    if sample_size and sample_size < len(files):
        import random
        random.seed(42)
        files = random.sample(files, sample_size)

    n = 0
    empty_before = 0
    empty_after = 0
    total_existing = 0
    total_enriched = 0
    enriched_concept_counts = Counter()

    for fname in files:
        with open(os.path.join(folder, fname), encoding='utf-8') as fh:
            try:
                data = json.load(fh)
            except Exception:
                continue
        n += 1
        existing = set(data.get("legal_concepts") or [])
        principles_text = " ".join(data.get("reasoning", {}).get("principles", []) or [])
        summary_text = data.get("reasoning", {}).get("summary", "") or ""
        found = extract_concepts_from_text(principles_text + " " + summary_text)

        merged = existing | found
        total_existing += len(existing)
        total_enriched += len(merged)
        enriched_concept_counts.update(found)

        if not existing:
            empty_before += 1
        if not merged:
            empty_after += 1

    print(f"\n{'='*70}\nLegal concept enrichment diagnostic — {folder} (n={n})\n{'='*70}")
    print(f"  Cases with empty legal_concepts BEFORE enrichment: {empty_before} "
          f"({100*empty_before/max(n,1):.1f}%)")
    print(f"  Cases with empty legal_concepts AFTER enrichment:  {empty_after} "
          f"({100*empty_after/max(n,1):.1f}%)")
    print(f"  Avg concepts/case before: {total_existing/max(n,1):.2f}")
    print(f"  Avg concepts/case after:  {total_enriched/max(n,1):.2f}")
    print(f"  Most common enriched concepts found: {enriched_concept_counts.most_common(10)}")

    print(f"\n{'='*70}")
    reduction = empty_before - empty_after
    if n and reduction / n < 0.1:
        print("  VERDICT: this vocabulary barely moves the needle. Either")
        print("  substantially expand CONCEPT_VOCAB using real phrases pulled")
        print("  from your corpus's principles/summary text, or accept that")
        print("  APPLIES_CONCEPT will be a sparse layer and don't over-invest.")
    else:
        print("  VERDICT: enrichment meaningfully reduces empty-concept cases —")
        print("  worth keeping as a preprocessing step.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--sample", type=int, default=None)
    args = parser.parse_args()
    diagnose(args.folder, args.sample)
