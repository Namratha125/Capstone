"""clean_fact_layer_v2.py — v_n fact layer -> CLEANED_v2/*.json (no LLM, no judges).
Usage: python clean_fact_layer_v2.py <v_n_dir_or_dirs...> <out_dir> [--sample N]
Writes <out_dir>/_report.json with every counter used in PROJECT_AUDIT.md."""
import json, os, sys, glob, argparse, collections as C
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_v2_utils import *

def clean_case(d, vocab, rep):
    out = dict(d)
    cid = d["case_id"]; dec = d.get("decision") or {}; outcome = dec.get("outcome"); meta = d.get("metadata") or {}
    st, dropped = clean_statutes((d.get("reasoning") or {}).get("statutes"))
    out["statutes_clean"] = st; out["statutes_dropped_bare"] = dropped
    rep["statute_kind"].update(s["kind"] for s in st if not s.get("derived_parent")); rep["bare_dropped"] += len(dropped)
    cites = clean_citations(d.get("citations")); out["citations_clean"] = cites; rep["cite_type"].update(c["citation_type"] for c in cites)
    L = list(dict.fromkeys(d.get("legal_concepts") or []))
    bad = [c for c in L if c not in vocab]; rep["out_of_vocab"].update(bad)
    out["concepts_clean"] = [c for c in L if c in vocab]
    if not out["concepts_clean"]: rep["empty_concepts"] += 1
    out["case_type_norm"] = normalize_case_type(meta.get("case_type"))
    parties = d.get("parties") or {}; pc = {}
    for role in ("petitioner", "respondent"):
        n = parties.get(role)
        if n: pc[role] = {"name": n, "name_normalized": normalize_party_name(n), "outcome_for_party": outcome_for_party(outcome, role)}
    out["parties_clean"] = pc
    out["arguments_clean"] = build_argument_nodes(cid, d.get("petitioner_arguments"), d.get("respondent_arguments"))
    flags = []
    if outcome_conflict(outcome, dec.get("details")): flags.append("outcome_conflict")
    if outcome in (None, "Unknown"): flags.append("outcome_unknown")
    if not d.get("petitioner_arguments") and d.get("respondent_arguments"): flags.append("petitioner_args_missing")
    out["quality_flags"] = flags; rep["flags"].update(flags)
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("paths", nargs="+"); ap.add_argument("--sample", type=int)
    a = ap.parse_args(); *ins, outdir = a.paths
    os.makedirs(outdir, exist_ok=True); vocab = load_vocab()
    files = [f for p in ins for f in glob.glob(os.path.join(p, "*.json"))]
    if a.sample: files = files[: a.sample]
    rep = {"statute_kind": C.Counter(), "cite_type": C.Counter(), "out_of_vocab": C.Counter(), "flags": C.Counter(), "bare_dropped": 0, "empty_concepts": 0}
    seen, n = set(), 0
    for f in sorted(files):
        try: d = json.load(open(f, encoding="utf-8"))
        except Exception: continue
        if not isinstance(d, dict) or "case_id" not in d or d["case_id"] in seen: continue
        seen.add(d["case_id"]); n += 1
        json.dump(clean_case(d, vocab, rep), open(os.path.join(outdir, os.path.basename(f)), "w", encoding="utf-8"), ensure_ascii=False)
    rep = {k: (dict(v) if isinstance(v, C.Counter) else v) for k, v in rep.items()}; rep["cases"] = n
    json.dump(rep, open(os.path.join(outdir, "_report.json"), "w"), indent=2); print(json.dumps(rep, indent=1))
if __name__ == "__main__": main()
