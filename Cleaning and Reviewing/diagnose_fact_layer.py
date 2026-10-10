"""
diagnose_fact_layer.py

Quantifies the data-quality issues flagged from manual inspection of individual
fact-layer JSONs (noisy judges, garbage statute entries, sparse legal_concepts,
citation ambiguity) across the FULL corpus, so you know whether they're edge
cases or the norm before you build KG preprocessing filters around them.

Usage:
    python diagnose_fact_layer.py /path/to/MERGED_fact_layer_final
    python diagnose_fact_layer.py /path/to/MERGED_fact_layer_final --sample 500
"""

import json
import os
import re
import random
import argparse
from collections import defaultdict

# ---------------------------------------------------------------------------
# Validators (same logic discussed in the KG construction planning chat)
# ---------------------------------------------------------------------------

JUDGE_GARBAGE_PATTERNS = [
    r'^from\s+the$', r'^all$', r'^civil\s*$', r'^civ\s', r'^cur\s',
    r'^sessions$', r'vs\.?\s*$', r'^\d+$', r'date\s+of',
    r'appellate', r'^appeal', r'court\s+of', r'^and$', r'magistrate\s+in',
]

# States/UTs, generic court/legal terms, and connector words that are
# capitalized in judgment text and will otherwise pass a naive
# "has a capitalized word" heuristic. Extend this as you find more in
# your corpus — this is not exhaustive.
JUDGE_STOPLIST = {
    "kerala", "karnataka", "maharashtra", "tamil nadu", "andhra pradesh",
    "uttar pradesh", "west bengal", "punjab", "haryana", "gujarat", "bihar",
    "rajasthan", "odisha", "assam", "telangana", "madhya pradesh", "goa",
    "delhi", "chandigarh", "india", "union of india", "state", "and", "etc",
    "ors", "anr", "magistrate", "munsiff", "judicial service", "high court",
    "supreme court", "governor", "tribunal",
}

def is_valid_judge_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    if len(n) < 4:
        return False
    low = n.lower().strip(".")
    if low in JUDGE_STOPLIST:
        return False
    for pat in JUDGE_GARBAGE_PATTERNS:
        if re.search(pat, low):
            return False
    # A plausible Indian judge name is usually either:
    #  (a) multi-token with at least one capitalized initial, e.g. "K. Ramaswamy"
    #  (b) explicitly prefixed with Justice/J./CJ
    has_initial_pattern = bool(re.search(r'\b[A-Z]\.\s?[A-Z][a-z]+', n))
    has_justice_prefix = bool(re.search(r'\b(justice|j\.|cj|c\.j\.)\b', low))
    multi_token_caps = len(re.findall(r'\b[A-Z][a-z]+\b', n)) >= 2
    return has_initial_pattern or has_justice_prefix or multi_token_caps


def is_plausible_constitution_article(statute_str: str) -> bool:
    """Rejects concatenation artifacts like Constitution_Art_23512."""
    m = re.search(r'Art_(\d+)', statute_str)
    if not m:
        return True  # not a constitution article, skip this check
    num = int(m.group(1))
    return 1 <= num <= 395


def is_plausible_section(statute_str: str) -> bool:
    m = re.search(r'Section_?(\d+)', statute_str)
    if not m:
        return True
    num = int(m.group(1))
    return num <= 10000


def classify_citation(citation: str) -> str:
    # Reporter citations, both common orderings:
    #   "1990 (2) SCC 680"   -> volume in parens after year
    #   "(2008) 17 SCC 703"  -> year in parens, volume unparenthesized
    #   "AIR 1994 SC 736"    -> AIR-prefixed, no SCC/SCR keyword needed
    if re.search(r'\d{4}\s*\(\d+\)\s*(SCC|SCR|AIR)', citation):
        return "reporter"
    if re.search(r'\(\d{4}\)\s*\d+\s*(SCC|SCR|AIR)', citation):
        return "reporter"
    if re.search(r'\bAIR\s*\d{4}\s*(SC|[A-Z]{2,})\b', citation, re.IGNORECASE):
        return "reporter"
    if re.search(r'(Civil|Criminal|Writ)\s+(Appeal|Petition)\s+No', citation, re.IGNORECASE):
        return "case_number"
    return "unknown"  # re-run diagnose_fact_layer.py after this fix; if the
    # unknown rate is still high, share the new sample examples and this
    # will need another iteration — reporter citation formats vary by era.


