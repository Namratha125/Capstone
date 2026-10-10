"""
check_statute_resolution.py

Reads statutes_cleaned directly from your cleaned_output (the actual
pipeline output, not a re-implementation) and reports the act-resolution
rate. Run this after re-running clean_fact_layer.py with the widened
context to see whether it actually moved the needle from ~17%.

Usage:
    python check_statute_resolution.py /path/to/cleaned_output
    python check_statute_resolution.py /path/to/cleaned_output --sample 1000
"""

import json
import os
import argparse
from collections import Counter


def check(cleaned_dir: str, sample_size: int | None):
    files = [f for f in os.listdir(cleaned_dir) if f.endswith('.json')
              and f != "done_keys.json"]
    if sample_size and sample_size < len(files):
        import random
        random.seed(42)
        files = random.sample(files, sample_size)

    total_bare_sections = 0
    resolved = 0
    resolved_acts = Counter()

    for fname in files:
        with open(os.path.join(cleaned_dir, fname), encoding='utf-8') as fh:
            try:
                data = json.load(fh)
            except Exception:
                continue
        for s in data.get("reasoning", {}).get("statutes_cleaned", []):
            # bare sections only (Constitution articles resolve trivially)
            if s["act_name"] != "Constitution of India" and s["plausible"]:
                total_bare_sections += 1
                if s["act_resolved"]:
                    resolved += 1
                    resolved_acts[s["act_name"]] += 1

    print(f"{'='*60}\nStatute act-resolution check — {cleaned_dir} (n_files={len(files)})\n{'='*60}")
    print(f"  Bare sections: {total_bare_sections}")
    if total_bare_sections:
        print(f"  Resolved:      {resolved} ({100*resolved/total_bare_sections:.1f}%)")
    print(f"  Resolved to:   {dict(resolved_acts.most_common(15))}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cleaned_dir")
    parser.add_argument("--sample", type=int, default=None)
    args = parser.parse_args()
    check(args.cleaned_dir, args.sample)
