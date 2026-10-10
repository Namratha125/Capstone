"""
judge_ner_crossvalidate.py

Cross-validates the regex-extracted `metadata.judges` field against spaCy
PERSON-NER, per the dissertation's own Future Work commitment (Section 7.2:
"spaCy and regex-based entity extraction pipeline will be finalized").

WHY THIS EXISTS
----------------
Manual inspection of 2 sample cases showed the regex judge extractor passing
place names ("Kerala") and truncated party fragments ("A. And") as judges.
Patching the regex further just trades one false-positive mode for another
(demonstrated in diagnose_fact_layer.py's test run). NER cross-validation
gives you a second, independent signal instead of a fifth regex tweak.

TWO MODES
---------
1. production_mode (recommended): call `crossvalidate_judges()` from inside
   your Module 2 extraction script, where you still have the raw dec_text /
   rsn_text blocks (the actual sentences classified as Decision/Reasoning)
   BEFORE they get compressed into the final JSON. This is where judge names
   actually appear in context (e.g. "CORAM: Justice A.K. Sikri, Justice R.
   Banumathi") so NER has real signal to work with.

2. json_mode (approximation, run now): operates on the already-produced
   merged JSON, concatenating whatever natural-language fields exist
   (issue, facts, arguments, reasoning.summary, decision.details, summary).
   Judge names rarely appear in these fields, so expect LOW recall here —
   this mode is only useful to sanity-check regex judges against accidental
   PERSON mentions elsewhere in the text (e.g. flags "Kerala" as NOT a
   PERSON, which is exactly the false positive we're trying to catch).

SETUP (run once, in an environment with internet access to GitHub release
assets — this sandbox blocks that domain, so run on Kaggle/Colab/local):
    pip install spacy
    python -m spacy download en_core_web_sm
"""

import json
import os
import re
import argparse
from collections import defaultdict

try:
    import spacy
    _NLP = None
    def get_nlp():
        global _NLP
        if _NLP is None:
            _NLP = spacy.load("en_core_web_sm")
        return _NLP
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


# Reuse the same stoplist logic from diagnose_fact_layer.py so both scripts
# agree on what counts as a plausible judge name.
JUDGE_STOPLIST = {
    "kerala", "karnataka", "maharashtra", "tamil nadu", "andhra pradesh",
    "uttar pradesh", "west bengal", "punjab", "haryana", "gujarat", "bihar",
    "rajasthan", "odisha", "assam", "telangana", "madhya pradesh", "goa",
    "delhi", "chandigarh", "india", "union of india", "state", "and", "etc",
    "ors", "anr", "magistrate", "munsiff", "judicial service", "high court",
    "supreme court", "governor", "tribunal",
}


def regex_judge_candidates(text_or_list):
    """Mimics the existing Module 2 deterministic judge regex, so we have
    something to cross-validate against. Adjust this to match your actual
    extractor if it differs."""
    if isinstance(text_or_list, list):
        return [j for j in text_or_list if isinstance(j, str)]
    # crude fallback: look for "Justice X" / "J. X" patterns in raw text
    return re.findall(r'(?:Justice|J\.)\s+[A-Z][A-Za-z.\s]{2,30}', text_or_list or "")


def ner_judge_candidates(text: str) -> list[str]:
    """Runs spaCy PERSON NER over a text block, filtered to entities near
    judge-indicating keywords (Justice, CJ, Bench, Coram, J.) to reduce
    false positives from party names also being PERSON-tagged."""
    if not SPACY_AVAILABLE:
        raise RuntimeError(
            "spaCy not installed. Run: pip install spacy && "
            "python -m spacy download en_core_web_sm"
        )
    nlp = get_nlp()
    doc = nlp(text or "")
    persons = [ent.text.strip() for ent in doc.ents if ent.label_ == "PERSON"]
    # keep only persons appearing within ~40 chars of a judge-indicating term
    keywords = ["justice", "coram", "bench", "j.", "c.j.", "hon'ble", "honble"]
    kept = []
    lower_text = text.lower() if text else ""
    for p in persons:
        idx = lower_text.find(p.lower())
        if idx == -1:
            continue
        window = lower_text[max(0, idx - 40): idx + len(p) + 10]
        if any(kw in window for kw in keywords):
            kept.append(p)
    return kept


JUDGE_GARBAGE_PATTERNS = [
    r'^from\s+the$', r'^all$', r'^civil\s*$', r'^civ\s', r'^cur\s',
    r'^sessions$', r'vs\.?\s*$', r'^\d+$', r'date\s+of',
    r'appellate', r'^appeal', r'court\s+of', r'^and$', r'magistrate\s+in',
    r'\bin\s+the\b',  # catches "Magistrate In The Kerala"
]


