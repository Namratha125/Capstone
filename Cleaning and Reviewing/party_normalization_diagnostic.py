"""
party_normalization_diagnostic.py

Party names like "State Of Orissa And Others Etc Etc" vs "State of Orissa"
are the same entity but different strings. This measures how much a simple
suffix-stripping normalization reduces your total Party node count, so you
can decide if it's worth doing before populating Neo4j (cheap to fix now,
expensive to fix after 50,000 Party nodes exist).
"""

import json
import os
import re
import argparse
from collections import Counter

SUFFIX_PATTERNS = [
    r'\s+and\s+ors\.?$', r'\s+and\s+anr\.?$', r'\s+etc\.?(\s+etc\.?)*$',
    r'\s+and\s+others$', r'\s+&\s+ors\.?$', r'\s+and\s+another$',
]


def normalize_party_name(name: str) -> str:
    n = name.strip()
    low = n.lower()
    for pat in SUFFIX_PATTERNS:
        low = re.sub(pat, '', low, flags=re.IGNORECASE)
    return low.strip().rstrip('.').strip()


def diagnose(folder: str, sample_size: int | None):
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    if sample_size and sample_size < len(files):
        import random
        random.seed(42)
        files = random.sample(files, sample_size)

    raw_names = []
    for fname in files:
        with open(os.path.join(folder, fname), encoding='utf-8') as fh:
            try:
                data = json.load(fh)
            except Exception:
                continue
        parties = data.get("parties", {})
        for role in ("petitioner", "respondent"):
            v = parties.get(role)
            if v:
                raw_names.append(v)

    raw_unique = len(set(n.strip().lower() for n in raw_names))
    normalized_unique = len(set(normalize_party_name(n) for n in raw_names))

    print(f"\n{'='*70}\nParty normalization diagnostic — {folder}\n{'='*70}")
    print(f"  Total party mentions:        {len(raw_names)}")
    print(f"  Unique raw strings:          {raw_unique}")
    print(f"  Unique after normalization:  {normalized_unique}")
    if raw_unique:
        reduction = 100 * (raw_unique - normalized_unique) / raw_unique
        print(f"  Reduction:                   {reduction:.1f}%")

    print(f"\n{'='*70}")
    print("  VERDICT: apply normalize_party_name() before MERGE-ing Party nodes.")
    print("  Even a modest reduction (10-20%) is worth it since fixing party_id")
    print("  collisions after 50k+ nodes exist means a full graph rebuild.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--sample", type=int, default=None)
    args = parser.parse_args()
    diagnose(args.folder, args.sample)
