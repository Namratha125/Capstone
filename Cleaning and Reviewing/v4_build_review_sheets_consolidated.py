"""
build_review_sheets_v4_consolidated.py
========================================
Same input/output structure and category coverage as v3 — every field in
the case JSON still gets reviewed, nothing is dropped. The only change:
list-type categories (judges, facts, arguments, statutes, principles,
legal_concepts, citations) that previously got ONE ROW PER ITEM now get
ONE ROW PER CASE, with all items numbered inside a single cell. `decision`
(previously outcome/details/outcome_reasoning as 3 rows) and `parties`
(previously petitioner/respondent as 2 rows) are also collapsed to 1 row
each.

Result: exactly 13 rows per case, every time — regardless of how many
facts or statutes a given case has. For 30 cases that's 390 rows instead
of 830, and the row count no longer explodes for a case that happens to
have a long facts list or 15 statute citations.

REAL TRADEOFF, worth knowing before you use this:
A single verdict cell can no longer say "facts 1, 2, 4 are fine but fact 3
is wrong" — one verdict now covers the whole numbered list. This is why
each cell uses a numbered list (1. 2. 3. ...) rather than a comma-blob:
tell your reviewer to use the numbers when using "partially_correct" +
a comment like "item 3 is inaccurate" so you don't lose that granularity
entirely, just make it a comment instead of a separate row.

Everything else — input folder structure, natural sort, PEOPLE list,
scoring function — is unchanged from v3.
"""

# ── CELL A: Config ────────────────────────────────────────────────────────────
import json, os, csv, glob, re
from collections import Counter
import pandas as pd

BASE_DIR   = "/content/drive/MyDrive/reviewer_packages"   # root with Person_1 … Person_5
OUTPUT_DIR = "/content/drive/MyDrive/review_sheets"        # where CSVs land

PEOPLE = ["Person_1", "Person_2", "Person_3", "Person_4", "Person_5"]

os.makedirs(OUTPUT_DIR, exist_ok=True)
print("✅ Config set")


# ── CELL B: Core helpers ──────────────────────────────────────────────────────

FIELDNAMES = [
    "case_id",
    "case_type",       # edge | regular
    "case_folder",     # e.g. case_1
    "title",
    "year",
    "category",        # judges | parties | issue | facts | petitioner_arguments |
                        # respondent_arguments | statutes | principles |
                        # reasoning_summary | decision | legal_concepts |
                        # citations | summary
    "sub_category",    # short label describing what's consolidated in this row
    "content_to_review",   # THE actual text/value the reviewer judges —
                            # numbered list (1. ... 2. ... ) when there are
                            # multiple items, so comments can reference "item 3"
    "reviewer_verdict (correct / incorrect / partially_correct / uncertain)",
    "reviewer_comment",
]

VERDICT_COL = FIELDNAMES[-2]


def _natural_key(folder_name: str):
    """case_2 < case_9 < case_10  (sorts by the number inside the name)."""
    m = re.search(r"(\d+)", folder_name)
    return (int(m.group(1)) if m else 0, folder_name)


def _row(base, category, sub_category, content):
    r = dict(base)
    r["category"] = category
    r["sub_category"] = sub_category
    r["content_to_review"] = (content or "").strip() if isinstance(content, str) else content
    return r


def _numbered(items: list) -> str:
    """Join a list into '1. x\n2. y\n...' so reviewer comments can reference
    a specific item number instead of needing a separate row per item."""
    items = [str(i).strip() for i in items if i is not None and str(i).strip()]
    if not items:
        return "(none extracted)"
    return "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


# ─── Row builders — one CONSOLIDATED row per category, in review order ───────

def _judges_row(data, base):
    # Only judges the pipeline KEPT are reviewed (same as v3 — rejected
    # names have nothing to verify since the pipeline already discarded
    # them). NOTE: this means a judge WRONGLY rejected is invisible to
    # the reviewer either way, in v3 or here — worth flagging as a known
    # limitation in your paper rather than something this change caused.
    meta = data.get("metadata") or {}
    names = [j.get("name", "") for j in (meta.get("judges_cleaned") or [])]
    return [_row(base, "judges", "all_kept_judges", _numbered(names))]


