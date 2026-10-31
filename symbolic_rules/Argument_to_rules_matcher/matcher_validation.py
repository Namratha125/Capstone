"""matcher_validation.py — build a blind labeling sheet from matcher_v2.score() output, then evaluate thresholds.
  sheet, key = make_sheet(recs, arg_text, rules, n=300, n_overlap=60, seed=7)   # write sheet to xlsx for labelers, keep `key` private
  report = evaluate(key, labeled)   # labeled: DataFrame with pair_id,label (yes/no/ambiguous)  [+ label2 for the overlap rows]
Label rule: 'yes' = the PETITIONER argues this pattern in favour of their side (not merely mentions it, not defending the law)."""
import numpy as np, pandas as pd, math

BANDS = [(0.30, 0.40), (0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 1.01)]
def family(rule_id): return rule_id.split("_")[0]          # ART19 / ART20 / ART22 / ART21 / ART32 / ART14

def make_sheet(recs, arg_text, rules, n=300, n_overlap=60, seed=7):
    rng = np.random.default_rng(seed); rmap = {r["rule_id"]: r for r in rules}
    df = pd.DataFrame(recs); df = df[df.similarity_score >= BANDS[0][0]].copy()
    df["band"] = pd.cut(df.similarity_score, [b[0] for b in BANDS] + [BANDS[-1][1]], right=False, labels=range(len(BANDS)))
    df["fam"] = df.rule_id.map(family); per_band = n // len(BANDS); parts = []
    for b in range(len(BANDS)):
        sub = df[df.band == b]
        if sub.empty: continue
        # spread across families: round-robin over families so no article dominates
        fams = list(sub.fam.unique()); take = []
        pools = {f: sub[sub.fam == f].sample(frac=1, random_state=int(rng.integers(1e9))) for f in fams}
        i = 0
        while len(take) < min(per_band, len(sub)) and any(len(p) > i for p in pools.values()):
            for f in fams:
                if len(pools[f]) > i and len(take) < per_band: take.append(pools[f].iloc[i])
            i += 1
        parts.append(pd.DataFrame(take))
    key = pd.concat(parts).drop_duplicates(["argument_id", "rule_id"]).sample(frac=1, random_state=seed).reset_index(drop=True)
    key["pair_id"] = [f"P{i:04d}" for i in range(len(key))]
    key["overlap"] = key.index < n_overlap                      # first n_overlap rows go to BOTH labelers
    sheet = pd.DataFrame({"pair_id": key.pair_id, "rule_pattern": key.rule_id.map(lambda r: rmap[r]["condition_logic"].get("petitioner_argument_pattern")),
                          "rule_test": key.rule_id.map(lambda r: rmap[r]["condition_logic"].get("test")),
                          "argument_text": key.argument_id.map(arg_text), "label": "", "notes": ""})
    return sheet, key[["pair_id", "case_id", "argument_id", "rule_id", "fam", "similarity_score", "keyword_hit", "band", "overlap"]]

def wilson(k, n, z=1.96):
    if n == 0: return (None, None)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round((c - h) / d, 3), round((c + h) / d, 3)

def kappa(a, b):
    a, b = np.array(a), np.array(b); cats = sorted(set(a) | set(b)); po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats); return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0

def evaluate(key, labeled, thresholds=np.arange(0.30, 0.80, 0.05), chosen=None):
    d = key.merge(labeled[["pair_id", "label"] + (["label2"] if "label2" in labeled else [])], on="pair_id")
    out = {}
    if "label2" in d:
        ov = d[d.overlap & d.label.isin(["yes", "no", "ambiguous"]) & d.label2.isin(["yes", "no", "ambiguous"])]
        out["agreement"] = {"n": len(ov), "kappa": kappa(ov.label, ov.label2) if len(ov) else None, "raw": round((ov.label == ov.label2).mean(), 3) if len(ov) else None}
    d = d[d.label.isin(["yes", "no"])].copy(); d["y"] = (d.label == "yes").astype(int)
    out["n_labeled"] = len(d); out["n_ambiguous_dropped"] = int((labeled.label == "ambiguous").sum()); out["positives"] = int(d.y.sum())
    def sweep(x):
        rows = []
        for t in thresholds:
            pr = x.similarity_score >= t; tp = int((x.y & pr).sum()); fp = int((~x.y.astype(bool) & pr).sum()); fn = int((x.y.astype(bool) & ~pr).sum())
            p = tp / (tp + fp) if tp + fp else None; r = tp / (tp + fn) if tp + fn else None
            f1 = 2 * p * r / (p + r) if p and r else None
            rows.append({"threshold": round(float(t), 2), "precision": None if p is None else round(p, 3), "recall": None if r is None else round(r, 3),
                         "f1": None if f1 is None else round(f1, 3), "n_pred": tp + fp, "precision_95ci": wilson(tp, tp + fp)})
        return pd.DataFrame(rows)
    out["overall"] = sweep(d); out["by_family"] = {f: sweep(g) for f, g in d.groupby("fam") if len(g) >= 20}
    out["note"] = ("Sample is stratified by score band, so precision is meaningful but recall is OPTIMISTIC unless you reweight; use it to compare thresholds, not as absolute recall." )
    if chosen is not None: out["chosen"] = out["overall"][out["overall"].threshold == chosen]
    return out
