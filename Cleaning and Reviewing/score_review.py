"""
score_review.py

Takes the review_sheet.csv AFTER a human has filled in 'reviewer_verdict'
(correct / incorrect / uncertain) for each row, and computes per-category
accuracy with a 95% Wilson confidence interval — the number you actually
report in your dissertation's Results chapter, e.g.:

    "Human validation on a stratified sample of N=120 cases (267 atomic
    decisions) found the judge-filtering step 91.2% accurate (95% CI:
    85.6-94.7%, n=136), statute plausibility classification 98.1% accurate
    (n=210), citation type classification 94.3% accurate (n=298)..."

Usage:
    python score_review.py review_sheet_completed.csv
"""

import csv
import argparse
import math
from collections import defaultdict


def wilson_ci(correct: int, n: int, z: float = 1.96):
    """95% Wilson score interval — better than a naive normal approximation
    for small n or accuracy near 0%/100%, both of which happen here."""
    if n == 0:
        return (0.0, 0.0)
    p = correct / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    adj = z * math.sqrt((p * (1 - p) + z**2 / (4 * n)) / n)
    lower = (centre - adj) / denom
    upper = (centre + adj) / denom
    return (max(0.0, lower) * 100, min(1.0, upper) * 100)


def score(csv_path: str):
    rows = []
    with open(csv_path, encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)

    unfilled = [r for r in rows if not r.get("reviewer_verdict", "").strip()]
    filled = [r for r in rows if r.get("reviewer_verdict", "").strip()]

    if unfilled:
        print(f"NOTE: {len(unfilled)}/{len(rows)} rows have no reviewer_verdict "
              f"yet and will be excluded from scoring.\n")

    by_category = defaultdict(lambda: {"correct": 0, "incorrect": 0, "uncertain": 0, "n": 0})
    for r in filled:
        v = r["reviewer_verdict"].strip().lower()
        cat = r["category"]
        by_category[cat]["n"] += 1
        if v.startswith("correct"):
            by_category[cat]["correct"] += 1
        elif v.startswith("incorrect"):
            by_category[cat]["incorrect"] += 1
        elif v.startswith("uncertain"):
            by_category[cat]["uncertain"] += 1
        else:
            print(f"WARNING: unrecognized verdict '{v}' on review_id "
                  f"{r.get('review_id')} — expected correct/incorrect/uncertain")

    n_cases = len(set(r["case_id"] for r in filled))

    print(f"{'='*72}")
    print(f"Human-in-the-loop validation results")
    print(f"{'='*72}")
    print(f"Cases reviewed: {n_cases}   Decisions reviewed: {len(filled)}\n")

    print(f"{'Category':<12} {'n':>5} {'Correct':>8} {'Incorrect':>10} "
          f"{'Uncertain':>10} {'Accuracy':>10} {'95% CI':>16}")
    print("-" * 72)

    overall_correct, overall_n = 0, 0
    table_rows = []
    for cat, stats in sorted(by_category.items()):
        n = stats["n"]
        # 'uncertain' excluded from the accuracy denominator by default —
        # report it separately since it's a different kind of signal
        # (ambiguous ground truth, not a system error)
        definitive_n = stats["correct"] + stats["incorrect"]
        acc = 100 * stats["correct"] / definitive_n if definitive_n else 0.0
        lo, hi = wilson_ci(stats["correct"], definitive_n)
        print(f"{cat:<12} {n:>5} {stats['correct']:>8} {stats['incorrect']:>10} "
              f"{stats['uncertain']:>10} {acc:>9.1f}% {f'[{lo:.1f}-{hi:.1f}]':>16}")
        overall_correct += stats["correct"]
        overall_n += definitive_n
        table_rows.append((cat, n, acc, lo, hi))

    overall_acc = 100 * overall_correct / overall_n if overall_n else 0.0
    overall_lo, overall_hi = wilson_ci(overall_correct, overall_n)
    print("-" * 72)
    print(f"{'OVERALL':<12} {len(filled):>5} {overall_correct:>8} "
          f"{overall_n - overall_correct:>10} {'':>10} {overall_acc:>9.1f}% "
          f"{f'[{overall_lo:.1f}-{overall_hi:.1f}]':>16}")

    print(f"\n{'='*72}")
    print("Paper-ready sentence (edit as needed):\n")
    print(f'  "Human-in-the-loop validation was conducted on a stratified')
    print(f'  sample of {n_cases} cases ({len(filled)} atomic preprocessing')
    print(f'  decisions), combining random sampling with deliberate')
    print(f'  oversampling of edge-case conditions identified during')
    print(f'  automated diagnostics. Overall decision accuracy was')
    print(f'  {overall_acc:.1f}% (95% CI: {overall_lo:.1f}-{overall_hi:.1f}%). Per-category')
    print(f'  results are reported in Table X.X."')

    print(f"\nMarkdown table for your report:\n")
    print("| Category | n | Accuracy | 95% CI |")
    print("|---|---|---|---|")
    for cat, n, acc, lo, hi in table_rows:
        print(f"| {cat} | {n} | {acc:.1f}% | [{lo:.1f}, {hi:.1f}] |")
    print(f"| **Overall** | {len(filled)} | {overall_acc:.1f}% | [{overall_lo:.1f}, {overall_hi:.1f}] |")

    # Surface incorrect examples for qualitative discussion in the paper
    print(f"\n{'='*72}")
    print("Sample 'incorrect' decisions (useful for your Error Analysis / Limitations section):")
    incorrect_rows = [r for r in filled if r["reviewer_verdict"].strip().lower().startswith("incorrect")]
    for r in incorrect_rows[:15]:
        print(f"  [{r['category']}] case={r['case_id']} "
              f"orig='{r['original_value']}' system='{r['system_decision']}' "
              f"comment='{r.get('reviewer_comment','')}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", help="Path to the completed review sheet")
    args = parser.parse_args()
    score(args.csv_path)