def _parties_row(data, base):
    cleaned = data.get("parties_cleaned") or {}
    raw = data.get("parties") or {}
    lines = []
    for role in ("petitioner", "respondent"):
        c = cleaned.get(role)
        if c:
            name, norm = c.get("name", ""), c.get("name_normalized", "")
            lines.append(f"{role.title()}: {name}" if name == norm
                         else f"{role.title()}: {name}  →  normalized: {norm}")
        else:
            lines.append(f"{role.title()}: {raw.get(role, '')}")
    return [_row(base, "parties", "petitioner_and_respondent", "\n".join(lines))]


def _issue_row(data, base):
    issue = (data.get("issue") or "").strip()
    return [_row(base, "issue", "legal_question", issue)] if issue else []


def _facts_row(data, base):
    return [_row(base, "facts", "all_facts", _numbered(data.get("facts") or []))]


def _arguments_row(data, base, side):
    with_ids = [a for a in (data.get("arguments_with_ids") or []) if a.get("side") == side]
    items = [a.get("text", "") for a in with_ids] if with_ids else \
            [str(a) for a in (data.get(f"{side}_arguments") or [])]
    return [_row(base, f"{side}_arguments", f"all_{side}_arguments", _numbered(items))]


def _statutes_row(data, base):
    reasoning = data.get("reasoning") or {}
    cleaned = reasoning.get("statutes_cleaned") or []
    lines = []
    if cleaned:
        for s in cleaned:
            status = "plausible" if s.get("plausible", True) else "IMPLAUSIBLE"
            extra = (f" (act resolved: {s.get('act_name')})"
                     if s.get("plausible") and s.get("act_resolved") else "")
            lines.append(f"{s.get('statute_id', '')} [{status}]{extra}")
    else:
        lines = [str(s) for s in reasoning.get("statutes") or []]
    return [_row(base, "statutes", "all_statutes", _numbered(lines))]


def _principles_row(data, base):
    reasoning = data.get("reasoning") or {}
    return [_row(base, "principles", "all_principles", _numbered(reasoning.get("principles") or []))]


def _reasoning_summary_row(data, base):
    reasoning = data.get("reasoning") or {}
    s = (reasoning.get("summary") or "").strip()
    return [_row(base, "reasoning_summary", "summary", s)] if s else []


def _decision_row(data, base):
    decision = data.get("decision") or {}
    parts = []
    if decision.get("outcome"):
        parts.append(f"Outcome: {decision['outcome']}")
    if decision.get("details"):
        parts.append(f"Details: {decision['details']}")
    if decision.get("outcome_reasoning"):
        parts.append(f"Reasoning: {decision['outcome_reasoning']}")
    return [_row(base, "decision", "full_decision", "\n".join(parts))] if parts else []


def _legal_concepts_row(data, base):
    original = list(dict.fromkeys(data.get("legal_concepts") or []))
    cleaned = list(dict.fromkeys(data.get("legal_concepts_cleaned") or []))
    original_set, cleaned_set = set(original), set(cleaned)
    lines = []
    for c in cleaned:
        tag = "original" if c in original_set else "ADDED_BY_ENRICHMENT"
        lines.append(f"{c} [{tag}]")
    for c in original:
        if c not in cleaned_set:
            lines.append(f"{c} [REMOVED]")
    return [_row(base, "legal_concepts", "all_concepts", _numbered(lines))]


def _citations_row(data, base):
    cleaned = data.get("citations_cleaned") or []
    if cleaned:
        lines = [f"{c.get('citation', '')} [{c.get('citation_type', 'unknown')}]" for c in cleaned]
    else:
        lines = [str(c) for c in data.get("citations") or []]
    return [_row(base, "citations", "all_citations", _numbered(lines))]


def _summary_row(data, base):
    s = (data.get("summary") or "").strip()
    return [_row(base, "summary", "case_summary", s)] if s else []