def is_plausible_name(name: str) -> bool:
    low = name.lower().strip(".")
    if len(name) < 4 or low in JUDGE_STOPLIST:
        return False
    for pat in JUDGE_GARBAGE_PATTERNS:
        if re.search(pat, low):
            return False
    # Require it to look like a name: multi-token caps OR "X. Surname" initial
    has_initial_pattern = bool(re.search(r'\b[A-Z]\.\s?[A-Z][a-z]+', name))
    multi_token_caps = len(re.findall(r'\b[A-Z][a-z]+\b', name)) >= 2
    if not (has_initial_pattern or multi_token_caps):
        return False
    # Reject if EVERY capitalized token is itself a stoplist word
    # (handles "Magistrate ... Kerala" style fragments even if the pattern
    # list above doesn't catch a future variant)
    tokens = [t.lower() for t in re.findall(r'\b[A-Za-z]+\b', name)]
    if all(t in JUDGE_STOPLIST or t in {"a", "the", "of", "in"} for t in tokens):
        return False
    return True


def crossvalidate_judges(regex_judges: list[str], raw_text: str) -> dict:
    """
    Returns a dict with:
      - confirmed: judges found by BOTH regex and NER -> highest confidence
      - regex_only: kept only if plausible AND not in stoplist -> medium confidence
      - ner_only: NER found a judge-context PERSON the regex missed -> flag for review
      - rejected: regex candidates that fail the plausibility check outright
    Recommended KG policy: only create DECIDED_BY edges for 'confirmed' and
    'regex_only' (with a confidence property); log 'ner_only' for manual
    review rather than auto-creating nodes from it.
    """
    regex_clean = {j.strip() for j in regex_judges if is_plausible_name(j)}
    rejected = {j.strip() for j in regex_judges if not is_plausible_name(j)}

    if SPACY_AVAILABLE and raw_text:
        ner_clean = {n.strip() for n in ner_judge_candidates(raw_text) if is_plausible_name(n)}
    else:
        ner_clean = set()

    def name_key(n):
        return re.sub(r'[^a-z]', '', n.lower())

    regex_keys = {name_key(n): n for n in regex_clean}
    ner_keys = {name_key(n): n for n in ner_clean}

    confirmed = [regex_keys[k] for k in regex_keys if k in ner_keys]
    regex_only = [regex_keys[k] for k in regex_keys if k not in ner_keys]
    ner_only = [ner_keys[k] for k in ner_keys if k not in regex_keys]

    return {
        "confirmed": confirmed,
        "regex_only": regex_only,
        "ner_only": ner_only,
        "rejected": list(rejected),
    }


def json_mode_run(folder: str, sample_size: int = 50):
    """Approximate check against already-produced JSON (limited signal —
    see module docstring). Reports how often existing metadata.judges
    entries are corroborated by any PERSON mention elsewhere in the case
    text, and flags likely false positives."""
    if not SPACY_AVAILABLE:
        print("spaCy not available in this environment. Install it where "
              "you run this (see module docstring), then re-run.")
        return

    files = [f for f in os.listdir(folder) if f.endswith('.json')][:sample_size]
    totals = defaultdict(int)
    examples_rejected = []

    for fname in files:
        with open(os.path.join(folder, fname), encoding='utf-8') as fh:
            data = json.load(fh)

        judges = data.get("metadata", {}).get("judges", []) or []
        text_fields = [
            data.get("issue", ""),
            " ".join(data.get("facts", []) or []),
            " ".join(data.get("petitioner_arguments", []) or []),
            " ".join(data.get("respondent_arguments", []) or []),
            data.get("reasoning", {}).get("summary", ""),
            data.get("decision", {}).get("details", ""),
            data.get("summary", ""),
        ]
        combined_text = " ".join(t for t in text_fields if t)

        result = crossvalidate_judges(judges, combined_text)
        totals["cases"] += 1
        totals["confirmed"] += len(result["confirmed"])
        totals["regex_only"] += len(result["regex_only"])
        totals["ner_only"] += len(result["ner_only"])
        totals["rejected"] += len(result["rejected"])

        if result["rejected"]:
            examples_rejected.append((fname, result["rejected"]))

    print(f"\n{'='*70}\nJudge NER cross-validation (json_mode, n={totals['cases']})\n{'='*70}")
    print(f"  Confirmed (regex+NER agree):  {totals['confirmed']}")
    print(f"  Regex-only (no NER support):  {totals['regex_only']}")
    print(f"  NER-only (regex missed):      {totals['ner_only']}")
    print(f"  Rejected outright:            {totals['rejected']}")
    if examples_rejected:
        print(f"\n  Sample rejections:")
        for fname, rej in examples_rejected[:10]:
            print(f"    {fname}: {rej}")
    print(f"\n  NOTE: json_mode has low recall by design (judge names rarely")
    print(f"  appear in issue/facts/arguments text). Run production_mode inside")
    print(f"  Module 2 against dec_text/rsn_text for the real signal.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Path to MERGED_fact_layer_final")
    parser.add_argument("--sample", type=int, default=50)
    args = parser.parse_args()
    json_mode_run(args.folder, args.sample)
