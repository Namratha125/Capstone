"""kg_v2_utils.py — cleaning helpers for the v_n (gpt-oss-20b, 2-call) fact layer.
Designed from measurements on chunk 3 (2,496 cases, 2013-2019); see PROJECT_AUDIT.md section B.
Vocabulary comes ONLY from concept_vocab.json (generated from the v_n notebook)."""
import json, re, os

HERE = os.path.dirname(os.path.abspath(__file__))
def load_vocab(path=None):
    d = json.load(open(path or os.path.join(HERE, "concept_vocab.json")))
    return set(d["concepts"])

def concept_display(cid):
    return cid.replace("_", " ").title()

# ── STATUTES ────────────────────────────────────────────────────────────────
ABBR = {"ipc": "Indian Penal Code", "crpc": "Code of Criminal Procedure", "cr.p.c": "Code of Criminal Procedure",
        "cpc": "Code of Civil Procedure", "iea": "Indian Evidence Act", "ndps": "NDPS Act"}
BARE_SECTION_RE = re.compile(r"^Section_\w+(\(\w+\))*(-\w+)?$")
CONST_ID_RE = re.compile(r"^Constitution_Art_(\d+[A-Z]?)((?:\(\w+\))*)$")
ART_RE = re.compile(r"(?:Articles?|Art\.?)\s*(\d+[A-Z]?)((?:\s*\(\s*\w+\s*\))*)", re.I)
SEC_RE = re.compile(r"^(?:Sections?|Secs?\.?|S\.)\s*(\d+[A-Za-z]?(?:\(\w+\))*(?:-\w+)?)\s*(?:of|,|-)?\s*(?:the\s+)?(.*)$", re.I)
ACT_ID_RE = re.compile(r"^(IPC|CrPC|CPC|IEA)_S(\w+)$")
SEC_ACT_ABBR_RE = re.compile(r"^(?:Sections?|Secs?\.?)\s*(\d+[A-Za-z]?(?:\(\w+\))*)\s*(IPC|CrPC|Cr\.P\.C|CPC|IEA)\b", re.I)

def slug(s, n=60):
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", s)).strip("_")[:n]

def _clauses(s):
    return "".join("(%s)" % c for c in re.findall(r"\(\s*(\w+)\s*\)", s or ""))

def canon_statute(raw):
    """-> dict(statute_id, act_name, section, kind, resolved) or None (dropped).
    kind: constitution | section | act_ref | bare_dropped"""
    s = (raw or "").strip()
    if not s:
        return None
    if BARE_SECTION_RE.match(s):
        return {"statute_id": None, "kind": "bare_dropped", "raw": s}
    m = CONST_ID_RE.match(s)
    if m:
        return _const(m.group(1), m.group(2), s)
    if re.match(r"^(Articles?|Art\.?)\s*\d", s, re.I) or ("onstitution" in s and ART_RE.search(s)):
        m = ART_RE.search(s)
        if m:
            return _const(m.group(1), _clauses(m.group(2)), s)
    m = ACT_ID_RE.match(s)
    if m:
        act = ABBR[m.group(1).lower()]
        return _sec(act, m.group(2), s)
    m = SEC_ACT_ABBR_RE.match(s)
    if m:
        return _sec(ABBR[m.group(2).lower().replace(".", "")] if m.group(2).lower().replace(".", "") in ABBR else m.group(2), m.group(1), s)
    m = SEC_RE.match(s)
    if m and m.group(2).strip():
        act = re.sub(r"\s+", " ", m.group(2)).strip(" ,.")
        act = re.sub(r"^the\s+", "", act, flags=re.I)
        if len(act) > 100:      # whole-sentence statute: keep as unparsed act reference
            return {"statute_id": "Ref_" + slug(act, 60), "act_name": act[:150], "section": None, "kind": "act_ref", "resolved": False, "raw": s}
        return _sec(act, m.group(1), s)
    # rules / orders / schedules / acts without section
    return {"statute_id": "Ref_" + slug(s, 60), "act_name": s[:150], "section": None, "kind": "act_ref", "resolved": False, "raw": s}

def _const(num, clauses, raw):
    clauses = clauses if clauses.startswith("(") or not clauses else _clauses(clauses)
    sid = f"Constitution_Art_{num.upper()}{clauses}"
    return {"statute_id": sid, "act_name": "Constitution of India", "section": f"Art_{num}{clauses}",
            "kind": "constitution", "resolved": True, "raw": raw, "base_article_id": f"Constitution_Art_{num.upper()}"}

ACT_ALIASES = {"evidence act": "Indian Evidence Act", "the evidence act": "Indian Evidence Act", "penal code": "Indian Penal Code",
               "criminal procedure code": "Code of Criminal Procedure", "code of criminal procedure": "Code of Criminal Procedure",
               "civil procedure code": "Code of Civil Procedure", "ndps act": "Narcotic Drugs and Psychotropic Substances Act",
               "cr.p.c.": "Code of Criminal Procedure", "i.p.c.": "Indian Penal Code"}
UNSPECIFIED_ACT = {"act", "the act", "said act", "this act", "rules", "the rules", "code", "the code", ""}

def norm_act(act):
    a = re.sub(r"\s+", " ", act).strip(" ,.")
    a = re.sub(r"^(the)\s+", "", a, flags=re.I)
    a = re.sub(r",?\s*\(?(1[89]|20)\d{2}\)?$", "", a).strip(" ,.")      # drop ', 1973'
    a = ABBR.get(a.lower(), a)
    return ACT_ALIASES.get(a.lower(), a)

