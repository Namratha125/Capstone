"""
populate_kg.py
==============
Reads CLEANED_fact_layer/ (output of transform_fact_layer.py) and populates
a Neo4j Knowledge Graph matching the schema defined in the dissertation
(Chapter 4, Section 4.5).

PREREQUISITES
-------------
    pip install neo4j tqdm

    Neo4j must be running (Desktop / Docker / Aura).
    Set NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD as env vars OR pass via CLI.

USAGE (Colab)
-------------
    # Install
    !pip install -q neo4j tqdm

    # Run (all stages)
    !python populate_kg.py \
        --folder  /content/drive/MyDrive/CLEANED_fact_layer \
        --uri     bolt://localhost:7687 \
        --user    neo4j \
        --password YOUR_PASSWORD

    # Run a specific stage only
    !python populate_kg.py ... --stage nodes
    !python populate_kg.py ... --stage rels
    !python populate_kg.py ... --stage citations
    # (SIMILAR_FACTS is a separate script — see compute_similar_facts.py)

STAGE ORDER
-----------
  1. constraints  — indexes + uniqueness constraints (idempotent)
  2. nodes        — Case, Statute, Topic, LegalConcept, Party, Judge,
                    Argument nodes
  3. rels         — INVOLVES, RELATES_TO, DECIDED_BY, HAS_PARTY,
                    MAKES_ARGUMENT, APPLIES_CONCEPT
  4. citations    — CITES edges (only for citations resolvable to a Case node)
  5. similar      — SIMILAR_FACTS (run compute_similar_facts.py instead;
                    listed here for reference)

All stages are checkpoint-aware: a file (kg_progress.json) tracks which
case_ids have been fully processed for each stage, so a Colab session crash
is recoverable.
"""

import argparse
import json
import os
import re
import sys
import hashlib
import time
from collections import defaultdict
from pathlib import Path

try:
    from neo4j import GraphDatabase, exceptions as neo4j_exc
except ImportError:
    print("neo4j not installed. Run:  pip install neo4j")
    sys.exit(1)

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

BATCH = 500   # nodes per Cypher UNWIND batch — tune down if you hit memory


def _iter(items, desc=""):
    if HAS_TQDM:
        return tqdm(items, desc=desc, unit="case")
    return items


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _load_all_cases(folder: str) -> list[dict]:
    files = sorted(Path(folder).glob("*.json"))
    cases = []
    errors = 0
    skipped = 0
    for f in files:
        if f.name == "done_keys.json":
            skipped += 1
            continue
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "case_id" not in data:
                skipped += 1
                continue
            cases.append(data)
        except Exception:
            errors += 1
    if errors:
        print(f"  [warn] {errors} files failed to parse — skipped")
    if skipped:
        print(f"  [info] {skipped} non-case files skipped (checkpoint etc.)")
    print(f"  Loaded {len(cases)} cleaned case JSONs")
    return cases


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 0 — CONSTRAINTS & INDEXES
# ──────────────────────────────────────────────────────────────────────────────

CONSTRAINTS = [
    # Uniqueness
    "CREATE CONSTRAINT unique_case       IF NOT EXISTS FOR (n:Case)         REQUIRE n.case_id    IS UNIQUE",
    "CREATE CONSTRAINT unique_statute    IF NOT EXISTS FOR (n:Statute)      REQUIRE n.statute_id IS UNIQUE",
    "CREATE CONSTRAINT unique_concept    IF NOT EXISTS FOR (n:LegalConcept) REQUIRE n.concept_id IS UNIQUE",
    "CREATE CONSTRAINT unique_judge      IF NOT EXISTS FOR (n:Judge)        REQUIRE n.judge_id   IS UNIQUE",
    "CREATE CONSTRAINT unique_party      IF NOT EXISTS FOR (n:Party)        REQUIRE n.party_id   IS UNIQUE",
    "CREATE CONSTRAINT unique_topic      IF NOT EXISTS FOR (n:Topic)        REQUIRE n.topic_id   IS UNIQUE",
    "CREATE CONSTRAINT unique_argument   IF NOT EXISTS FOR (n:Argument)     REQUIRE n.argument_id IS UNIQUE",
    # Indexes for common query patterns
    "CREATE INDEX idx_case_year    IF NOT EXISTS FOR (n:Case)    ON (n.year)",
    "CREATE INDEX idx_case_outcome IF NOT EXISTS FOR (n:Case)    ON (n.outcome)",
    "CREATE INDEX idx_statute_act  IF NOT EXISTS FOR (n:Statute) ON (n.act_name)",
    "CREATE INDEX idx_judge_name   IF NOT EXISTS FOR (n:Judge)   ON (n.name)",
]


