"""
kg_preprocess_utils.py

Single source of truth for all preprocessing functions used by
clean_fact_layer.py before Neo4j population.

Merged from:
  - Dhatri's kg_preprocess_utils.py  (structure, outcome_for_party, base logic)
  - Namratha's transform_fact_layer.py (judge garbage patterns, argument nodes,
    larger ACT_KEYWORDS + CONCEPT_VOCAB, statute dedup, domain tagging,
    decision-text concept scan, Crl.A citation fix)
"""

import re

# ─────────────────────────────────────────────────────────────────────────────
# JUDGES
# ─────────────────────────────────────────────────────────────────────────────

JUDGE_STOPLIST = {
    "kerala", "karnataka", "maharashtra", "tamil nadu", "andhra pradesh",
    "uttar pradesh", "west bengal", "punjab", "haryana", "gujarat", "bihar",
    "rajasthan", "odisha", "assam", "telangana", "madhya pradesh", "goa",
    "delhi", "chandigarh", "india", "union of india", "state", "and", "etc",
    "ors", "anr", "magistrate", "munsiff", "judicial service", "high court",
    "supreme court", "governor", "tribunal", "collector", "director",
    "commissioner", "secretary", "officer",
}

# Dhatri's base patterns + Namratha's additional catches confirmed by diagnostics:
#   "Orissa Administrative Services. Prior To"  → services\., \bprior\s+to\b, administrative
#   "T.N.A. Appeal"                             → \bappeal\b (as last word after initials)
JUDGE_GARBAGE_PATTERNS = [
    r'^from\s+the$', r'^all$', r'^civil\s*$', r'^civ\s', r'^cur\s',
    r'^sessions$', r'vs\.?\s*$', r'^\d+$', r'date\s+of',
    r'appellate', r'^appeal', r'court\s+of', r'^and$', r'magistrate\s+in',
    r'\bin\s+the\b', r'^ors\.?\s*', r'^the$', r'^original$',
    r'^single$', r'^subordinate$', r'natra', r'^from\b',
    # Namratha additions — catch institutional strings regex missed
    r'services?\.',
    r'\bprior\s+to\b',
    r'administrative',
    r'judicial\s+service',
    r'\bappeal\b',
    r'\bpetition\b',
    r'\bjudgment\b',
]


def is_valid_judge_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    n = name.strip()
    low = n.lower().strip(".")
    if len(n) < 4 or low in JUDGE_STOPLIST:
        return False
    for pat in JUDGE_GARBAGE_PATTERNS:
        if re.search(pat, low):
            return False
    has_initial_pattern = bool(re.search(r'\b[A-Z]\.\s?[A-Z][a-z]+', n))
    multi_token_caps    = len(re.findall(r'\b[A-Z][a-z]+\b', n)) >= 2
    if not (has_initial_pattern or multi_token_caps):
        return False
    tokens = [t.lower() for t in re.findall(r'\b[A-Za-z]+\b', n)]
    if all(t in JUDGE_STOPLIST or t in {"a", "the", "of", "in"} for t in tokens):
        return False
    return True


def judge_confidence(name: str) -> str:
    """'high' for K.-Ramaswamy initials pattern; 'medium' otherwise."""
    return "high" if re.search(r'\b[A-Z]\.\s?[A-Z][a-z]+', name) else "medium"


# ─────────────────────────────────────────────────────────────────────────────
# STATUTES
# ─────────────────────────────────────────────────────────────────────────────