def _sec(act, sec, raw):
    act = norm_act(act)
    if act.lower() in UNSPECIFIED_ACT:        # 'Section 5 of the Act' -> cannot identify the act
        return {"statute_id": None, "kind": "bare_dropped", "raw": raw}
    return {"statute_id": f"{slug(act, 50)}_S{slug(sec, 20)}", "act_name": act, "section": sec,
            "kind": "section", "resolved": True, "raw": raw}

def clean_statutes(raw_list):
    out, seen, dropped = [], set(), []
    for r in raw_list or []:
        c = canon_statute(r)
        if not c:
            continue
        if c["kind"] == "bare_dropped":
            dropped.append(c["raw"]); continue
        if c["statute_id"] in seen:
            continue
        seen.add(c["statute_id"]); out.append(c)
        if c.get("base_article_id") and c["base_article_id"] != c["statute_id"] and c["base_article_id"] not in seen:
            seen.add(c["base_article_id"])   # also link the parent article so rules on 'Constitution_Art_21' match
            out.append({"statute_id": c["base_article_id"], "act_name": "Constitution of India",
                        "section": c["base_article_id"].split("Constitution_", 1)[1], "kind": "constitution",
                        "resolved": True, "raw": c["raw"], "derived_parent": True})
    return out, dropped

# ── CITATIONS ───────────────────────────────────────────────────────────────
REPORTER_RE = re.compile(r"(\(\d{4}\)\s*\d+\s*SCC\s*\d+|\d{4}\s*\(\d+\)\s*SCC\s*\d+|\d{4}\s*Supp\.?\s*SCC\s*\d+|AIR\s*\d{4}\s*SC\s*\d+|\d{4}\s*SCR\s*\d+|\(\d{4}\)\s*\d+\s*SCR\s*\d+)", re.I)
CASE_NO_RE = re.compile(r"(Civil|Criminal)\s+Appeal\s+No|W\.?P\.?|SLP|Special Leave", re.I)
NAME_RE = re.compile(r"^(.*?\b(?:v\.?|vs\.?|versus)\s+.*?)(?:[,(]?\s*(?:\(\d{4}\)|\d{4}\s*\(|AIR\s*\d{4}|\d{4}\s*SC).*)?$", re.I)

def clean_citations(raw_list):
    out, seen = [], set()
    for r in raw_list or []:
        if not isinstance(r, str) or not r.strip():
            continue
        r = r.strip()
        m = REPORTER_RE.search(r)
        key = re.sub(r"\s+", "", m.group(0)).lower() if m else re.sub(r"[^a-z0-9]+", "", r.lower())
        name = None
        nm = re.search(r"^(.+?\b(?:v\.?|vs\.?|versus)\s+.+?)\s*(?:[,(]|\d{4}|AIR\b|$)", r, re.I)
        if nm and re.search(r"\b(v\.?|vs\.?|versus)\b", r, re.I):
            name = nm.group(1).strip(" ,")
        if key in seen:
            # same reporter cite listed twice: upgrade existing entry with name if the dup carries one
            for e in out:
                if e["key"] == key and name and not e["case_name"]:
                    e["case_name"], e["citation"], e["citation_type"] = name, r, "named"
            continue
        seen.add(key)
        ctype = "named" if name else "reporter" if m else "case_number" if CASE_NO_RE.search(r) else "other"
        out.append({"citation": r, "citation_type": ctype, "reporter_key": key if m else None, "case_name": name, "key": key})
    for e in out: e.pop("key")
    return out

# ── MISC ────────────────────────────────────────────────────────────────────
def normalize_case_type(ct):
    t = (ct or "").lower()
    if not t.strip(): return "unspecified"
    for k, v in (("special leave", "slp"), ("slp", "slp"), ("writ", "writ"), ("criminal", "criminal"), ("civil", "civil"),
                 ("tax", "tax"), ("service", "service"), ("constitution", "constitutional"), ("contempt", "contempt"),
                 ("review", "review"), ("transfer", "transfer"), ("arbitration", "arbitration"), ("appeal", "appeal_other")):
        if k in t: return v
    return "other"

def outcome_direction(details):
    t = (details or "").lower()
    a = bool(re.search(r"\ballow|set aside|quash|\bgranted|acquit", t)); d = bool(re.search(r"dismiss|\bfail|rejected", t))
    return "allowed" if a and not d else "dismissed" if d and not a else "mixed" if a and d else "none"

def outcome_conflict(outcome, details):
    dr = outcome_direction(details)
    return (outcome == "Accept" and dr == "dismissed") or (outcome == "Reject" and dr == "allowed")

def outcome_for_party(outcome, role):
    if outcome not in ("Accept", "Reject", "Partially Accept"):
        return None            # Unknown / Directions Issued: no favorable/unfavorable claim
    if outcome == "Partially Accept":
        return "partial"
    fav = (outcome == "Accept" and role == "petitioner") or (outcome == "Reject" and role == "respondent")
    return "favorable" if fav else "unfavorable"

def normalize_party_name(name):
    low = (name or "").strip().lower()
    for pat in (r"\s+and\s+ors\.?$", r"\s+and\s+anr\.?$", r"\s+etc\.?(\s+etc\.?)*$", r"\s+and\s+others$", r"\s+&\s+ors\.?$", r"\s+and\s+another$", r"\s+ors\.?$", r"\s+anr\.?$"):
        low = re.sub(pat, "", low).strip()
    return low.rstrip(".").strip()

def build_argument_nodes(case_id, pet, res):
    nodes = []
    for side, tag, lst in (("petitioner", "P", pet), ("respondent", "R", res)):
        for i, t in enumerate(lst or []):
            if t: nodes.append({"argument_id": f"{case_id}_{tag}_{i}", "text": t, "side": side, "court_accepted": None})
    return nodes
