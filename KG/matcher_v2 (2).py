"""matcher_v2.py — argument -> Rule matcher for the v_n graph (Layer 1 keyword flag + Layer 2 semantic similarity).
Candidate cases per rule come from the rule's own cypher_template (statute filter), so an argument is only scored
against rules whose statutes the case actually cites. Optionally writes (:Argument)-[:MATCHES_RULE]->(:Rule) into Neo4j."""
import json, re, numpy as np

def load_rules(paths):
    rules = []
    for p in paths:
        d = json.load(open(p))
        rs = d["rules"] if "rules" in d else [r for k in ("article_19_rules", "article_20_rules", "article_22_rules") for r in d.get(k, [])]
        for r in rs:
            r = dict(r); r["_file"] = p; rules.append(r)
    ids = [r["rule_id"] for r in rules]
    assert len(ids) == len(set(ids)), "duplicate rule_id"
    return rules

def article_of(rule_id):
    m = re.match(r"ART(\d+)", rule_id); return m.group(1) if m else None

def get_candidates(session, rules):
    """rule_id -> set(case_id), by running the rule's own cypher_template."""
    cand = {}
    for r in rules:
        rows = session.run(r["cypher_template"]).data()
        k = next((k for k in (rows[0] if rows else {}) if "case_id" in k), None)
        cand[r["rule_id"]] = {row[k] for row in rows} if k else set()
    return cand

def pull_args(session, case_ids, min_words=6):
    out = []; ids = sorted(case_ids)
    for i in range(0, len(ids), 2000):
        out += session.run("MATCH (c:Case)-[:MAKES_ARGUMENT]->(a:Argument) WHERE a.side='petitioner' AND a.text IS NOT NULL AND a.text<>'' AND c.case_id IN $ids "
                           "RETURN c.case_id AS case_id, a.argument_id AS argument_id, a.text AS text", ids=ids[i:i + 2000]).data()
    return [a for a in out if len(a["text"].split()) >= min_words]     # drop junk fragments (<6 words)

BARE_ART = re.compile(r"^Constitution_Art_\d+[A-Z]?$")

def tier_a_cases(session, rules):
    """rule_id -> set(case_id) where the case cites a CLAUSE-level statute of the rule (not just the bare article).
    Only possible for rules whose cypher returns matched_statutes (the 28 Art 19/20/22 rules); others -> None."""
    out = {}
    for r in rules:
        rows = session.run(r["cypher_template"]).data()
        if not rows or "matched_statutes" not in rows[0]: out[r["rule_id"]] = None; continue
        out[r["rule_id"]] = {x["c.case_id"] for x in rows if any(not BARE_ART.match(sid) for sid in (x["matched_statutes"] or []))}
    return out

def add_tier(recs, tiers):
    """Adds 'tier': 'A' clause-level cited, 'B' bare-article only, 'U' unknown (rule has no matched_statutes column)."""
    for x in recs:
        t = tiers.get(x["rule_id"]); x["tier"] = "U" if t is None else ("A" if x["case_id"] in t else "B")
    return recs

def keyword_hit(text, rule):
    low = (text or "").lower(); return any(k.lower() in low for k in rule.get("layer1_keywords", []))

def top2_mean(sims):
    s = np.sort(sims, axis=1)
    return s[:, -2:].mean(axis=1) if s.shape[1] >= 2 else s[:, -1]

def score(rules, cand, args, encode):
    """encode(list[str]) -> L2-normalised ndarray. Returns list of per-(argument,rule) dicts for candidate cases only."""
    ex_texts = [e for r in rules for e in r["exemplar_sentences"]]
    ex_emb = encode(ex_texts); off, spans = 0, {}
    for r in rules: n = len(r["exemplar_sentences"]); spans[r["rule_id"]] = (off, off + n); off += n
    arg_emb = encode([a["text"] for a in args]); case_idx = {}
    for i, a in enumerate(args): case_idx.setdefault(a["case_id"], []).append(i)
    recs = []
    for r in rules:
        rid = r["rule_id"]; idx = [i for c in cand[rid] for i in case_idx.get(c, [])]
        if not idx: continue
        s0, s1 = spans[rid]; sims = arg_emb[idx] @ ex_emb[s0:s1].T
        sc, best = top2_mean(sims), sims.argmax(axis=1)
        for j, i in enumerate(idx):
            recs.append({"case_id": args[i]["case_id"], "argument_id": args[i]["argument_id"], "rule_id": rid,
                         "similarity_score": round(float(sc[j]), 4), "keyword_hit": keyword_hit(args[i]["text"], r),
                         "matched_exemplar": r["exemplar_sentences"][int(best[j])]})
    return recs

def select_edges(recs, floor, top_n=2):
    by = {}
    for x in recs:
        if x["similarity_score"] >= floor: by.setdefault((x["case_id"], x["rule_id"]), []).append(x)
    return [x for v in by.values() for x in sorted(v, key=lambda z: -z["similarity_score"])[:top_n]]

Q_RULE = """UNWIND $rows AS r MERGE (n:Rule {rule_id:r.rule_id})
SET n.article=r.article, n.domain=r.domain, n.rule_type=r.rule_type, n.evidence_level=r.evidence_level, n.predicted_outcome_direction=r.direction"""
Q_EDGE = """UNWIND $rows AS r MATCH (a:Argument {argument_id:r.argument_id}) MATCH (n:Rule {rule_id:r.rule_id})
MERGE (a)-[m:MATCHES_RULE]->(n) SET m.similarity_score=r.similarity_score, m.keyword_hit=r.keyword_hit, m.matched_exemplar=r.matched_exemplar, m.case_id=r.case_id, m.threshold=r.threshold"""

def write_graph(session, rules, edges, floor):
    session.run("CREATE CONSTRAINT unique_rule IF NOT EXISTS FOR (n:Rule) REQUIRE n.rule_id IS UNIQUE")
    session.run(Q_RULE, rows=[{"rule_id": r["rule_id"], "article": article_of(r["rule_id"]), "domain": r.get("domain"), "rule_type": r.get("rule_type"),
                               "evidence_level": r.get("evidence_level"), "direction": r.get("predicted_outcome_direction")} for r in rules])
    rows = [dict(e, threshold=floor) for e in edges]
    for i in range(0, len(rows), 500): session.run(Q_EDGE, rows=rows[i:i + 500])