# ─── Master row builder for one case — FIXED ORDER, exactly 13 rows max ──────

def rows_for_case(json_path: str, case_type: str, case_folder: str) -> list[dict]:
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠ Could not read {json_path}: {e}")
        return []

    base = {
        "case_id": data.get("case_id", "UNKNOWN"),
        "case_type": case_type,
        "case_folder": case_folder,
        "title": data.get("title", ""),
        "year": data.get("year", ""),
        "category": "",
        "sub_category": "",
        "content_to_review": "",
        VERDICT_COL: "",     # ← reviewer fills
        "reviewer_comment": "",   # ← reviewer fills
    }

    rows = []
    rows += _judges_row(data, base)
    rows += _parties_row(data, base)
    rows += _issue_row(data, base)
    rows += _facts_row(data, base)
    rows += _arguments_row(data, base, "petitioner")
    rows += _arguments_row(data, base, "respondent")
    rows += _statutes_row(data, base)
    rows += _principles_row(data, base)
    rows += _reasoning_summary_row(data, base)
    rows += _decision_row(data, base)
    rows += _legal_concepts_row(data, base)
    rows += _citations_row(data, base)
    rows += _summary_row(data, base)
    return rows


# ─── Load all cases for one person, in natural (non-jumbled) order ───────────

def load_person_cases(person: str) -> list[dict]:
    person_dir = os.path.join(BASE_DIR, person)
    cases = []

    for case_type, folder_name in (("edge", "edge_cases"), ("regular", "regular_cases")):
        type_dir = os.path.join(person_dir, folder_name)
        if not os.path.isdir(type_dir):
            print(f"  ⚠ {person}: folder not found — {type_dir}")
            continue

        case_folders = sorted(os.listdir(type_dir), key=_natural_key)
        for case_folder in case_folders:
            json_path = os.path.join(type_dir, case_folder, "case.json")
            if not os.path.isfile(json_path):
                print(f"  ⚠ {person}/{folder_name}/{case_folder}: no case.json found")
                continue
            cases.append({
                "json_path": json_path,
                "case_type": case_type,
                "case_folder": case_folder,
            })

    return cases


# ─── Build one CSV per person ─────────────────────────────────────────────────

def build_person_sheet(person: str) -> str:
    print(f"\n{'─'*55}")
    print(f"Building sheet for {person}...")

    cases = load_person_cases(person)
    print(f"  Found {len(cases)} cases  "
          f"({sum(1 for c in cases if c['case_type']=='edge')} edge, "
          f"{sum(1 for c in cases if c['case_type']=='regular')} regular)")

    all_rows = []
    for c in cases:
        all_rows.extend(
            rows_for_case(c["json_path"], c["case_type"], c["case_folder"])
        )

    out_path = os.path.join(OUTPUT_DIR, f"{person}_review_sheet.csv")
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(all_rows)

    counts = Counter(r["category"] for r in all_rows)
    print(f"  Wrote {len(all_rows):,} review rows ({len(cases)} cases × up to 13) → {out_path}")
    print(f"  Category breakdown:")
    for cat, n in sorted(counts.items()):
        print(f"    {cat:22s} {n:4d} rows")

    return out_path


def build_all_review_sheets():
    print("=" * 55)
    print("BUILDING CONSOLIDATED REVIEW SHEETS FOR ALL REVIEWERS")
    print("=" * 55)
    print(f"Input:  {BASE_DIR}")
    print(f"Output: {OUTPUT_DIR}")

    written = []
    for person in PEOPLE:
        if not os.path.isdir(os.path.join(BASE_DIR, person)):
            print(f"\n⚠ {person}: folder not found — skipping")
            continue
        written.append((person, build_person_sheet(person)))

    print(f"\n{'='*55}")
    print(f"✅ Done — {len(written)} review sheets written:")
    for person, path in written:
        print(f"  {person} → {path}")
    print(f"\nSend each person ONLY their own CSV.")
    print(f"They fill '{VERDICT_COL}' and optionally 'reviewer_comment'.")
    print(f"For 'partially_correct', ask them to reference the item number")
    print(f"from the numbered list (e.g. 'item 3 is inaccurate') in the comment.")
    print(f"Run score_reviews() after all sheets are returned.")