# Dhatri's base 25 acts + Namratha's additions from the expanded corpus
ACT_KEYWORDS = {
    "Indian Penal Code":                ["indian penal code", "ipc"],
    "Code of Criminal Procedure":       ["criminal procedure", "crpc", "cr.p.c"],
    "Code of Civil Procedure":          ["civil procedure", "cpc"],
    "Evidence Act":                     ["evidence act"],
    "Contract Act":                     ["contract act"],
    "Land Reforms Act":                 ["land reforms"],
    "Tenancy Act":                      ["tenancy act"],
    "Motor Vehicles Act":               ["motor vehicles act"],
    "Companies Act":                    ["companies act"],
    "Income Tax Act":                   ["income tax act", "income-tax act"],
    "Land Acquisition Act":             ["land acquisition act"],
    "Arms Act":                         ["arms act"],
    "NDPS Act":                         ["ndps act", "narcotic drugs"],
    "Negotiable Instruments Act":       ["negotiable instruments act"],
    "Industrial Disputes Act":          ["industrial disputes act"],
    "Hindu Marriage Act":               ["hindu marriage act"],
    "Hindu Succession Act":             ["hindu succession act"],
    "Prevention of Corruption Act":     ["prevention of corruption"],
    "Consumer Protection Act":          ["consumer protection act"],
    "Arbitration Act":                  ["arbitration act", "arbitration and conciliation"],
    "Rent Control Act":                 ["rent control act"],
    "Excise Act":                       ["excise act", "central excise"],
    "Customs Act":                      ["customs act"],
    "Representation of the People Act": ["representation of the people"],
    "Kerala Judicial Service Rules":    ["kerala judicial service"],
    # Namratha additions
    "Transfer of Property Act":         ["transfer of property act"],
    "Specific Relief Act":              ["specific relief act"],
    "Limitation Act":                   ["limitation act"],
    "Registration Act":                 ["registration act"],
    "Factories Act":                    ["factories act"],
    "Mines Act":                        ["mines act"],
    "Employees State Insurance Act":    ["employees state insurance", "esi act"],
    "Provident Fund Act":               ["provident fund act", "epf act"],
    "Workmen Compensation Act":         ["workmen's compensation", "workmen compensation"],
    "Electricity Act":                  ["electricity act"],
    "Banking Regulation Act":           ["banking regulation act"],
    "Foreign Exchange Act":             ["foreign exchange", "fera", "fema"],
    "Competition Act":                  ["competition act"],
    "Environment Protection Act":       ["environment protection act"],
    "Wildlife Protection Act":          ["wildlife protection act"],
    "SC ST Prevention of Atrocities":   ["atrocities act", "scheduled castes and scheduled tribes"],
}

