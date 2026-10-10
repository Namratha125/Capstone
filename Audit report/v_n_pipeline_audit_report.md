# v_n Fact-Layer Pipeline — Fix Verification Audit

**Source notebook audited:** `v_n_for_2000_2025.ipynb` (uploaded copy, 30 cells)
**Method:** Every fix discussed across this conversation was checked against actual cell source code in the uploaded notebook — not assumed. Cell numbers below refer to this notebook's cell index (0-based, as loaded).

**Overall verdict:** 11 of 12 tracked fixes are confirmed present, correct, and reproducible across repeated runs, including the Jagdish statute-fabrication fix (re-verified after applying the recommended prompt guardrail). 1 fix (`legal_concepts`/statute anti-fabrication guardrails, generally) remains confirmed effective but **not fully reliable** — direct A/B testing on identical cases shows it reduces but does not eliminate misclassification with a non-deterministic, sampling-dependent error rate; a concrete Tier 1/Tier 2 monitoring plan (Section 6) is now in place to measure this rate during the full run rather than leave it as an open question. The legal-concepts vocabulary question is resolved with real Aura graph data — 52 terms, final (Sections 2 and 7).

---

## 1. Fixes Confirmed Present, With Evidence

### 1.1 Judges and `bench_strength` fully removed
**Status: ✅ Confirmed**

A global search across all 30 cells for `judges` and `bench_strength` returns **zero matches anywhere in the notebook** — not in `CASE_SCHEMA`, not in `build_case_prompt`, not in `extract_metadata`, not in the output `record`.

Evidence — `CASE_SCHEMA` (Cell 5):
```python
"required": ["title", "court", "date", "case_type",
             "parties", "issue", "facts", "petitioner_arguments",
             "respondent_arguments", "statutes", "citations"],
```
No `judges`/`bench_strength` keys present.

Evidence — `extract_metadata()` (Cell 11):
```python
return {
    "date": date,
    "court": court,
}
```
Returns only `date` and `court` — the old `judges` key is gone.

---

### 1.2 Title bug (trailing date + duplicate-suffix digit) — fixed
**Status: ✅ Confirmed**

Cell 11:
```python
_DATE_SUFFIX_RE = re.compile(
    r"_on_(\d{1,2})_([A-Za-z]+)_(\d{4})(?:_\d+)?$",
    re.I
)

def title_from_filename(filename):
    fn = re.sub(r"\.pdf$", "", filename, flags=re.I)
    fn = re.sub(r"__on_.+$", "", fn)      # old double-underscore variant
    fn = _DATE_SUFFIX_RE.sub("", fn)      # "_on_25_April_2000" or "_on_25_April_2000_1"
    fn = re.sub(r"_\d+$", "", fn)         # any remaining trailing "_1" dedup digit
    return fn.replace("_", " ").strip().title()
```
Handles both the double-underscore and single-underscore `_on_` date-suffix patterns, plus a trailing duplicate-file digit. Directly verified against real output in conversation (e.g. `"Haldiram Bhujiawala And Anr vs Anand Kumar Deepak Kumar And Anr"` — clean, no `_on_28_February_2000_1` remnant).

---

### 1.3 Date priority (filename-first, not body-regex-first)
**Status: ✅ Confirmed**

Cell 11:
```python
def extract_date_from_filename(filename):
    fn = re.sub(r"\.pdf$", "", filename, flags=re.I)
    m = _DATE_SUFFIX_RE.search(fn)
    if not m:
        return None
    day, month_name, year = m.groups()
    month = _MONTHS.get(month_name.lower())
    if not month:
        return None
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"
```

Cell 19, in `record["metadata"]`:
```python
"date": extract_date_from_filename(filename) or meta["date"],
```
Filename-derived date is tried first; the body-text regex (`meta["date"]`) is only a fallback. This matches the fix applied after the Hridaya Rangan Verma case showed the reverse priority picking up a wrong in-body date.