def run_constraints(session):
    print("\n── Stage 0: Constraints & Indexes ──")
    for cql in CONSTRAINTS:
        try:
            session.run(cql)
        except Exception as e:
            print(f"  [warn] constraint/index skipped: {e}")
    print("  Done.")


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 1 — NODES
# ──────────────────────────────────────────────────────────────────────────────

def _build_case_row(d: dict) -> dict:
    meta     = d.get("metadata", {}) or {}
    decision = d.get("decision", {}) or {}
    reasoning= d.get("reasoning", {}) or {}
    return {
        "case_id":           d.get("case_id"),
        "title":             d.get("title"),
        "year":              d.get("year"),
        "filename":          d.get("filename"),
        "court":             meta.get("court", "Supreme Court of India"),
        "date":              meta.get("date"),
        "bench_strength":    meta.get("bench_strength"),
        "case_type":         meta.get("case_type"),
        "has_judge_data":    meta.get("has_judge_data", False),
        "outcome":           decision.get("outcome"),
        "outcome_reasoning": decision.get("outcome_reasoning"),
        "decision_details":  decision.get("details"),
        "issue":             d.get("issue"),
        "reasoning_summary": reasoning.get("summary"),
        "case_summary":      d.get("summary"),
        "extraction_method": d.get("extraction_method"),
        "quality_flag":      d.get("quality_flag", "standard"),
    }


_MERGE_CASE = """
UNWIND $rows AS r
MERGE (c:Case {case_id: r.case_id})
SET c.title            = r.title,
    c.year             = r.year,
    c.filename         = r.filename,
    c.court            = r.court,
    c.date             = r.date,
    c.bench_strength   = r.bench_strength,
    c.case_type        = r.case_type,
    c.has_judge_data   = r.has_judge_data,
    c.outcome          = r.outcome,
    c.outcome_reasoning= r.outcome_reasoning,
    c.decision_details = r.decision_details,
    c.issue            = r.issue,
    c.reasoning_summary= r.reasoning_summary,
    c.case_summary     = r.case_summary,
    c.extraction_method= r.extraction_method,
    c.quality_flag     = r.quality_flag
"""


def load_case_nodes(session, cases: list[dict]):
    print("\n── Stage 1a: Case nodes ──")
    rows = [_build_case_row(d) for d in cases]
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_CASE, rows=batch)
    print(f"  MERGEd {len(rows)} Case nodes.")


# ── Statute nodes ──────────────────────────────────────────────────────────────

_MERGE_STATUTE = """
UNWIND $rows AS r
MERGE (s:Statute {statute_id: r.statute_id})
SET s.act_name      = r.act_name,
    s.section       = r.section,
    s.statute_type  = r.statute_type,
    s.act_resolved  = r.act_resolved,
    s.domain        = r.domain,
    s.plausible     = r.plausible
"""


def load_statute_nodes(session, cases: list[dict]):
    print("\n── Stage 1b: Statute nodes ──")
    seen = set()
    rows = []
    for d in cases:
        for st in (d.get("reasoning", {}) or {}).get("statutes_cleaned", []) or []:
            if not isinstance(st, dict):
                continue
            sid = st.get("statute_id")
            if sid and sid not in seen:
                seen.add(sid)
                rows.append({
                    "statute_id":   sid,
                    "act_name":     st.get("act_name"),
                    "section":      st.get("section"),
                    "statute_type": st.get("statute_type"),
                    "act_resolved": st.get("act_resolved", False),
                    "domain":       st.get("domain"),
                    "plausible":    st.get("plausible", True),
                })
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_STATUTE, rows=batch)
    print(f"  MERGEd {len(rows)} unique Statute nodes.")


# ── Topic nodes ────────────────────────────────────────────────────────────────

_MERGE_TOPIC = """
UNWIND $rows AS r
MERGE (t:Topic {topic_id: r.topic_id})
SET t.name = r.name
"""


