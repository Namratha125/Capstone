"""populate_kg_v2.py — load CLEANED_v2 (output of clean_fact_layer_v2.py) into Neo4j.
Schema: Case, Statute, Topic, Party, LegalConcept, Argument. No Judge/DECIDED_BY (removed from v_n by design).
All writes MERGE (idempotent). Run stages separately:  python -u populate_kg_v2.py --folder F --uri U --user neo4j --password P --stage nodes
--dry-run builds every row set and prints counts without touching Neo4j (use before the real run)."""
import argparse, json, os, re, sys, time
from collections import defaultdict, Counter
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kg_v2_utils import load_vocab, concept_display, slug

BATCH = 500

def chunks(lst, n, label=""):
    total = (len(lst) + n - 1) // n
    for i in range(0, len(lst), n):
        if label and (i // n) % 20 == 0:
            print(f"    {label}: batch {i // n + 1}/{total}", flush=True)
        yield lst[i:i + n]

class Dry:
    def __init__(self): self.rows = Counter()
    def run(self, cql, rows=None, **kw):
        if rows is not None: self.rows[cql.strip().split("\n")[1][:48]] += len(rows)

def load_cases(folder, sample=None):
    cases = []
    for f in sorted(Path(folder).glob("*.json")):
        if f.name.startswith("_") or f.name == "done_keys.json": continue
        try: d = json.loads(f.read_text(encoding="utf-8"))
        except Exception: continue
        if isinstance(d, dict) and d.get("case_id") and "statutes_clean" in d: cases.append(d)
    if sample: cases = cases[:sample]
    print(f"  Loaded {len(cases)} cleaned cases"); return cases

CONSTRAINTS = [
 "CREATE CONSTRAINT unique_case IF NOT EXISTS FOR (n:Case) REQUIRE n.case_id IS UNIQUE",
 "CREATE CONSTRAINT unique_statute IF NOT EXISTS FOR (n:Statute) REQUIRE n.statute_id IS UNIQUE",
 "CREATE CONSTRAINT unique_concept IF NOT EXISTS FOR (n:LegalConcept) REQUIRE n.concept_id IS UNIQUE",
 "CREATE CONSTRAINT unique_party IF NOT EXISTS FOR (n:Party) REQUIRE n.party_id IS UNIQUE",
 "CREATE CONSTRAINT unique_topic IF NOT EXISTS FOR (n:Topic) REQUIRE n.topic_id IS UNIQUE",
 "CREATE CONSTRAINT unique_argument IF NOT EXISTS FOR (n:Argument) REQUIRE n.argument_id IS UNIQUE",
 "CREATE INDEX idx_case_year IF NOT EXISTS FOR (n:Case) ON (n.year)",
 "CREATE INDEX idx_case_outcome IF NOT EXISTS FOR (n:Case) ON (n.outcome)",
 "CREATE INDEX idx_case_title IF NOT EXISTS FOR (n:Case) ON (n.title)",
 "CREATE INDEX idx_statute_act IF NOT EXISTS FOR (n:Statute) ON (n.act_name)",
]
Q_CASE = """
UNWIND $rows AS r
MERGE (c:Case {case_id: r.case_id})
SET c.title=r.title, c.year=r.year, c.filename=r.filename, c.court=r.court, c.date=r.date, c.case_type=r.case_type,
    c.case_type_norm=r.case_type_norm, c.outcome=r.outcome, c.outcome_reasoning=r.outcome_reasoning, c.decision_details=r.decision_details,
    c.issue=r.issue, c.reasoning_summary=r.reasoning_summary, c.case_summary=r.case_summary, c.extraction_method=r.extraction_method,
    c.quality_flags=r.quality_flags"""
Q_STATUTE = """
UNWIND $rows AS r
MERGE (s:Statute {statute_id: r.statute_id})
SET s.act_name=r.act_name, s.section=r.section, s.statute_type=r.kind, s.act_resolved=r.resolved"""
Q_TOPIC = "\nUNWIND $rows AS r\nMERGE (t:Topic {topic_id: r.topic_id}) SET t.name=r.name"
Q_PARTY = "\nUNWIND $rows AS r\nMERGE (p:Party {party_id: r.party_id}) SET p.name=r.name"
Q_CONCEPT = "\nUNWIND $rows AS r\nMERGE (lc:LegalConcept {concept_id: r.concept_id}) SET lc.name=r.name"
Q_ARG = "\nUNWIND $rows AS r\nMERGE (a:Argument {argument_id: r.argument_id}) SET a.text=r.text, a.side=r.side, a.court_accepted=r.court_accepted"
Q_INVOLVES = """
UNWIND $rows AS r
MATCH (c:Case {case_id:r.case_id}) MATCH (s:Statute {statute_id:r.statute_id})
MERGE (c)-[rel:INVOLVES {statute_id:r.statute_id}]->(s) SET rel.derived_parent=r.derived_parent"""
Q_RELATES = "\nUNWIND $rows AS r\nMATCH (c:Case {case_id:r.case_id}) MATCH (t:Topic {topic_id:r.topic_id})\nMERGE (c)-[:RELATES_TO]->(t)"
Q_HASPARTY = """
UNWIND $rows AS r
MATCH (c:Case {case_id:r.case_id}) MATCH (p:Party {party_id:r.party_id})
MERGE (c)-[rel:HAS_PARTY {party_id:r.party_id, role:r.role}]->(p) SET rel.outcome_for_party=r.outcome_for_party"""
Q_MAKES = "\nUNWIND $rows AS r\nMATCH (c:Case {case_id:r.case_id}) MATCH (a:Argument {argument_id:r.argument_id})\nMERGE (c)-[rel:MAKES_ARGUMENT {argument_id:r.argument_id}]->(a)"
Q_CONCEPTREL = "\nUNWIND $rows AS r\nMATCH (c:Case {case_id:r.case_id}) MATCH (lc:LegalConcept {concept_id:r.concept_id})\nMERGE (c)-[rel:APPLIES_CONCEPT {concept_id:r.concept_id}]->(lc) SET rel.status='applied'"
Q_CITES = """
UNWIND $rows AS r
MATCH (s:Case {case_id:r.src_id}) MATCH (t:Case {case_id:r.tgt_id})
MERGE (s)-[rel:CITES {tgt_id:r.tgt_id}]->(t) SET rel.citation_raw=r.citation_raw, rel.match_score=r.score, rel.match_method=r.method"""

def pid(name): return re.sub(r"_+", "_", re.sub(r"[^a-z0-9_]", "_", name[:60])).strip("_")

def write(session, cql, rows, label):
    for b in chunks(rows, BATCH, label): session.run(cql, rows=b)
    print(f"  {label}: {len(rows)}")

def stage_nodes(session, cases, vocab):
    print("\n── nodes ──")
    write(session, Q_CASE, [{
        "case_id": d["case_id"], "title": d.get("title"), "year": d.get("year"), "filename": d.get("filename"),
        "court": (d.get("metadata") or {}).get("court"), "date": (d.get("metadata") or {}).get("date"),
        "case_type": (d.get("metadata") or {}).get("case_type"), "case_type_norm": d.get("case_type_norm"),
        "outcome": (d.get("decision") or {}).get("outcome"), "outcome_reasoning": (d.get("decision") or {}).get("outcome_reasoning"),
        "decision_details": (d.get("decision") or {}).get("details"), "issue": d.get("issue"),
        "reasoning_summary": (d.get("reasoning") or {}).get("summary"), "case_summary": d.get("summary"),
        "extraction_method": d.get("extraction_method"), "quality_flags": d.get("quality_flags", [])} for d in cases], "Case")
    st = {}
    for d in cases:
        for s in d["statutes_clean"]: st.setdefault(s["statute_id"], {k: s.get(k) for k in ("statute_id", "act_name", "section", "kind", "resolved")})
    write(session, Q_STATUTE, list(st.values()), "Statute")
    tp = {d["case_type_norm"]: {"topic_id": d["case_type_norm"], "name": d["case_type_norm"]} for d in cases}
    write(session, Q_TOPIC, list(tp.values()), "Topic")
    pt = {}
    for d in cases:
        for p in d["parties_clean"].values():
            n = p.get("name_normalized") or p["name"]
            if n and pid(n): pt[pid(n)] = {"party_id": pid(n), "name": n}
    write(session, Q_PARTY, list(pt.values()), "Party")
    write(session, Q_CONCEPT, [{"concept_id": c, "name": concept_display(c)} for c in sorted(vocab)], "LegalConcept (all vocab terms)")
    write(session, Q_ARG, [a for d in cases for a in d["arguments_clean"]], "Argument")

def stage_rels(session, cases, vocab):
    print("\n── rels ──")
    inv, rel, par, mk, cn = [], [], [], [], []; unk = Counter()
    for d in cases:
        c = d["case_id"]
        inv += [{"case_id": c, "statute_id": s["statute_id"], "derived_parent": bool(s.get("derived_parent"))} for s in d["statutes_clean"]]
        rel.append({"case_id": c, "topic_id": d["case_type_norm"]})
        for role, p in d["parties_clean"].items():
            n = p.get("name_normalized") or p["name"]
            if n and pid(n): par.append({"case_id": c, "party_id": pid(n), "role": role, "outcome_for_party": p.get("outcome_for_party")})
        mk += [{"case_id": c, "argument_id": a["argument_id"]} for a in d["arguments_clean"]]
        for k in d["concepts_clean"]:
            if k in vocab: cn.append({"case_id": c, "concept_id": k})
            else: unk[k] += 1
    if unk: print("  [WARN] out-of-vocab concepts skipped:", dict(unk))
    for q, rows, lab in ((Q_INVOLVES, inv, "INVOLVES"), (Q_RELATES, rel, "RELATES_TO"), (Q_HASPARTY, par, "HAS_PARTY"), (Q_MAKES, mk, "MAKES_ARGUMENT"), (Q_CONCEPTREL, cn, "APPLIES_CONCEPT")):
        write(session, q, rows, lab)

# ── citations: name match against Case.title, with coverage guard ──
STOP = {"state", "union", "india", "and", "the", "of", "ors", "anr", "others", "another", "ltd", "pvt", "co", "m", "s", "vs", "v", "versus", "dead", "lrs", "by", "through", "rep", "etc"}
def toks(s): return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if len(w) >= 2 and w not in STOP}