# ─── CELL C: Scoring — run after all sheets are returned ─────────────────────
# Unchanged from v3 — category names are identical, so scoring works the
# same way even though each category is now 1 row/case instead of N rows/case.
# The only difference: "accuracy_%" per category now reflects agreement on
# the WHOLE consolidated list per case, not per individual item — a coarser
# but much less burdensome signal. Mention this granularity change explicitly
# if you report these numbers in your paper.

def score_reviews(completed_sheets_dir: str = None):
    search_dir = completed_sheets_dir or OUTPUT_DIR
    sheet_paths = glob.glob(os.path.join(search_dir, "*_review_sheet.csv"))
    if not sheet_paths:
        print(f"⚠ No review sheet CSVs found in {search_dir}")
        return {}

    print(f"Loading {len(sheet_paths)} completed review sheets...")
    all_dfs = []
    for path in sheet_paths:
        person = os.path.basename(path).replace("_review_sheet.csv", "")
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
        df["person"] = person
        all_dfs.append(df)
        filled = df[VERDICT_COL].notna() & (df[VERDICT_COL].str.strip() != "")
        print(f"  {person}: {len(df):,} rows | {filled.sum():,} verdicts filled ({filled.mean()*100:.1f}%)")

    combined = pd.concat(all_dfs, ignore_index=True)
    combined["verdict_clean"] = (
        combined[VERDICT_COL].fillna("").str.strip().str.lower().replace({"": "unfilled"})
    )
    reviewed = combined[combined["verdict_clean"] != "unfilled"].copy()
    print(f"\n📊 Total filled verdicts: {len(reviewed):,} / {len(combined):,}")

    def accuracy_table(df):
        out = []
        for cat, grp in df.groupby("category"):
            total = len(grp)
            correct = (grp["verdict_clean"] == "correct").sum()
            partial = (grp["verdict_clean"] == "partially_correct").sum()
            incorrect = (grp["verdict_clean"] == "incorrect").sum()
            uncertain = (grp["verdict_clean"] == "uncertain").sum()
            out.append({
                "category": cat, "total": total, "correct": correct,
                "partially_correct": partial, "incorrect": incorrect,
                "uncertain": uncertain,
                "accuracy_%": round(correct / total * 100, 1) if total else 0,
            })
        return pd.DataFrame(out).sort_values("category")

    overall_acc = accuracy_table(reviewed)
    print("\n" + "="*55 + "\nOVERALL ACCURACY BY CATEGORY\n" + "="*55)
    print(overall_acc.to_string(index=False))

    per_person = {}
    print("\n" + "="*55 + "\nPER-REVIEWER ACCURACY BY CATEGORY\n" + "="*55)
    for person, grp in reviewed.groupby("person"):
        tbl = accuracy_table(grp)
        per_person[person] = tbl
        print(f"\n  {person}:")
        print(tbl.to_string(index=False))

    incorrect = reviewed[reviewed["verdict_clean"] == "incorrect"].copy()
    if not incorrect.empty:
        flag_path = os.path.join(search_dir, "flagged_incorrect_decisions.csv")
        incorrect.to_csv(flag_path, index=False, encoding="utf-8-sig")
        print(f"\n⚠ {len(incorrect):,} rows flagged as INCORRECT → {flag_path}")

    summary_path = os.path.join(search_dir, "accuracy_summary.csv")
    overall_acc.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"\n✅ Accuracy summary saved → {summary_path}")

    return {"combined": combined, "reviewed": reviewed, "overall_acc": overall_acc,
            "per_person": per_person, "incorrect": incorrect}


# ═══════════════════════════════════════════════════════════════
# RUN  (paste these as separate Colab cells)
# ═══════════════════════════════════════════════════════════════

# Cell B — generate all 5 sheets
build_all_review_sheets()

# ── Cell C — run this AFTER all sheets are returned ──
# results = score_reviews()