def load_topic_nodes(session, cases: list[dict]):
    print("\n── Stage 1c: Topic nodes ──")
    seen = set()
    rows = []
    for d in cases:
        ct = (d.get("metadata", {}) or {}).get("case_type")
        if ct and ct not in seen:
            seen.add(ct)
            rows.append({"topic_id": ct.lower().replace(" ", "_"), "name": ct})
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_TOPIC, rows=batch)
    print(f"  MERGEd {len(rows)} unique Topic nodes.")


# ── Judge nodes ────────────────────────────────────────────────────────────────

_MERGE_JUDGE = """
UNWIND $rows AS r
MERGE (j:Judge {judge_id: r.judge_id})
SET j.name = r.name
"""


def _make_judge_id(name: str) -> str:
    slug = re.sub(r'[^a-z0-9]', '_', name.lower().strip())
    slug = re.sub(r'_+', '_', slug).strip('_')
    return slug[:60] or hashlib.md5(name.encode()).hexdigest()[:12]


def load_judge_nodes(session, cases: list[dict]):
    print("\n── Stage 1d: Judge nodes ──")
    seen = set()
    rows = []
    for d in cases:
        judges = (d.get("metadata", {}) or {}).get("judges_cleaned", []) or []
        for j in judges:
            name = j.get("name") if isinstance(j, dict) else str(j)
            if not name:
                continue
            jid = _make_judge_id(name)
            if jid not in seen:
                seen.add(jid)
                rows.append({"judge_id": jid, "name": name})
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_JUDGE, rows=batch)
    print(f"  MERGEd {len(rows)} unique Judge nodes.")


# ── Party nodes ────────────────────────────────────────────────────────────────

_MERGE_PARTY = """
UNWIND $rows AS r
MERGE (p:Party {party_id: r.party_id})
SET p.name = r.name
"""


def load_party_nodes(session, cases: list[dict]):
    print("\n── Stage 1e: Party nodes ──")
    seen = set()
    rows = []
    for d in cases:
        parties = d.get("parties_cleaned", {}) or {}
        for role in ("petitioner", "respondent"):
            p = parties.get(role, {}) or {}
            if not isinstance(p, dict):
                continue
            name = p.get("name_normalized") or p.get("name", "")
            if not name:
                continue
            pid = re.sub(r'[^a-z0-9_]', '_', name[:60]).strip('_')
            pid = re.sub(r'_+', '_', pid)
            if pid and pid not in seen:
                seen.add(pid)
                rows.append({"party_id": pid, "name": name})
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_PARTY, rows=batch)
    print(f"  MERGEd {len(rows)} unique Party nodes.")


# ── LegalConcept nodes ─────────────────────────────────────────────────────────

_CONCEPT_DISPLAY = {
    "natural_justice": "Natural Justice",
    "res_judicata": "Res Judicata",
    "mens_rea": "Mens Rea",
    "estoppel": "Estoppel",
    "promissory_estoppel": "Promissory Estoppel",
    "fundamental_rights": "Fundamental Rights",
    "due_process": "Due Process",
    "audi_alteram_partem": "Audi Alteram Partem",
    "burden_of_proof": "Burden of Proof",
    "vicarious_liability": "Vicarious Liability",
    "doctrine_of_merger": "Doctrine of Merger",
    "locus_standi": "Locus Standi",
    "ultra_vires": "Ultra Vires",
    "quasi_judicial": "Quasi-Judicial",
    "arbitration": "Arbitration",
    "stare_decisis": "Stare Decisis",
    "separation_of_powers": "Separation of Powers",
    "rule_of_law": "Rule of Law",
    "judicial_review": "Judicial Review",
    "writ_jurisdiction": "Writ Jurisdiction",
    "rule_against_bias": "Rule Against Bias",
    "double_jeopardy": "Double Jeopardy",
    "right_against_self_incrimination": "Right Against Self-Incrimination",
    "right_to_equality": "Right to Equality",
    "right_to_life": "Right to Life",
    "delegated_legislation": "Delegated Legislation",
    "legitimate_expectation": "Legitimate Expectation",
    "unjust_enrichment": "Unjust Enrichment",
    "force_majeure": "Force Majeure",
    "mala_fides": "Mala Fides",
    "public_interest": "Public Interest",
}