def stage_citations(session, cases, min_jaccard=0.85, min_tokens=3):
    print("\n── citations ──")
    by_tok = defaultdict(set); tt = {}; yr = {d['case_id']: d.get('year') or 0 for d in cases}
    for d in cases:
        t = toks(d.get("title") or ""); tt[d["case_id"]] = t
        for w in t: by_tok[w].add(d["case_id"])
    rows, st = [], Counter()
    for d in cases:
        for e in d.get("citations_clean", []):
            if e["citation_type"] != "named":
                st["skipped_" + e["citation_type"]] += 1; continue
            ct = toks(e["case_name"] or "")
            if len(ct) < min_tokens: st["name_too_generic"] += 1; continue
            cand = Counter(c for w in ct for c in by_tok.get(w, ()) if c != d["case_id"])
            best = None
            for c, n in cand.most_common(8):
                if yr[c] > yr[d['case_id']]: st['rejected_future_target'] += 1; continue   # a case cannot cite a later judgment
                j = len(ct & tt[c]) / len(ct | tt[c])
                if j >= min_jaccard and (best is None or j > best[1]): best = (c, j)
            if best: rows.append({"src_id": d["case_id"], "tgt_id": best[0], "citation_raw": e["citation"], "score": round(best[1], 3), "method": "name_jaccard"}); st["resolved"] += 1
            else: st["unresolved_named"] += 1
    write(session, Q_CITES, rows, "CITES"); print("  ", dict(st))
    print("  NOTE: chunk-only graph resolves only citations whose target is in the loaded set; hand-check ~50 edges (match_score is stored).")

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--folder", required=True)
    ap.add_argument("--uri", default=os.environ.get("NEO4J_URI")); ap.add_argument("--user", default="e600e96a")
    ap.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""))
    ap.add_argument("--stage", default="all", choices=["all", "constraints", "nodes", "rels", "citations", "validate"])
    ap.add_argument("--sample", type=int); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(); vocab = load_vocab(); cases = load_cases(a.folder, a.sample)
    if a.dry_run: session = Dry(); ctx = None
    else:
        from neo4j import GraphDatabase
        drv = GraphDatabase.driver(a.uri, auth=(a.user, a.password)); drv.verify_connectivity(); ctx = drv.session(); session = ctx   # user must be 'neo4j'
    if a.stage in ("all", "constraints") and not a.dry_run:
        for q in CONSTRAINTS: session.run(q)
    if a.stage in ("all", "nodes"): stage_nodes(session, cases, vocab)
    if a.stage in ("all", "rels"): stage_rels(session, cases, vocab)
    if a.stage in ("all", "citations"): stage_citations(session, cases)
    if a.stage in ("all", "validate") and not a.dry_run:
        for lab, q in (("nodes", "MATCH (n) RETURN labels(n)[0] AS l, count(n) AS n ORDER BY n DESC"), ("rels", "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS n ORDER BY n DESC")):
            print(lab, session.run(q).data())
    if ctx: ctx.close()
if __name__ == "__main__": main()