# ---------------------------------------------------------------------------
# Diagnostic pass
# ---------------------------------------------------------------------------

def diagnose(folder: str, sample_size: int | None):
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    if not files:
        print(f"No .json files found directly in {folder}. "
              f"Check the path — if cases are nested in subfolders, this script "
              f"needs a small tweak to os.walk.")
        return

    if sample_size and sample_size < len(files):
        random.seed(42)
        files = random.sample(files, sample_size)

    stats = defaultdict(lambda: {
        "count": 0,
        "zero_valid_judges": 0,
        "date_null": 0,
        "no_legal_concepts": 0,
        "no_citations": 0,
        "statute_total": 0,
        "statute_implausible": 0,
        "citation_reporter": 0,
        "citation_case_number": 0,
        "citation_unknown": 0,
        "parse_errors": 0,
    })

    for fname in files:
        path = os.path.join(folder, fname)
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception:
            stats["ALL"]["parse_errors"] += 1
            continue

        method = data.get("extraction_method", "unknown")
        s = stats[method]
        s["count"] += 1

        judges = data.get("metadata", {}).get("judges", []) or []
        valid_judges = [j for j in judges if is_valid_judge_name(j)]
        if len(valid_judges) == 0:
            s["zero_valid_judges"] += 1

        if data.get("metadata", {}).get("date") is None:
            s["date_null"] += 1

        if not data.get("legal_concepts"):
            s["no_legal_concepts"] += 1

        if not data.get("citations"):
            s["no_citations"] += 1

        statutes = data.get("reasoning", {}).get("statutes", []) or []
        for st in statutes:
            s["statute_total"] += 1
            if not (is_plausible_constitution_article(st) and is_plausible_section(st)):
                s["statute_implausible"] += 1

        for c in (data.get("citations") or []):
            ctype = classify_citation(c)
            s[f"citation_{ctype}"] += 1
            if ctype == "unknown" and len(s.setdefault("_unknown_examples", [])) < 20:
                s["_unknown_examples"].append(c)

    # ---- Report ----
    print(f"\n{'='*70}\nDiagnostic report — {folder}\n{'='*70}")
    for method, s in stats.items():
        n = s["count"] if s["count"] else 1
        print(f"\n--- extraction_method = {method} (n={s['count']}) ---")
        print(f"  Zero valid judges:      {s['zero_valid_judges']:>5} ({100*s['zero_valid_judges']/n:.1f}%)")
        print(f"  Null date:              {s['date_null']:>5} ({100*s['date_null']/n:.1f}%)")
        print(f"  No legal_concepts:      {s['no_legal_concepts']:>5} ({100*s['no_legal_concepts']/n:.1f}%)")
        print(f"  No citations:           {s['no_citations']:>5} ({100*s['no_citations']/n:.1f}%)")
        if s["statute_total"]:
            print(f"  Statute entries:        {s['statute_total']:>5}, "
                  f"implausible: {s['statute_implausible']} "
                  f"({100*s['statute_implausible']/s['statute_total']:.1f}%)")
        total_cite = s['citation_reporter'] + s['citation_case_number'] + s['citation_unknown']
        if total_cite:
            print(f"  Citations classified:   reporter={s['citation_reporter']}, "
                  f"case_number={s['citation_case_number']}, unknown={s['citation_unknown']}")
        if s.get("parse_errors"):
            print(f"  Parse errors:           {s['parse_errors']}")
        if s.get("_unknown_examples"):
            print(f"  Sample 'unknown' citations (fix classify_citation against these):")
            for ex in s["_unknown_examples"]:
                print(f"    - {ex}")

    print(f"\n{'='*70}")
    print("Read this as: if 'zero_valid_judges' or 'statute_implausible' rates are")
    print("high for 'fallback' but low for 'groq', judges/DECIDED_BY should be built")
    print("mainly from groq-extracted cases, and fallback cases should be flagged")
    print("with lower confidence rather than silently merged in.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Path to MERGED_fact_layer_final")
    parser.add_argument("--sample", type=int, default=None,
                         help="Random sample size (default: all files)")
    args = parser.parse_args()
    diagnose(args.folder, args.sample)
