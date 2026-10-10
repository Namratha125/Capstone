"""
clean_fact_layer.py

The last step before Neo4j population. Reads every case JSON from
MERGED_fact_layer_final, applies all validated fixes, and writes one
cleaned JSON per case to an output directory.
Does NOT call the LLM — this only transforms data you already have.

Fixes applied (confirmed by 500-case and 10,000-case diagnostic runs):
  1. Judges    → filtered to plausible names (garbage patterns fixed in
                 kg_preprocess_utils.py), each tagged with confidence
                 "high"/"medium"; zero-judge cases get has_judge_data: false.
  2. Statutes  → converted to structured records (statute_id, act_name,
                 section, plausible, act_resolved, domain). Implausible
                 entries marked plausible: false — skip these in Neo4j.
                 Deduplicated per case.
  3. Citations → each citation tagged with citation_type
                 (reporter / case_number / unknown). Regex covers all
                 formats found in the 10k sample.
  4. Concepts  → enriched via keyword pass over principles, reasoning
                 summary, decision details, and outcome reasoning.
                 Merged with sparse existing legal_concepts field.
  5. Parties   → normalized names + outcome_for_party tag added.
  6. Arguments → argument_id added to each argument for Neo4j
                 Argument node creation (case_id_P_0, case_id_R_0, ...).
  7. temporal_year → always set from year (100% populated); date is
                 null in ~26% of cases and Stage 3 only needs year anyway.

Usage (Colab):
    !python clean_fact_layer.py \
        /content/drive/MyDrive/MERGED_fact_layer_final \
        /content/drive/MyDrive/CLEANED_fact_layer

    # Test on 500 files first:
    !python clean_fact_layer.py \
        /content/drive/MyDrive/MERGED_fact_layer_final \
        /content/drive/MyDrive/CLEANED_fact_layer \
        --sample 500

Resumable: checkpoint file (done_keys.json) tracks completed filenames.
If the Colab session dies, re-run the same command — already-cleaned
files are skipped automatically.
"""

import json
import os
import argparse

from kg_preprocess_utils import (
    is_valid_judge_name, judge_confidence,
    normalize_statutes_for_case,
    classify_citation,
    enrich_concepts,
    normalize_party_name, outcome_for_party,
    build_argument_nodes,
)

CHECKPOINT_FILE = "done_keys.json"


# ─────────────────────────────────────────────────────────────────────────────
# CHECKPOINT  (Dhatri: keyed by filename, not case_id — safer for bad JSONs)
# ─────────────────────────────────────────────────────────────────────────────

def load_checkpoint(output_dir: str) -> set:
    path = os.path.join(output_dir, CHECKPOINT_FILE)
    if os.path.exists(path):
        with open(path, encoding='utf-8') as fh:
            return set(json.load(fh))
    return set()


def save_checkpoint(output_dir: str, done: set):
    path = os.path.join(output_dir, CHECKPOINT_FILE)
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(sorted(done), fh)


# ─────────────────────────────────────────────────────────────────────────────
# CORE TRANSFORM
# ─────────────────────────────────────────────────────────────────────────────