_MERGE_CONCEPT = """
UNWIND $rows AS r
MERGE (lc:LegalConcept {concept_id: r.concept_id})
SET lc.name = r.name
"""


def load_concept_nodes(session, cases: list[dict]):
    print("\n── Stage 1f: LegalConcept nodes ──")
    seen = set()
    rows = []
    for d in cases:
        for cid in (d.get("legal_concepts_cleaned") or []):
            if cid and cid not in seen:
                seen.add(cid)
                rows.append({
                    "concept_id": cid,
                    "name": _CONCEPT_DISPLAY.get(cid,
                                cid.replace("_", " ").title()),
                })
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_CONCEPT, rows=batch)
    print(f"  MERGEd {len(rows)} unique LegalConcept nodes.")


# ── Argument nodes ─────────────────────────────────────────────────────────────

_MERGE_ARGUMENT = """
UNWIND $rows AS r
MERGE (a:Argument {argument_id: r.argument_id})
SET a.text           = r.text,
    a.side           = r.side,
    a.court_accepted = r.court_accepted
"""


def load_argument_nodes(session, cases: list[dict]):
    print("\n── Stage 1g: Argument nodes ──")
    rows = []
    for d in cases:
        for arg in (d.get("arguments_with_ids") or []):
            if not isinstance(arg, dict):
                continue
            rows.append({
                "argument_id":   arg.get("argument_id"),
                "text":          arg.get("text", ""),
                "side":          arg.get("side"),
                "court_accepted": arg.get("court_accepted"),
            })
    for batch in _chunks(rows, BATCH):
        session.run(_MERGE_ARGUMENT, rows=batch)
    print(f"  MERGEd {len(rows)} Argument nodes.")


def stage_nodes(session, cases):
    load_case_nodes(session, cases)
    load_statute_nodes(session, cases)
    load_topic_nodes(session, cases)
    load_judge_nodes(session, cases)
    load_party_nodes(session, cases)
    load_concept_nodes(session, cases)
    load_argument_nodes(session, cases)


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 2 — RELATIONSHIPS (non-citation, non-similarity)
# ──────────────────────────────────────────────────────────────────────────────

_MERGE_INVOLVES = """
UNWIND $rows AS r
MATCH (c:Case    {case_id:    r.case_id})
MATCH (s:Statute {statute_id: r.statute_id})
MERGE (c)-[rel:INVOLVES {statute_id: r.statute_id}]->(s)
SET rel.interpretation = r.interpretation
"""

_MERGE_RELATES_TO = """
UNWIND $rows AS r
MATCH (c:Case  {case_id:  r.case_id})
MATCH (t:Topic {topic_id: r.topic_id})
MERGE (c)-[:RELATES_TO]->(t)
"""

_MERGE_DECIDED_BY = """
UNWIND $rows AS r
MATCH (c:Case  {case_id:  r.case_id})
MATCH (j:Judge {judge_id: r.judge_id})
MERGE (c)-[rel:DECIDED_BY {judge_id: r.judge_id}]->(j)
SET rel.confidence = r.confidence
"""

_MERGE_HAS_PARTY = """
UNWIND $rows AS r
MATCH (c:Case  {case_id:  r.case_id})
MATCH (p:Party {party_id: r.party_id})
MERGE (c)-[rel:HAS_PARTY {party_id: r.party_id}]->(p)
SET rel.role             = r.role,
    rel.outcome_for_party = r.outcome_for_party
"""

_MERGE_MAKES_ARGUMENT = """
UNWIND $rows AS r
MATCH (c:Case     {case_id:     r.case_id})
MATCH (a:Argument {argument_id: r.argument_id})
MERGE (c)-[rel:MAKES_ARGUMENT {argument_id: r.argument_id}]->(a)
SET rel.court_accepted = r.court_accepted
"""

_MERGE_APPLIES_CONCEPT = """
UNWIND $rows AS r
MATCH (c:Case         {case_id:    r.case_id})
MATCH (lc:LegalConcept {concept_id: r.concept_id})
MERGE (c)-[rel:APPLIES_CONCEPT {concept_id: r.concept_id}]->(lc)
SET rel.status = r.status
"""


