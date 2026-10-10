"""
statute_diagnostic.py

Quantifies two things needed before you write the Statute node MERGE logic:
  1. What fraction of statute strings are outright implausible (concatenation
     artifacts like Constitution_Art_23512).
  2. Of the AMBIGUOUS ones (bare Section_N with no act name), how many can
     actually be resolved to an act name using reasoning.principles /
     metadata.case_type context — vs. how many will stay ambiguous no
     matter what you do.

This tells you whether "infer the act from principles text" is worth
building as a real NLP step or whether it will only resolve a small
fraction and isn't worth the engineering time relative to other Phase 3
priorities.
"""

import json
import os
import re
import argparse
from collections import defaultdict, Counter

ACT_KEYWORDS = {
    "Indian Penal Code": ["indian penal code", "ipc"],
    "Code of Criminal Procedure": ["criminal procedure", "crpc", "cr.p.c"],
    "Code of Civil Procedure": ["civil procedure", "cpc"],
    "Kerala Judicial Service Rules": ["kerala judicial service"],
    "Evidence Act": ["evidence act"],
    "Contract Act": ["contract act"],
    "Land Reforms Act": ["land reforms"],
    "Tenancy Act": ["tenancy act"],
    "Motor Vehicles Act": ["motor vehicles act"],
    "Companies Act": ["companies act"],
    "Income Tax Act": ["income tax act", "income-tax act"],
    "Land Acquisition Act": ["land acquisition act"],
    "Arms Act": ["arms act"],
    "NDPS Act": ["ndps act", "narcotic drugs"],
    "Negotiable Instruments Act": ["negotiable instruments act"],
    "Industrial Disputes Act": ["industrial disputes act"],
    "Hindu Marriage Act": ["hindu marriage act"],
    "Hindu Succession Act": ["hindu succession act"],
    "Prevention of Corruption Act": ["prevention of corruption"],
    "Consumer Protection Act": ["consumer protection act"],
    "Arbitration Act": ["arbitration act"],
    "Rent Control Act": ["rent control act"],
    "Excise Act": ["excise act", "central excise"],
    "Customs Act": ["customs act"],
    "Representation of the People Act": ["representation of the people"],
    # Extend further as your diagnostic output reveals more acts.
}


def is_plausible_constitution_article(statute_str: str) -> bool:
    m = re.search(r'Art_(\d+)', statute_str)
    if not m:
        return True
    return 1 <= int(m.group(1)) <= 395


def is_plausible_section(statute_str: str) -> bool:
    m = re.search(r'Section_?(\d+)', statute_str)
    if not m:
        return True
    return int(m.group(1)) <= 10000


def infer_act_from_context(statute_str: str, principles_text: str, case_type: str):
    text = (principles_text or "").lower()
    for act, keywords in ACT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return act
    return None  # unresolved


def diagnose(folder: str, sample_size: int | None):
    files = [f for f in os.listdir(folder) if f.endswith('.json')]
    if sample_size and sample_size < len(files):
        import random
        random.seed(42)
        files = random.sample(files, sample_size)

    total_statutes = 0
    implausible = 0
    constitution_arts = 0
    bare_sections = 0
    bare_resolved = 0
    resolved_acts = Counter()
    implausible_examples = []

    for fname in files:
        with open(os.path.join(folder, fname), encoding='utf-8') as fh:
            try:
                data = json.load(fh)
            except Exception:
                continue

        statutes = data.get("reasoning", {}).get("statutes", []) or []
        principles_text = " ".join(data.get("reasoning", {}).get("principles", []) or [])
        case_type = data.get("metadata", {}).get("case_type", "")

        for st in statutes:
            total_statutes += 1
            plausible = is_plausible_constitution_article(st) and is_plausible_section(st)
            if not plausible:
                implausible += 1
                if len(implausible_examples) < 15:
                    implausible_examples.append((fname, st))
                continue

            if 'Art_' in st or 'Constitution' in st:
                constitution_arts += 1
            elif st.startswith('Section'):
                bare_sections += 1
                act = infer_act_from_context(st, principles_text, case_type)
                if act:
                    bare_resolved += 1
                    resolved_acts[act] += 1

    print(f"\n{'='*70}\nStatute diagnostic — {folder} (n_files={len(files)})\n{'='*70}")
    print(f"  Total statute entries:       {total_statutes}")
    print(f"  Implausible (garbage):       {implausible} "
          f"({100*implausible/max(total_statutes,1):.1f}%)")
    print(f"  Constitution articles:       {constitution_arts}")
    print(f"  Bare Section_N (ambiguous):  {bare_sections}")
    if bare_sections:
        print(f"  ...resolvable via context:   {bare_resolved} "
              f"({100*bare_resolved/bare_sections:.1f}%)")
        print(f"  ...resolved to:              {dict(resolved_acts)}")
    if implausible_examples:
        print(f"\n  Sample implausible entries:")
        for fname, st in implausible_examples:
            print(f"    {fname}: {st}")

    print(f"\n{'='*70}")
    if bare_sections and bare_resolved / bare_sections < 0.3:
        print("  VERDICT: context-based act inference resolves <30% of bare")
        print("  Section_N entries with the current keyword vocabulary.")
        print("  Either (a) expand ACT_KEYWORDS substantially using your real")
        print("  corpus's act names, or (b) accept these as domain-tagged-only")
        print("  Statute nodes (case_type as proxy) rather than act-name-tagged,")
        print("  and don't over-invest engineering time here.")
    elif bare_sections:
        print("  VERDICT: context inference resolves a meaningful share —")
        print("  worth implementing as a real preprocessing step.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--sample", type=int, default=None)
    args = parser.parse_args()
    diagnose(args.folder, args.sample)