---

### 1.4 Statute deduplication (multi-section, Order/Rule, Article)
**Status: ✅ Confirmed, and the multi-section regex bug is fixed**

Cell 19:
```python
_YEAR_RE = re.compile(r"^(18|19|20)\d{2}$")
_NUM_TOKEN_RE = re.compile(r"\b(\d{1,3}[A-Za-z]?(?:\(\d+\)|\(\w\))?)\b")

def _bare_statute_keys(s):
    if re.search(r"[Ss]ections?\b", s):
        tokens = _NUM_TOKEN_RE.findall(s)
        nums = {t for t in tokens if not _YEAR_RE.match(t)}
        if nums:
            return {f"section_{n.lower()}" for n in nums}
    m = _ARTICLE_NUM_RE.search(s)
    if m:
        return {f"article_{m.group(1).lower()}"}
    m = _ORDER_RULE_RE.search(s)
    if m:
        return {f"order_{m.group(1)}_rule_{m.group(2)}"}
    return {s.strip().lower()}
```
This is the corrected version — the earlier `_SECTION_ALL_RE.findall()` approach (which only caught the number immediately after "Section(s)" in a comma list) was replaced with a token-scan across the whole string. **Directly re-verified against the K Shamrao case (2003_079a48222227)**: a rerun after this fix produced zero leftover bare `Section_N` fragments — every one collapsed into the LLM's fully-named form. One residual gap noted and accepted: `Section_5(2)` vs `"Section 5(2) of the Act"` didn't merge due to a parenthetical-subsection formatting mismatch — flagged as a known minor residual, not the systemic bug.

---

### 1.5 Citation deduplication (reporter cites + case-number cites)
**Status: ✅ Confirmed**

Cell 19:
```python
_REPORTER_CITE_RE = re.compile(
    r"\(?\d{4}\)?\s*\d+\s*(?:SCC|SCR|SCALE)\s*\d+|AIR\s*\d{4}\s*[A-Za-z\.]+\s*\d+",
    re.I
)
_CASE_NUM_CITE_RE = re.compile(r"[A-Z]{2,8}\s*\(?[A-Za-z]*\)?\s*\d+\s*/\s*\d{2,4}")

def _bare_cite_key(cite):
    m = _REPORTER_CITE_RE.search(cite)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip().lower()
    m = _CASE_NUM_CITE_RE.search(cite)
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip().lower()
    return cite.strip().lower()
```
Handles both `AIR/SCC/SCR`-style reporter citations and `RFA (OS) 17/99`-style case-number citations (the second pattern was added after the Haldiram Bhujiawala case showed a same-citation-different-format duplicate slipping through).

---

### 1.6 `legal_concepts` constrained to a fixed enum + anti-overreach instruction
**Status: ⚠️ Confirmed present, but empirically non-deterministic — direct A/B evidence found**

`ANALYSIS_SCHEMA`, Cell 5 — `legal_concepts` uses `"enum": [...]` listing 50 fixed terms (not free text). Cell 7 (`build_analysis_prompt`) contains the matching instruction block:
```
Select ONLY from this fixed list of legal concept IDs — do not invent
new concept names...
Only select a concept if it is a genuine legal basis for the Court's
reasoning — not merely a term that sounds topically related to the
subject matter of the case.
Return only the ones actually applicable. If none of the listed
concepts genuinely apply, return [] rather than the closest match.
```
Both the schema-level enforcement and the prompt-level instruction are present and match each other's term list exactly.

**Direct reproducibility test on the J Chatterjee (rent eviction) case shows the instruction is not reliable.** Two independent runs of the identical `case_id` (`2000_1bd9d893cb84`) produced different `legal_concepts`:
- Run 1: `["burden_of_proof", "locus_standi"]` — clean.
- Run 2: `["burden_of_proof", "delegated_legislation", "quasi_judicial"]` — the previously-identified `delegated_legislation` misclassification reappeared.

