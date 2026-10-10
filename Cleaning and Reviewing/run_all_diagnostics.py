"""
run_all_diagnostics.py

Single entry point: runs every diagnostic against your MERGED_fact_layer_final
folder and prints one consolidated report. Run this FIRST, before writing any
Neo4j population code — the output tells you exactly which preprocessing
steps are worth building and which aren't.

Usage:
    python run_all_diagnostics.py /path/to/MERGED_fact_layer_final
    python run_all_diagnostics.py /path/to/MERGED_fact_layer_final --sample 1000

(judge_ner_crossvalidate's json_mode needs `pip install spacy` +
`python -m spacy download en_core_web_sm` first — run separately if spaCy
isn't set up yet; everything else has no extra dependencies.)
"""

import argparse
import importlib

MODULES = [
    ("diagnose_fact_layer", "diagnose"),
    ("statute_diagnostic", "diagnose"),
    ("concept_enrichment_diagnostic", "diagnose"),
    ("party_normalization_diagnostic", "diagnose"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", help="Path to MERGED_fact_layer_final")
    parser.add_argument("--sample", type=int, default=None,
                         help="Random sample size (default: all files — "
                              "use a sample for a quick first pass)")
    parser.add_argument("--skip-ner", action="store_true",
                         help="Skip the spaCy judge cross-validation step "
                              "(useful if spaCy isn't installed yet)")
    args = parser.parse_args()

    for mod_name, func_name in MODULES:
        mod = importlib.import_module(mod_name)
        func = getattr(mod, func_name)
        try:
            func(args.folder, args.sample)
        except Exception as e:
            print(f"\n[!] {mod_name} failed: {e}")

    if not args.skip_ner:
        try:
            ner_mod = importlib.import_module("judge_ner_crossvalidate")
            ner_mod.json_mode_run(args.folder, args.sample or 50)
        except Exception as e:
            print(f"\n[!] judge_ner_crossvalidate failed (likely spaCy not "
                  f"installed — run `pip install spacy && python -m spacy "
                  f"download en_core_web_sm`, or pass --skip-ner): {e}")

    print(f"\n{'='*70}")
    print("ALL DIAGNOSTICS COMPLETE")
    print(f"{'='*70}")
    print("Next step: read each VERDICT line above and decide, per component,")
    print("whether to (a) build the full preprocessing fix, (b) accept the")
    print("field as sparse/low-confidence and move on, or (c) flag it for")
    print("manual curation. Don't build all five fixes reflexively — the")
    print("numbers above tell you which ones actually matter for your corpus.")


if __name__ == "__main__":
    main()