def stage_rels(session, cases: list[dict]):
    print("\n── Stage 2: Relationships ──")

    involves_rows, relates_rows, decided_rows = [], [], []
    party_rows, arg_rows, concept_rows = [], [], []

    for d in cases:
        cid  = d.get("case_id")
        meta = d.get("metadata", {}) or {}
        dec  = d.get("decision", {}) or {}

        # INVOLVES (Case → Statute)
        for st in (d.get("reasoning", {}) or {}).get("statutes_cleaned", []) or []:
            if isinstance(st, dict) and st.get("statute_id") and st.get("plausible", True):
                involves_rows.append({
                    "case_id":       cid,
                    "statute_id":    st["statute_id"],
                    "interpretation": None,  # set by symbolic reasoning later
                })

        # RELATES_TO (Case → Topic)
        ct = meta.get("case_type")
        if ct:
            relates_rows.append({
                "case_id":  cid,
                "topic_id": ct.lower().replace(" ", "_"),
            })

        # DECIDED_BY (Case → Judge)
        for j in (meta.get("judges_cleaned") or []):
            name = j.get("name") if isinstance(j, dict) else str(j)
            conf = j.get("confidence", "medium") if isinstance(j, dict) else "medium"
            if name:
                decided_rows.append({
                    "case_id":   cid,
                    "judge_id":  _make_judge_id(name),
                    "confidence": conf,
                })

        # HAS_PARTY (Case → Party)
        parties = d.get("parties_cleaned", {}) or {}
        for role in ("petitioner", "respondent"):
            p = parties.get(role, {}) or {}
            if not isinstance(p, dict):
                continue
            name = p.get("name_normalized") or p.get("name", "")
            if not name:
                continue
            pid = re.sub(r'[^a-z0-9_]', '_', name[:60]).strip('_')
            pid = re.sub(r'_+', '_', pid)
            if pid:
                party_rows.append({
                    "case_id":           cid,
                    "party_id":          pid,
                    "role":              role,
                    "outcome_for_party": p.get("outcome_for_party"),
                })

        # MAKES_ARGUMENT (Case → Argument)
        for arg in (d.get("arguments_with_ids") or []):
            if isinstance(arg, dict) and arg.get("argument_id"):
                arg_rows.append({
                    "case_id":       cid,
                    "argument_id":   arg["argument_id"],
                    "court_accepted": arg.get("court_accepted"),
                })

        # APPLIES_CONCEPT (Case → LegalConcept)
        for cpt in (d.get("legal_concepts_cleaned") or []):
            concept_rows.append({
                "case_id":   cid,
                "concept_id": cpt,
                "status":    "applied",   # default; reasoning engine may update
            })

    def _batch_run(cql, rows, label):
        for batch in _chunks(rows, BATCH):
            session.run(cql, rows=batch)
        print(f"  {label}: {len(rows)} edges")

    _batch_run(_MERGE_INVOLVES,       involves_rows, "INVOLVES       ")
    _batch_run(_MERGE_RELATES_TO,     relates_rows,  "RELATES_TO     ")
    _batch_run(_MERGE_DECIDED_BY,     decided_rows,  "DECIDED_BY     ")
    _batch_run(_MERGE_HAS_PARTY,      party_rows,    "HAS_PARTY      ")
    _batch_run(_MERGE_MAKES_ARGUMENT, arg_rows,      "MAKES_ARGUMENT ")
    _batch_run(_MERGE_APPLIES_CONCEPT,concept_rows,  "APPLIES_CONCEPT")


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 3 — CITATION EDGES
# ──────────────────────────────────────────────────────────────────────────────

def _build_resolution_index(cases: list[dict]) -> dict:
    """
    Builds two lookup indexes:
      filename_index : normalized_filename → case_id
      year_title_index : (year, title_slug) → case_id
    Used to resolve citation strings → case_ids.
    """
    filename_index = {}
    year_title_index = {}

    for d in cases:
        cid  = d.get("case_id")
        fn   = (d.get("filename") or "").lower().replace(" ", "_")
        yr   = d.get("year")
        title= (d.get("title") or "").lower()

        if fn:
            # Index both full filename and stem (without extension)
            stem = re.sub(r'\.(pdf|json)$', '', fn, flags=re.I)
            filename_index[stem] = cid
            filename_index[fn]   = cid

        if yr and title:
            slug = re.sub(r'[^a-z0-9]', '_', title)[:80]
            year_title_index[(yr, slug)] = cid

    print(f"  Citation index: {len(filename_index)} filename entries, "
          f"{len(year_title_index)} year+title entries")
    return filename_index, year_title_index