def clean_case(data: dict) -> dict:
    out = dict(data)  # preserve all original fields alongside cleaned ones

    meta      = data.get("metadata", {}) or {}
    reasoning = data.get("reasoning", {}) or {}
    decision  = data.get("decision",  {}) or {}
    case_id   = data.get("case_id", "")
    case_type = meta.get("case_type", "")
    outcome   = decision.get("outcome", "")

    # ── 1. Judges ────────────────────────────────────────────────────────────
    raw_judges   = meta.get("judges", []) or []
    valid_judges = [j for j in raw_judges if is_valid_judge_name(j)]
    out.setdefault("metadata", {}).update({
        "judges_cleaned": [
            {"name": j, "confidence": judge_confidence(j)} for j in valid_judges
        ],
        "has_judge_data": len(valid_judges) > 0,
        "judges_raw":     raw_judges,           # kept for audit
    })

    # ── 2. Statutes ───────────────────────────────────────────────────────────
    principles      = reasoning.get("principles", []) or []
    # Widened context: Act names are often mentioned in `issue` or `facts`
    # rather than `principles` alone — this was checked against the 10k-case
    # diagnostic sample before rolling out (see statute_diagnostic.py).
    statute_context_text = " ".join([
        " ".join(principles),
        data.get("issue", "") or "",
        " ".join(data.get("facts", []) or []),
        reasoning.get("summary", "") or "",
    ])
    raw_statutes    = reasoning.get("statutes", []) or []

    out.setdefault("reasoning", {})["statutes_cleaned"] = (
        normalize_statutes_for_case(raw_statutes, statute_context_text, case_type)
    )

    # ── 3. Citations ──────────────────────────────────────────────────────────
    raw_citations = data.get("citations", []) or []
    out["citations_cleaned"] = [
        {"citation": c, "citation_type": classify_citation(c)}
        for c in raw_citations
        if c and isinstance(c, str)
    ]

    # ── 4. Legal concepts (enriched) ──────────────────────────────────────────
    out["legal_concepts_cleaned"] = enrich_concepts(
        existing          = data.get("legal_concepts") or [],
        principles        = principles,
        reasoning_summary = reasoning.get("summary") or "",
        decision_details  = decision.get("details") or "",
        outcome_reasoning = decision.get("outcome_reasoning") or "",
        case_summary      = data.get("summary") or "",
    )

    # ── 5. Parties ────────────────────────────────────────────────────────────
    parties = data.get("parties", {}) or {}
    cleaned_parties = {}
    for role in ("petitioner", "respondent"):
        name = parties.get(role)
        if name:
            cleaned_parties[role] = {
                "name":             name,
                "name_normalized":  normalize_party_name(name),
                "outcome_for_party": outcome_for_party(outcome, role) if outcome else None,
            }
    out["parties_cleaned"] = cleaned_parties

    # ── 6. Arguments with IDs ─────────────────────────────────────────────────
    out["arguments_with_ids"] = build_argument_nodes(
        case_id        = case_id,
        petitioner_args = data.get("petitioner_arguments", []) or [],
        respondent_args = data.get("respondent_arguments", []) or [],
    )

    # ── 7. Temporal year (always populated) ───────────────────────────────────
    out["temporal_year"] = data.get("year")

    # ── Quality flag ──────────────────────────────────────────────────────────
    out["quality_flag"] = (
        "low_confidence"
        if data.get("extraction_method") == "regex_fallback"
        else "standard"
    )

    return out


# ─────────────────────────────────────────────────────────────────────────────
# RUNNER
# ─────────────────────────────────────────────────────────────────────────────

def run(input_dir: str, output_dir: str, sample_size: int | None):
    os.makedirs(output_dir, exist_ok=True)
    done = load_checkpoint(output_dir)

    files = [f for f in os.listdir(input_dir) if f.endswith('.json')]
    if sample_size and sample_size < len(files):
        import random
        random.seed(42)
        files = random.sample(files, sample_size)

    to_process = [f for f in files if f not in done]
    print(f"Total files   : {len(files)}")
    print(f"Already done  : {len(done)}")
    print(f"To process    : {len(to_process)}")

    errors = []
    for i, fname in enumerate(to_process, 1):
        try:
            with open(os.path.join(input_dir, fname), encoding='utf-8') as fh:
                data = json.load(fh)
            cleaned = clean_case(data)
            with open(os.path.join(output_dir, fname), 'w', encoding='utf-8') as fh:
                json.dump(cleaned, fh, ensure_ascii=False, indent=2)
            done.add(fname)
        except Exception as e:
            errors.append((fname, str(e)))

        if i % 500 == 0:
            save_checkpoint(output_dir, done)
            print(f"  ...{i}/{len(to_process)} processed, checkpoint saved")

    save_checkpoint(output_dir, done)
    print(f"\nDone. {len(done)} total cleaned cases in {output_dir}")

    if errors:
        print(f"\n{len(errors)} errors (first 10):")
        for fname, err in errors[:10]:
            print(f"  {fname}: {err}")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean MERGED_fact_layer_final JSONs before Neo4j population"
    )
    parser.add_argument("input_dir",  help="Path to MERGED_fact_layer_final")
    parser.add_argument("output_dir", help="Path to write cleaned JSONs")
    parser.add_argument("--sample", type=int, default=None,
                        help="Process only N random files (for testing)")
    args = parser.parse_args()
    run(args.input_dir, args.output_dir, args.sample)