# Map case_type → domain label for unresolved bare sections (Namratha addition)
_CASETYPE_TO_DOMAIN = {
    "constitutional": "Constitutional Law",
    "criminal":       "Criminal Law",
    "civil":          "Civil Law",
    "labour law":     "Labour Law",
    "tax":            "Tax Law",
    "service":        "Service Law",
    "property":       "Property Law",
    "commercial":     "Commercial Law",
    "family":         "Family Law",
    "environmental":  "Environmental Law",
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


def infer_act_from_context(context_text: str) -> str | None:
    text = (context_text or "").lower()
    for act, keywords in ACT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return act
    return None


def normalize_statute(statute_raw: str, context_text: str,
                      case_type: str = "") -> dict:
    """
    Returns a structured statute record ready for Statute node creation.

    `context_text` should combine principles + issue + facts + reasoning
    summary (widened from principles-only — the Act name is often
    mentioned in `issue` or `facts` rather than `principles` alone). See
    build_statute_context() in clean_fact_layer.py for how it's assembled.

    Fields:
      statute_id   — deduplicated MERGE key for Neo4j
      act_name     — resolved act name or None
      section      — section string
      plausible    — False means likely a concatenation artifact; skip in KG
      act_resolved — True if act_name was successfully inferred
      domain       — act_name if resolved, else case_type fallback, else None
    """
    plausible = (is_plausible_constitution_article(statute_raw)
                 and is_plausible_section(statute_raw))

    domain_fallback = _CASETYPE_TO_DOMAIN.get((case_type or "").lower())

    if not plausible:
        return {
            "statute_id":   statute_raw,
            "act_name":     None,
            "section":      statute_raw,
            "plausible":    False,
            "act_resolved": False,
            "domain":       domain_fallback,
        }

    if 'Art_' in statute_raw or 'Constitution' in statute_raw:
        return {
            "statute_id":   statute_raw,
            "act_name":     "Constitution of India",
            "section":      statute_raw.split('_', 1)[1] if '_' in statute_raw else statute_raw,
            "plausible":    True,
            "act_resolved": True,
            "domain":       "Constitutional Law",
        }

    act = infer_act_from_context(context_text)
    return {
        "statute_id":   f"{act}_{statute_raw}" if act else statute_raw,
        "act_name":     act,
        "section":      statute_raw,
        "plausible":    True,
        "act_resolved": act is not None,
        "domain":       act if act else domain_fallback,
    }


def normalize_statutes_for_case(raw_statutes: list, context_text: str,
                                 case_type: str = "") -> list:
    """
    Processes the full statutes list for one case.
    Deduplicates by statute_id (Namratha addition — prevents duplicate nodes
    when the same section appears twice in one case JSON).
    """
    seen = set()
    result = []
    for raw in (raw_statutes or []):
        if not raw or not isinstance(raw, str):
            continue
        entry = normalize_statute(raw, context_text, case_type)
        if entry["statute_id"] not in seen:
            seen.add(entry["statute_id"])
            result.append(entry)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# CITATIONS
# ─────────────────────────────────────────────────────────────────────────────

def classify_citation(citation: str) -> str:
    # SCC/SCR/AIR with volume in parens after year: "1990 (2) SCC 680"
    if re.search(r'\d{4}\s*\(\d+\)\s*(SCC|SCR|AIR)', citation):
        return "reporter"
    # Year in parens, volume unparenthesized: "(2008) 17 SCC 703"
    if re.search(r'\(\d{4}\)\s*\d+\s*(SCC|SCR|AIR)', citation):
        return "reporter"
    # AIR-prefixed: "AIR 1994 SC 736"
    if re.search(r'\bAIR\s*\d{4}\s*(SC|[A-Z]{2,})\b', citation, re.IGNORECASE):
        return "reporter"
    # No parentheses: "1952 SCR 1091", "1981 Supp SCC 87"
    if re.search(r'\b\d{4}\s+(Supp\.?\s+)?(SCC|SCR|AIR)\s+\d+', citation, re.IGNORECASE):
        return "reporter"
    # JT reporter: "JT 2003 (3) SC 50"
    if re.search(r'\bJT\s+\d{4}\s*\(\d+\)\s*SC\b', citation, re.IGNORECASE):
        return "reporter"
    # Standard case numbers: "Civil Appeal No. 750 of 1987"
    if re.search(r'(Civil|Criminal|Writ)\s+(Appeal|Petition)\s+No', citation, re.IGNORECASE):
        return "case_number"
    # Abbreviated case numbers — Dhatri's base + Namratha's Crl.A fix
    if re.search(
        r'\b(W\.?P\.?|Cr\.?l?\.?A\.?|C\.?A\.?|S\.?L\.?P\.?|T\.?C\.?)\s*\(?[A-Za-z]*\)?\s*No\.?\s*\d+',
        citation, re.IGNORECASE
    ):
        return "case_number"
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# LEGAL CONCEPTS
# ─────────────────────────────────────────────────────────────────────────────

# Dhatri's 15 core terms + Namratha's 40 additions confirmed by corpus
CONCEPT_VOCAB = {
    # Dhatri's base
    "natural justice":               "natural_justice",
    "principles of natural justice": "natural_justice",
    "res judicata":                  "res_judicata",
    "mens rea":                      "mens_rea",
    "estoppel":                      "estoppel",
    "promissory estoppel":           "promissory_estoppel",
    "fundamental rights":            "fundamental_rights",
    "due process":                   "due_process",
    "audi alteram partem":           "audi_alteram_partem",
    "burden of proof":               "burden_of_proof",
    "vicarious liability":           "vicarious_liability",
    "doctrine of merger":            "doctrine_of_merger",
    "locus standi":                  "locus_standi",
    "ultra vires":                   "ultra_vires",
    "quasi-judicial":                "quasi_judicial",
    # Namratha additions
    "quasi judicial":                "quasi_judicial",
    "right to be heard":             "audi_alteram_partem",
    "heard the other side":          "audi_alteram_partem",
    "fair hearing":                  "natural_justice",
    "fundamental right":             "fundamental_rights",
    "onus of proof":                 "burden_of_proof",
    "doctrine of precedent":         "stare_decisis",
    "stare decisis":                 "stare_decisis",
    "separation of powers":          "separation_of_powers",
    "rule of law":                   "rule_of_law",
    "judicial review":               "judicial_review",
    "writ jurisdiction":             "writ_jurisdiction",
    "bias":                          "rule_against_bias",
    "nemo judex":                    "rule_against_bias",
    "double jeopardy":               "double_jeopardy",
    "self incrimination":            "right_against_self_incrimination",
    "article 14":                    "right_to_equality",
    "right to equality":             "right_to_equality",
    "article 21":                    "right_to_life",
    "right to life":                 "right_to_life",
    "personal liberty":              "right_to_life",
    "standing to sue":               "locus_standi",
    "delegated legislation":         "delegated_legislation",
    "legitimate expectation":        "legitimate_expectation",
    "unjust enrichment":             "unjust_enrichment",
    "force majeure":                 "force_majeure",
    "mala fide":                     "mala_fides",
    "malafide":                      "mala_fides",
    "public interest":               "public_interest",
    "good faith":                    "good_faith",
    "reasonable doubt":              "reasonable_doubt",
    "beyond reasonable doubt":       "beyond_reasonable_doubt",
    "circumstantial evidence":       "circumstantial_evidence",
    "hearsay":                       "hearsay_evidence",
    "dying declaration":             "dying_declaration",
    "adverse possession":            "adverse_possession",
    "limitation period":             "limitation",
    "time barred":                   "limitation",
    "arbitration":                   "arbitration",
}


def extract_concepts_from_text(text: str) -> set:
    """Scans arbitrary text and returns matching concept IDs."""
    text = (text or "").lower()
    return {cid for phrase, cid in CONCEPT_VOCAB.items() if phrase in text}


def enrich_concepts(existing: list, principles: list,
                    reasoning_summary: str, decision_details: str,
                    outcome_reasoning: str, case_summary: str) -> list:
    """
    Merges existing legal_concepts with keyword-extracted ones.
    Scans: principles, reasoning_summary, decision_details,
           outcome_reasoning, case_summary.
    (Namratha: also scans decision fields, not just principles+summary.)
    Returns sorted deduplicated list.
    """
    scan_text = " ".join([
        " ".join(principles or []),
        reasoning_summary or "",
        decision_details or "",
        outcome_reasoning or "",
        case_summary or "",
    ])
    found = extract_concepts_from_text(scan_text)
    return sorted(set(existing or []) | found)


# ─────────────────────────────────────────────────────────────────────────────
# PARTIES
# ─────────────────────────────────────────────────────────────────────────────

SUFFIX_PATTERNS = [
    r'\s+and\s+ors\.?$', r'\s+and\s+anr\.?$', r'\s+etc\.?(\s+etc\.?)*$',
    r'\s+and\s+others$', r'\s+&\s+ors\.?$', r'\s+and\s+another$',
    r'\s+ors\.?$', r'\s+anr\.?$',
    r'\s+and\s*$', r'\s+&\s*$',  # dangling connector left after a partial strip
]


def normalize_party_name(name: str) -> str:
    if not name:
        return ""
    low = name.strip().lower()
    # Strip repeatedly until stable — a single pass can leave a dangling
    # "and"/"&" when multiple suffixes are stacked (e.g. "X And Ors Etc"
    # only fully resolves after two rounds: "...ors etc" -> "...and ors" ->
    # "...and" -> "...").
    prev = None
    while prev != low:
        prev = low
        for pat in SUFFIX_PATTERNS:
            low = re.sub(pat, '', low, flags=re.IGNORECASE).strip()
    return low.strip().rstrip('.').strip()


def outcome_for_party(outcome: str, role: str) -> str:
    """Dhatri's helper — kept exactly as written."""
    favorable = (outcome == "Accept" and role == "petitioner") or \
                (outcome == "Reject" and role == "respondent")
    return "favorable" if favorable else "unfavorable"


# ─────────────────────────────────────────────────────────────────────────────
# ARGUMENTS  (Namratha addition — needed for Argument nodes in Neo4j)
# ─────────────────────────────────────────────────────────────────────────────

def build_argument_nodes(case_id: str, petitioner_args: list,
                          respondent_args: list) -> list:
    """
    Constructs Argument node dicts with stable argument_id values.
    Format: case_id_P_0, case_id_P_1 ... for petitioner;
            case_id_R_0, case_id_R_1 ... for respondent.
    court_accepted is None at this stage — set by the symbolic
    reasoning engine later.
    """
    nodes = []
    for i, text in enumerate(petitioner_args or []):
        if text:
            nodes.append({
                "argument_id":   f"{case_id}_P_{i}",
                "text":          text,
                "side":          "petitioner",
                "court_accepted": None,
            })
    for i, text in enumerate(respondent_args or []):
        if text:
            nodes.append({
                "argument_id":   f"{case_id}_R_{i}",
                "text":          text,
                "side":          "respondent",
                "court_accepted": None,
            })
    return nodes