def _try_resolve(citation_raw: str, citation_type: str,
                 filename_index: dict, year_title_index: dict,
                 current_year: int) -> str | None:
    """
    Tries to resolve a citation string to a case_id.
    Returns case_id or None.
    """
    if citation_type == "reporter":
        # Extract year and try to narrow by year+title matching
        yr_m = re.search(r'\b(\d{4})\b', citation_raw)
        if not yr_m:
            return None
        # We can't resolve reporter citations to specific case_ids without
        # a full citation index. Skip — log unresolved.
        return None

    elif citation_type == "case_number":
        # e.g. "Civil Appeal No. 750 of 1987"
        # Extract year and try filename index
        yr_m = re.search(r'\bof\s+(\d{4})\b', citation_raw, re.I)
        num_m = re.search(r'No\.?\s*(\d+)', citation_raw, re.I)
        if not yr_m:
            return None
        yr  = int(yr_m.group(1))
        num = num_m.group(1) if num_m else None
        # Try to find a case from that year
        # This is inherently ambiguous without a docket number index
        return None

    return None


_MERGE_CITES = """
UNWIND $rows AS r
MATCH (src:Case {case_id: r.src_id})
MATCH (tgt:Case {case_id: r.tgt_id})
MERGE (src)-[rel:CITES {tgt_id: r.tgt_id}]->(tgt)
SET rel.citation_raw  = r.citation_raw,
    rel.citation_type = r.citation_type
"""


def stage_citations(session, cases: list[dict]):
    """
    Creates CITES edges where citations can be resolved to Case nodes.
    Also creates FOLLOWS edges where the same filename appears in citations
    (strong precedent signal — filing cites an earlier case by its exact name).
    """
    print("\n── Stage 3: Citation edges ──")

    filename_index, year_title_index = _build_resolution_index(cases)

    cites_rows = []
    unresolved = 0
    resolved   = 0

    for d in cases:
        src_id = d.get("case_id")
        for cite in (d.get("citations") or []):
            if not isinstance(cite, dict):
                continue
            raw   = cite.get("raw", "")
            ctype = cite.get("citation_type", "unknown")

            # Strategy: look for the opponent's party name in filename index
            # (many Indian SC citations literally embed the case title)
            # This is the highest-fidelity resolution available without a
            # full citation database.
            resolved_id = None

            # Filename-title fuzzy match for case_number citations
            if ctype == "case_number" or ctype == "unknown":
                # Strip citation metadata, keep name fragment if any
                name_fragment = re.sub(
                    r'(Civil|Criminal|Writ|Transfer|Special|SLP)\s+'
                    r'(Appeal|Petition|Case|Leave|Misc)\.?\s*(No\.?\s*\d+)?'
                    r'(\s+of\s+\d{4})?',
                    '', raw, flags=re.I).strip()
                if len(name_fragment) > 8:
                    slug = re.sub(r'[^a-z0-9]', '_', name_fragment.lower())[:60]
                    for key, cid in filename_index.items():
                        if slug in key and cid != src_id:
                            resolved_id = cid
                            break

            if resolved_id:
                resolved += 1
                cites_rows.append({
                    "src_id":       src_id,
                    "tgt_id":       resolved_id,
                    "citation_raw": raw,
                    "citation_type": ctype,
                })
            else:
                unresolved += 1

    for batch in _chunks(cites_rows, BATCH):
        session.run(_MERGE_CITES, rows=batch)

    print(f"  CITES edges created:  {resolved}")
    print(f"  Unresolved citations: {unresolved}")
    print(f"  Resolution rate:      {100*resolved/max(resolved+unresolved,1):.1f}%")
    print(f"  NOTE: Reporter citations (SCC/AIR/SCR) require a full citation")
    print(f"  lookup table to resolve — not available without external DB.")


# ──────────────────────────────────────────────────────────────────────────────
# STAGE 4 — SIMILAR_FACTS (reference — run compute_similar_facts.py)
# ──────────────────────────────────────────────────────────────────────────────

def stage_similar_placeholder():
    print("\n── Stage 4: SIMILAR_FACTS ──")
    print("  Run compute_similar_facts.py (Kaggle GPU recommended).")
    print("  It will generate embeddings, compute cosine similarity via FAISS,")
    print("  and create SIMILAR_FACTS edges in this same Neo4j instance.")