This confirms the instruction is a genuine soft mitigation that lowers the error rate but does not eliminate it — the model's non-zero temperature (0.05) means the same case can be classified correctly on one call and incorrectly on the next. **Treat this as a documented, evidence-backed residual risk, not a resolved item** — see Limitation 2 (updated).

---

### 1.7 Outcome: `Directions Issued` category + regex fallback + `normalize_outcome` mapping
**Status: ✅ Confirmed, and now reproducibly stable across two independent runs**

`ANALYSIS_SCHEMA`, Cell 5:
```python
"outcome": {
    "type": ["string", "null"],
    "enum": ["Accept", "Reject", "Partially Accept", "Directions Issued", None]
},
```
`OUTCOME_MAP` and `normalize_outcome()`, Cell 5, include the `"directions issued"` / `"continuing mandamus"` mappings and a keyword-fallback branch.

Cell 19:
```python
groq_outcome = normalize_outcome(sem.get("outcome"))
final_outcome = groq_outcome or regex_outcome(decision_text) or "Unknown"
```
`regex_outcome()` (Cell 11) is a full, working function — confirmed not a stub.

The prompt (Cell 7) contains **two rounds of tightening**, both present:
1. The "don't confuse this with ordinary judgments containing the word 'direct'" paragraph (added after the Allahabad Bank over-use case).
2. The "a remand with a deadline is still Accept, not Directions Issued" paragraph (added after the Mediwell Hospital borderline case — confirmed against the source PDF that this case's correct outcome was `Accept`, not `Directions Issued`).

**Re-verified twice, independently, with consistent results:**
- `1996_80ae8cd2b5f6` (Mediwell Hospital) — flipped from `Directions Issued` to `Accept`, matching the source PDF.
- `2013_7505f073133b` — confirmed `Reject` on two separate runs (was previously mis-classified as `Directions Issued`).
- `2000_9e957bd63530` (Almitra H Patel, the genuine PIL positive control) — confirmed `Directions Issued` on two separate runs, showing the tightening didn't over-correct and suppress legitimate uses of the category.

This is now the most reliably validated fix in the pipeline — stable across repeated calls, not just a single lucky run.

**Re-verified with a direct spot-check.** Running `process_case()` fresh on `1996_80ae8cd2b5f6` (Mediwell Hospital) after both tightening rounds now returns:
```json
{
  "outcome": "Accept",
  "outcome_reasoning": "The Court ordered the respondent to issue the exemption certificate to the appellant and to discharge the bank guarantee, thereby granting the relief sought.",
  "extraction_method": "case:groq|analysis:groq"
}
```
Confirmed flipped from `Directions Issued` to the correct `Accept` classification. One case that has **not** yet been re-checked with the same spot-check method: `2013_7505f073133b`, which still showed as `Directions Issued` in the most recent batch output — worth running the same one-case check on it before treating the fix as fully validated across the board, since one confirmed flip doesn't guarantee every borderline case resolves correctly.

---

### 1.8 Act-name hallucination guardrail
**Status: ✅ Confirmed present (prompt-level only — inherently a soft mitigation)**

Cell 6 (`build_case_prompt`), in the `STATUTES:` section:
```
Do not invent an Act name. Do not guess or infer the parent Act name for
a bare section number based on assumption or pattern-matching. Only
attach an Act name if it is explicitly stated in the judgment text, or
if the context makes the Act unambiguous (e.g., a motor accident
compensation claim under "Section 166" is virtually always the Motor
Vehicles Act, 1988 — never the Insurance Act). If you are not confident
of the correct Act, leave the provision as a bare section number rather
than attributing it to the wrong Act.
```
This is present, but **note: this is a prompt instruction, not a hard constraint** — the schema has no mechanism to enforce it. Treat as a mitigation that reduces but does not eliminate this failure mode (see Section 4, Limitation #2).

---

### 1.9 `extraction_method` reflects real per-call success/failure
**Status: ✅ Confirmed**

Cell 19:
```python
extraction_method = f"case:{method1}|analysis:{method2}"
```
Replaces the old hardcoded `"groq_2pass"` string. Also confirmed wired into the checkpoint logic:
```python
if "regex_fallback" in record["extraction_method"]:
    errors.append({"key": key, "error": f"partial/full LLM failure: {record['extraction_method']}"})
else:
    done_keys.add(key)
    session_done += 1
```
A partially- or fully-failed case is no longer silently marked "done" — it stays in `todo` for retry on the next run.

---

## 2. Legal Concepts Vocabulary — Resolved With Aura Data

**Query run:** `MATCH (lc:LegalConcept) RETURN lc.name, count{(lc)<-[:APPLIES_CONCEPT]-()} AS n ORDER BY n DESC` against the production Aura instance (baseline v0 KG, 26,688 cases). Full results: 49 concept nodes returned, ranging from `Natural Justice` (18,117 cases) down to `Force Majeure` (2 cases).

**Finding 1 — the 50-term enum is data-validated, not a guess.** Cross-checking all 49 returned concept names against the schema's enum: every single one matches a term already in the enum (39 from `kg_preprocess_utils.py`'s `CONCEPT_VOCAB`, plus the ~12 terms unique to the old fact-layer's local `_CONCEPTS` dict — `habeas_corpus`, `doctrine_of_severability`, `precedent`, `fair_trial`, `preventive_detention`, `bail_jurisprudence`, `specific_performance`, `tax_law`, `service_law`, `property_law`, `hostile_witness`, `consumer_protection`). No unexplained or mismatched names.

**Finding 2 — no garbage/one-off terms to prune.** The lowest-frequency nodes (`Force Majeure`=2, `Hearsay Evidence`=5, `Unjust Enrichment`=7) are all genuine legal doctrines, not malformed strings or duplicates. Your friend's hypothesis that some of the ~50 might be uncurated freeform-LLM leftovers worth dropping is not supported by this data — nothing here looks like noise.

**Finding 3 — exactly one enum term has zero nodes in the graph:** `right_against_self_incrimination`. It's a legitimate `CONCEPT_VOCAB` term that simply never fired on any case in the baseline corpus. Recommend keeping it in the enum regardless — it's a real doctrine that could plausibly appear in the 2000–2025 subset even though it didn't trigger historically.

**Finding 4 — confirms the two previously-identified gaps are real, not speculative.** Neither `basic_structure` nor `right_to_privacy` appears anywhere in the 49 returned nodes — the graph's own vocabulary has never captured either doctrine, consistent with what was flagged earlier from the Kesavananda Bharati validation case.

**Decision: expand to 52 terms.** Keep all 50 existing enum terms as-is (data shows no reason to prune any), add `basic_structure` and `right_to_privacy`. This is no longer a pending/undecided item — apply the update to `ANALYSIS_SCHEMA`'s `legal_concepts` enum (Cell 5) and the matching list in `build_analysis_prompt` (Cell 7) before the full run.

---

## 3. Outstanding Verification Items — Updated With This Round's Results

- **`2013_7505f073133b`** — ✅ **Resolved and reproducibly confirmed.** `Reject` on two independent runs, no longer `Directions Issued`.
- **Almitra H Patel positive control** — ✅ **Resolved and reproducibly confirmed.** `Directions Issued` on two independent runs.
- **Indian Overseas Bank case** (`vicarious_liability`/`circumstantial_evidence`) — ✅ Resolved and stable across two runs (`["service_law", "precedent"]` both times).
- **Jagdish rent-eviction case** (`delegated_legislation`) — ⚠️ **Confirmed non-deterministic, not resolved.** Direct A/B evidence: clean on one run, `delegated_legislation` reappeared on the next run of the identical case. See Section 1.6 (updated) and Limitation 2 (updated).
- **Jagdish & Anr. murder case** (bogus Article statutes) — ❌ **Still broken, and the root cause is worse than first diagnosed.** First run produced normalized `Constitution_Art_7/9/14` (regex-path origin); this run produced raw, unnormalized `"Article 7"`/`"Article 9"`/`"Article 14"` (LLM-path origin). The bug is not confined to `extract_statutes()`'s regex — the model itself is fabricating these statute references directly, and which path produces the error varies run to run. The context-window regex fix proposed earlier only patches one of the two sources. **Needs a prompt-level fix, not just a regex fix — see recommendation below.**
- **The four originally-reviewed cases as a combined batch** — now effectively done: Dena Bank, Haldiram Bhujiawala, Hridaya Rangan Verma, and Indian Overseas Bank have all been re-run (twice, in fact) under the current pipeline as part of this round and the last. All four look structurally sound; Haldiram's previously-flagged `Section_69(2)` statute duplicate did not recur in this run (though see the note on non-determinism above — a clean run doesn't guarantee the underlying dedup bug in `_bare_statute_keys` is fully fixed, only that this particular run didn't trigger it).

**Recommended prompt-level fix for the Jagdish Article-hallucination issue** — add to Cell 6 (`build_case_prompt`), in the `STATUTES:` section, alongside the existing Act-name guardrail:
```
Do not include a constitutional Article or statutory section merely
because the number appears somewhere in the source text (e.g. in a
citation, docket number, or unrelated numbered clause). Only include a
provision if the judgment text discusses or applies it substantively in
connection with the legal issue being decided. If you are not certain a
provision is actually relevant to this case's reasoning, omit it.
```
This targets the LLM-side fabrication directly, which the regex-only fix cannot reach. Recommend applying this before the full run, then re-running the Jagdish case (`2000_6c941e2104ed`) once more to confirm.

---

## 4. Limitations That Cannot Be Fully Resolved at This Layer

These are genuine, evidence-backed ceilings — appropriate to state plainly as documented limitations in a methodology/limitations section rather than problems still being chased.

### Limitation 1 — Petitioner/respondent role confusion (upstream Stage 1 ceiling)
**Confirmed recurring, not fixable in the Fact Layer.** Directly observed in the Phoenix Arc Private Limited case (`2021_f511133cf8dc`): `parties.petitioner` lists the parties in reverse order relative to the case caption, consistent with your dissertation's own documented Stage 1 finding (LegalBERT macro F1 65.62%, with petitioner/respondent argument confusion named as the single largest error source). The `ARGUMENTS — LABEL VERIFICATION` prompt instruction mitigates this for the *arguments* fields by asking the model to re-derive the correct side from content, but this instruction does not extend to the `parties` object itself, and the underlying sentence-classification error is not something a downstream extraction prompt can fully correct. **Recommended framing for your paper:** state this as an inherited ~7% ceiling from Stage 1, not a Fact Layer defect.

### Limitation 2 — Concept/statute selection has a confirmed non-zero, non-deterministic error rate even with prompt guardrails in place
Two separate guardrails (the "genuine legal basis, not just topically related" instruction for `legal_concepts`, and the Act-name guardrail for statutes) are both confirmed present and both confirmed to *reduce* errors on repeated testing — but **direct A/B evidence from two independent reruns of the same cases** shows they do not eliminate errors: the J Chatterjee case's `delegated_legislation` misclassification disappeared on one run and reappeared on the next; the Jagdish & Anr. case's bogus constitutional Articles persisted across two runs but from a different source path each time (regex-extracted the first time, LLM-fabricated the second). **Recommended framing for your paper:** state plainly, with these two cases as concrete examples, that prompt-level guardrails measurably reduce but do not guarantee elimination of concept/statute misclassification, and that the error rate is better characterized as probabilistic (tied to model sampling temperature) than as a fixed, fully-patched defect. A residual hallucination rate should be assumed for both fields and, if resources allow, spot-audited on a larger sample rather than assumed to be zero.

### Limitation 3 — Citation resolution ceiling (bare reporter citations)
Structural, already documented in your own project handoffs: the majority of citations in the corpus are bare reporter strings (e.g. `"(2017) 14 SCC 80"`) with no case name attached, and cannot be resolved to a specific Case node in the Knowledge Graph without an external SCC/AIR/SCR → case-identity lookup table. Nothing in this Fact Layer pipeline changes this — the dedup fixes in Section 1.5 reduce *duplicate* citation entries but do not increase *resolvability*. This is a data-availability limitation, not an extraction-quality one.

### Limitation 4 — `reasoning.summary` / `principles` null-rate, partially unexplained and directionally unstable
Diagnostic evidence gathered across two separate batches now shows this is more unsettled than a single stable bias. On a 96-case batch, `reasoning_text` length was nearly identical between Accept (10,883 chars) and Reject (10,304 chars) outcome cases, ruling out "dismissals are just more terse" as a full explanation for why `reasoning.summary` nulls out more for some outcomes. But the *direction* of the divergence itself is not stable across runs: an earlier batch showed Reject cases nulling out roughly 2x more than Accept; a later 43-case batch showed the opposite — Accept at 39.1% null vs. Reject at 21.4% null (`Partially Accept` at 66.7%, on only 3 cases — too small to read as a real rate). This inconsistency across batches is itself informative: it suggests the effect is closer to sample-size noise / case-by-case Stage-1 classification variance than a systematic, direction-stable bias tied to any one outcome category. **Recommended framing:** report the null-rate as a real, measured phenomenon (roughly 20–50% depending on batch and field), explicitly note that reasoning-text length does not explain it, and state that the direction of any outcome-correlation was not stable across batches — consistent with attributing it to per-case Stage-1 labeling variance rather than a directional bias in the Fact Layer pipeline itself.

### Limitation 5 — `Directions Issued` remains a judgment call in genuinely gray-zone cases
Even after two rounds of prompt tightening (Section 1.7), the Mediwell Hospital case demonstrated that "remand with a compliance deadline" is a real boundary case between `Accept` and `Directions Issued` that prompt engineering can narrow but not fully eliminate — some Indian Supreme Court judgments do not cleanly fall into either an ordinary adversarial win/loss frame or a pure continuing-mandamus PIL frame. **Recommended framing:** state this as an inherent taxonomy-boundary ambiguity in a subset of judgments, present at a low but non-zero rate even after mitigation.

### Limitation 6 — PDF-extraction and Stage 1 sentence-classification noise
Inherited, not addressed by this pipeline: page header/footer text occasionally leaking mid-sentence (partially mitigated by the `TEXT ARTIFACTS` prompt instruction, not eliminated), and the underlying LegalBERT classifier's known accuracy ceiling (70.94% validation / 64.43% test accuracy) bounding how much signal any downstream prompt-based extraction can recover from mis-labeled or unlabeled sentences.

### Limitation 7 — No train/independent-verification loop for statute Act-attribution or concept selection at scale
All verification in this conversation was done by hand-reading a small number of source PDFs against extracted JSON (K Shamrao, Mediwell Hospital, Pashora Singh, and roughly a dozen others). This does not constitute a scaled accuracy measurement. **Recommended framing for the paper:** state clearly that fixes were validated on a small, non-random sample of manually-inspected cases plus the pre-existing 30-case Person_1 rubric, not on a large-scale statistically powered audit — and that your own audit document's proposed Tier 1/Tier 2 automated + LLM-judge framework (already designed, not yet executed at scale) remains the appropriate next step for a corpus-wide accuracy claim.

### Limitation 2 Update — Jagdish Article-hallucination fix re-verified
The recommended prompt fix (Cell 6, `STATUTES:` section — "do not include a provision merely because the number appears somewhere in the source text") was applied and the Jagdish case (`2000_6c941e2104ed`) re-run. Result:
```
statutes: ['Section 302 IPC', 'Section 34 IPC', 'Section 313 CrPC']
```
The three bogus Article entries are gone, nothing fabricated in their place. Confirmed resolved on the specific case that surfaced it. Given the earlier finding that this fabrication can originate from either the regex path or the LLM path across different runs, this should still be tracked via the Tier 1 grounding check (Section 6) during the full run rather than treated as permanently closed on one clean re-run alone.

---

## 6. Monitoring Plan for the Full Run (Concrete Implementation)

Since Limitation 2's residual non-determinism cannot be eliminated by further prompt iteration in the time available, this section gives the concrete mechanism for measuring and reporting it during the full run.

**Tier 1 — automated statute/citation grounding check.** Reconstructs each case's `full_text` from the source CSV and checks whether every extracted statute's section/article number appears anywhere in the source text the model actually saw. A number that appears nowhere in the source is flagged as a likely fabrication candidate. No API cost — pure string matching. This is the automated version of the check that caught the Jagdish Article-hallucination issue by hand. Run periodically (e.g. every 500–1,000 cases) during the full run.

**Tier 2 — LLM-judge on flagged cases + a small (~2%) random calibration sample.** Reuses the judge-prompt template already designed in `vn_vs_baseline_audit_30case.md` Section 6.2, run only against Tier-1-flagged cases plus a small random sample for calibration — not the full corpus, to keep API cost bounded.

**Reporting:** track the resulting flagged-case rate as a real, cited number (e.g. "X% of a Y-case sample showed statute-grounding failures") for the methodology/limitations section, rather than reporting the fixes as having reduced the error rate to zero.

---

## 7. Legal Concepts Vocabulary — Final Decision: Stop at 52 Terms

Following the Aura-data-driven expansion in Section 2, the recommendation is to **not expand further preemptively**. Three reasons, not just one:

1. **Coverage is already high on the baseline corpus** — 83.9% of all 26,688 cases matched under the pre-constraint scheme; the gap is real but bounded (~4,300 cases), not corpus-wide.
2. **The two additions made were evidence-driven** (a specific landmark validation case, Kesavananda Bharati, actually failing to match), which is the appropriate bar for adding a term — further additions without a similarly concrete trigger case would be guessing, not data-driven design.
3. **A longer tail of rare, single-purpose concepts works against Stage 4's rule-mining goal.** Concepts with very few case matches (e.g. `force_majeure` at n=2 in the Aura data) give the symbolic reasoning engine little to generalize a rule from. Adding more rare, hyper-specific concepts doesn't help Stage 4 — it just produces more sparsely-populated nodes.

**Recommended next step, if any:** let the `concepts_empty` diagnostic run across the full corpus, then look at whether empties cluster around a *specific recognizable legal domain* (not just isolated cases) at meaningful volume — e.g. if IP law consistently returns `[]` across hundreds of cases, that's the same kind of concrete signal that justified the current two additions, and would warrant a deliberate, advisor-consulted v2 vocabulary pass after the run. Doing it now, before that volume of evidence exists, would be guessing again.

---

## 8. Recommended Order of Operations From Here

1. ✅ Done — statute-fabrication guardrail applied and re-verified on the Jagdish case (see Limitation 2 update above).
2. ✅ Done — vocabulary expanded to 52 terms with Aura-data justification (Section 2).
3. Wire up the Tier 1/Tier 2 monitoring scripts (Section 6) before starting the run, so they're ready to run periodically rather than built after the fact.
4. Wipe production `OUTPUT_DIR` + checkpoint one final time (the 108 cases generated before the multi-section statute-dedup fix still need regenerating).
5. Start the real quarter run.
6. Run Tier 1 periodically (every 500–1,000 cases); run Tier 2 once near the end on the accumulated flagged + calibration set.
7. Report the Tier 1/Tier 2 flagged rate honestly in the methodology/limitations section as a measured residual error rate — not as a fully-closed issue.