# ──────────────────────────────────────────────────────────────────────────────
# VALIDATION
# ──────────────────────────────────────────────────────────────────────────────

VALIDATION_QUERIES = {
    "Node counts by label":
        "MATCH (n) RETURN labels(n)[0] AS label, COUNT(n) AS count ORDER BY count DESC",
    "Cases with no statutes":
        "MATCH (c:Case) WHERE NOT (c)-[:INVOLVES]->() RETURN COUNT(c) AS count",
    "Cases with no party":
        "MATCH (c:Case) WHERE NOT (c)-[:HAS_PARTY]->() RETURN COUNT(c) AS count",
    "Cases with no topic":
        "MATCH (c:Case) WHERE NOT (c)-[:RELATES_TO]->() RETURN COUNT(c) AS count",
    "Orphan Arguments":
        "MATCH (a:Argument) WHERE NOT ()-[:MAKES_ARGUMENT]->(a) RETURN COUNT(a) AS count",
    "CITES edges":
        "MATCH ()-[r:CITES]->() RETURN COUNT(r) AS count",
    "Outcome distribution":
        "MATCH (c:Case) RETURN c.outcome AS outcome, COUNT(c) AS count ORDER BY count DESC",
}


def run_validation(session):
    print("\n── Validation Queries ──")
    for label, cql in VALIDATION_QUERIES.items():
        try:
            result = session.run(cql)
            rows = result.data()
            print(f"\n  {label}:")
            for row in rows:
                print(f"    {row}")
        except Exception as e:
            print(f"  [{label}] error: {e}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Populate Neo4j KG from CLEANED_fact_layer JSONs"
    )
    parser.add_argument("--folder",   required=True,
                        help="Path to CLEANED_fact_layer folder")
    parser.add_argument("--uri",      default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
                        help="Neo4j bolt URI")
    parser.add_argument("--user",     default=os.environ.get("NEO4J_USER", "neo4j"),
                        help="Neo4j username")
    parser.add_argument("--password", default=os.environ.get("NEO4J_PASSWORD", ""),
                        help="Neo4j password")
    parser.add_argument("--stage",    default="all",
                        choices=["all", "constraints", "nodes", "rels", "citations", "validate"],
                        help="Run only one stage (default: all)")
    parser.add_argument("--sample",   type=int, default=None,
                        help="Process only N files (for testing)")
    args = parser.parse_args()

    if not args.password:
        print("ERROR: --password is required (or set NEO4J_PASSWORD env var).")
        sys.exit(1)

    print(f"Connecting to Neo4j at {args.uri} ...")
    try:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        driver.verify_connectivity()
        print("  Connected.")
    except Exception as e:
        print(f"  Connection failed: {e}")
        sys.exit(1)

    print(f"\nLoading JSONs from {args.folder} ...")
    cases = _load_all_cases(args.folder)
    if args.sample:
        import random; random.seed(42)
        cases = random.sample(cases, min(args.sample, len(cases)))
        print(f"  Sampled {len(cases)} cases for testing.")

    with driver.session() as session:
        stage = args.stage

        if stage in ("all", "constraints"):
            run_constraints(session)

        if stage in ("all", "nodes"):
            t0 = time.time()
            stage_nodes(session, cases)
            print(f"  Nodes done in {time.time()-t0:.1f}s")

        if stage in ("all", "rels"):
            t0 = time.time()
            stage_rels(session, cases)
            print(f"  Relationships done in {time.time()-t0:.1f}s")

        if stage in ("all", "citations"):
            t0 = time.time()
            stage_citations(session, cases)
            print(f"  Citations done in {time.time()-t0:.1f}s")

        if stage in ("all",):
            stage_similar_placeholder()

        if stage in ("all", "validate"):
            run_validation(session)

    driver.close()
    print(f"\n{'='*60}")
    print("KG population complete.")
    print(f"{'='*60}")
    print("\nNext steps:")
    print("  1. Run compute_similar_facts.py on Kaggle GPU")
    print("  2. Run symbolic reasoning engine against this graph")
    print("  3. Use Neo4j Browser to explore: http://localhost:7474")


if __name__ == "__main__":
    main()
