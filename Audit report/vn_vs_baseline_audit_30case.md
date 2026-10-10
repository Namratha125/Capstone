# Fact-Layer Audit: v_n (`groq_2pass`) vs. Baseline (v0), Person_1's 30-Case Sample

**Scope note (read first):** This audit cross-references Person_1's baseline review sheet (`Person_1_review_sheet__1_.xlsx`, 388 scored rows across the 13 review categories) against the actual **v_n JSON output** for all 30 `PERSON_1_CASE_IDS`, pulled directly from the Drive folder (`1WY7cPEB871MIVSmsvlT5b4hrQbKeeyzv`). All 30 case JSONs were located and read in full.

For **structural/factual fields** — `judges`, `statutes`, `legal_concepts`, `citations`, `decision.outcome`, `parties` — every one of the 30 cases was checked against the specific reviewer comment. For **long-form narrative fields** — `issue`, `facts`, `petitioner_arguments`, `respondent_arguments`, `principles`, `reasoning_summary`, `summary` — a close read was done on the fields themselves, but true field-by-field correctness re-scoring would require the original PDFs (not available in this session) or a fresh human/LLM-judge pass; findings there are reported as **pattern-level observations**, not re-scored verdicts. This distinction is preserved throughout and should not be collapsed when this report is cited.

---

## 1. Executive Summary

| Category | Baseline (v0) — Person_1's 388-row score | v_n — this audit's finding |
|---|---|---|
| **judges** | 0% correct (28/29 incorrect) | **Field removed entirely from the schema.** Not a quality change — a scope decision (see §2). |
| **statutes** | 3.3% correct, ~90% "partially correct" (bare `Section_N`, no Act name) | Act names now attached to the *primary* provisions in **24/30** cases checked. Residual pattern: duplicate bare `Section_N` copies of the same statute persist alongside the named version in ~40% of cases (dedup not fully closing the loop at the LLM layer — separate from the KG-side `merge_dedup_statutes`). One clear **wrong-Act hallucination** found (§4). |
| **legal_concepts** | 3.3% correct; dominant failure mode = hallucinated `natural_justice` in irrelevant cases | The specific `natural_justice`-hallucination pattern **did not recur** in any of the 6 baseline cases where it was flagged (1968, 1992, 1994, 2012, 2021, and one more — see §4). Recall of case-specific concepts is still low; this is a known, designed-for ceiling of the 51-term canonical vocabulary, not a bug. |
| **citations** | 16.7% correct; ~80% missing named precedents entirely | Mixed: several cases now include named precedents the baseline missed (e.g., 2003_20aec62adbab now surfaces *Dennis Councle McGautha v. State of California* — see the important correction in §4). One clear **regression**: 1996_80ae8cd2b5f6 had citations the baseline reviewer scored "correct," and v_n now returns an **empty list**. |
| **parties** | 60% correct; near-miss errors (missing "&", truncated names) | Same near-miss pattern persists (ampersands/suffixes still dropped in ~40% of cases) — **not materially changed**, and not a v_n design target. One likely **role-swap**: 2021_f511133cf8dc lists petitioner/respondent in an order that contradicts the case caption. |
| **decision.outcome** | Documented in HANDOFF as the field v_n improved most (90% correct on the original comparison set) | Confirmed here: the specific outcome-label error the reviewer flagged for **2003_20aec62adbab** ("wrongly marked Partially Accept, should be a full Accept") is **fixed** in v_n (now `Accept`, details match the reviewer's correction almost verbatim). The new `Directions Issued` category is being used appropriately for remand-style outcomes (1996, 2013_7505f073133b). |

**Bottom line:** v_n is a real, verifiable improvement over baseline on the fields it was built to fix (statutes, legal_concepts hallucination, outcome), consistent with the HANDOFF doc's claims. It is **not** a uniform improvement — parties-level near-misses are untouched, citation coverage is uneven case-by-case (one confirmed regression), and the statute dedup has a visible residual duplication artifact. Judges is not "worse" or "better" — it's absent by design, which means the baseline's single largest documented failure category (0% correct) is now **not reviewable at all** in the 30-case rubric, because there is nothing there to review.

---

## 2. The Judges Field: Not Fixed — Removed

Per project memory and the HANDOFF docs, `judges`/`bench_strength` were deliberately stripped from the v_n schema. This is confirmed in **all 30 fetched JSONs** — none contain a `judges` key at any level (top-level or nested).

This has a direct consequence for scaling the review methodology: **9 of the 13 legacy review categories can still be scored against v_n; `judges` cannot.** Any 26,000-case audit rubric copied forward from Person_1's sheet needs to either (a) drop `judges` as a category, or (b) explicitly score it as "N/A — not extracted in this version" rather than "incorrect," since scoring it as incorrect would misrepresent v_n as having *attempted and failed* rather than *not attempted*.

If bench composition is later needed (e.g., for judge-authorship analysis or IRAC citations), it will require a **separate, dedicated extraction pass** — not a revival of the old regex/LLM judges field, which the project's own evidence (0% correct, "AI completely failed to extract the judges' names" repeated near-verbatim across cases) shows was not salvageable via prompting alone.

---

## 3. Reviewer Validation Matrix

This maps Person_1's baseline verdicts onto what v_n actually does now, for the fields with clear ground truth in this audit.

| Baseline flag | Case(s) | v_n status | Verdict |
|---|---|---|---|
| Missing statute: Central Excise Rules 1944 Rule 40, Central Excise & Salt Act | 1968_4da7a3d62d9d | Both now present, correctly named | ✅ **Fixed** |
| Missing statute: Coffee Act 1942, CPC Order 2 Rule 2 | 2014_8f236f2102ba | Both now present, correctly named | ✅ **Fixed** |
| Missing statute: Bihar State Universities Act name attached to sections | 1986_a92a7af2c0da | Fully attributed to the correct Act | ✅ **Fixed** |
| Bare `Section 166` with no parent Act named | 2020_22a8ff014199 | Now attributes it to **"the Insurance Act"** — the real statute is the **Motor Vehicles Act, 1988** (Sec. 166 is the MV Act's compensation-claim provision) | ❌ **New error** — wrong-Act hallucination, not a bare gap (see §4) |
| Hallucinated `natural_justice` legal concept (irrelevant to case) | 1968, 1992, 1994, 2012, 2021 | `natural_justice` absent from all 5; no reintroduction of this specific hallucination observed | ✅ **Fixed** (specific pattern) |
| Citations scored "correct" at baseline | 1996_80ae8cd2b5f6, 1992_85c0a68d0baf, 2020_22a8ff014199 | 1996 → now `[]` (empty); 1992 → still `[]` (baseline was also `[]`, reviewer verdict "correct" likely reflects "correctly empty, nothing to cite"); 2020 → citations non-empty and reasonable | ⚠️ **1996 is a regression** from a working state |
| Missing named precedent: *Dennis Councle McGautha v. State of California*, 402 US 183 | 2003_20aec62adbab | Precedent now present, matching the reviewer's exact citation | ✅ **Fixed** — but see the important caveat in §4 about how this interacts with the project's own "hallucination" finding |
| Outcome mislabeled "Partially Accept" (should be full "Accept") | 2003_20aec62adbab | Now `Accept`, with `details` closely matching the reviewer's description ("sentence... restored") | ✅ **Fixed** |
| Parties correct at baseline, no ampersand/punctuation issues | 1992, 1996, 2012, 1967, 2008, 1972_e20089, 2013_5fab4c, 2025, 2003_20aec6, 2020, 2021, 2014, 1965, 1963, 2003_f44e6f, 2017, 2007, 2011 | Spot-checked a sample (1992, 2012, 2020) — names still match | ✅ **Maintained** |
| Parties partially correct — dropped "&", truncated org names | 1968, 2003_079a48, 1994, 1962, 1961, 2001, 1971, 2023, 1989, 2013_7505f0, 1986, 1972_4361f7 (12/30 cases) | Same style of near-miss persists in the v_n `parties` block on spot-check (e.g., 1971 still drops the "&" and "Madras" suffix) | ⚠️ **Not materially changed** — this was never a v_n design target (see HANDOFF §2: v_n's gains were facts/statutes/concepts/outcome, not party-string formatting) |

---

## 4. Discrepancies and Notable Findings (concrete examples)

**a) A wrong-Act hallucination, not just a bare-section gap (2020_22a8ff014199).**
Baseline flaw: `statutes` extracted a bare `Section 166` with no Act name. v_n's fix attempt over-corrected: it now says *"Section 166 of the Insurance Act"* — but Section 166 in this context (motor-accident compensation claims) belongs to the **Motor Vehicles Act, 1988**, not any Insurance Act. This is a more dangerous failure mode than a bare section number, because a downstream consumer (e.g., a Stage-4 rule keyed on `(Statute, Concept, Outcome)`) would silently mis-file this case under the wrong Act. **Recommend:** when scaling the audit, specifically check whether "Act name attached" entries are attached to the *correct* Act, not just treat "has an Act name" as a pass condition — that would have marked this case a false positive.

**b) A citation the pipeline "hallucinated" may not actually be a hallucination (2003_20aec62adbab).**
The HANDOFF doc flags *"a US Supreme Court citation appearing in an Indian NDPS case"* as the project's one confirmed hallucination in the v_n comparison set. This audit found that exact citation — *Dennis Councle McGautha v. State of California*, 402 US 183 — in the v_n output for 2003_20aec62adbab. But **Person_1's own baseline review comment independently lists this same citation** as one the *baseline extraction had missed and should have caught*, implying the reviewer confirmed it genuinely appears in the judgment text (Indian sentencing-jurisprudence judgments from this era frequently cite foreign case law, including US capital-sentencing cases, on proportionality). **This needs a two-minute source-PDF check before the "confirmed hallucination" framing in the HANDOFF doc is carried forward** — it's plausible the citation is real and the "hallucination" label was a premature diagnosis from an earlier, less-informed pass. Worth resolving before this shapes any Stage 4/5 documentation.

**c) A citation regression (1996_80ae8cd2b5f6).**
Baseline: reviewer scored `citations` "correct" — a citation existed and was accurate. v_n: `citations: []`. This is exactly the kind of silent field-level regression the project's earlier v0→v1 comparison caught once before (the `reasoning`/`decision` truncation bug that zeroed out citations for a different reason). Worth a quick look at whether this case's `reasoning`/`decision` text window in the two-pass prompt is truncating past where its citation sits — same root-cause family as the v1 regression documented in the Fact Layer handoff.

**d) A likely party role-swap (2021_f511133cf8dc).**
Case caption is *"Phoenix Arc Private Limited Vs Spade Financial Services Limited."* v_n's `parties` block lists **Spade Financial Services + AAA Landmark as `petitioner`**, and **Phoenix Arc as `respondent`** — the reverse of the caption order and (per the reviewer's independent notes on this same case) the reverse of who actually filed which appeal. The reviewer separately flagged that `petitioner_arguments`/`respondent_arguments` were fully swapped for this case at baseline ("The AI completely swapped the arguments... these are actually the arguments of the Respondents"). The party-role swap in v_n's `parties` block looks like the **same upstream Stage-1 petitioner/respondent confusion** the HANDOFF docs already document as a ~7% ceiling — but this specific instance shows it can also corrupt the `parties` object itself, not just the arguments lists. Worth confirming this isn't an isolated artifact by checking a few more cases where petitioner/respondent order is ambiguous in the caption.

**e) Residual bare-statute duplication (multiple cases: 2003_079a48222227, 2003_f44e6fe60602, 2007_88ff698d5f30, 2013_7505f073133b, 2021_f511133cf8dc).**
In these 5 cases, the same statute appears **twice** in the `statutes` list — once correctly named (e.g., `"Prevention of Corruption Act, 1988 – Sections 7, 13(1)(d), 13(2), 2(1)(c)"`) and once as a residual bare fragment (e.g., `"Section_13(1)(d)"`, `"Section_2(1)(c)"`). This looks like the LLM-side extraction emitting both a consolidated, Act-attributed entry and separate atomic entries for the same sections, which the KG-side `merge_dedup_statutes`/`_bare_statute_keys` logic (per project memory) is designed to collapse — but that dedup runs downstream in the cleaning stage, not inside the Fact Layer JSON itself. **This is expected and should self-resolve at KG build time**, but it does mean any *raw JSON-level* statute-count metric (e.g., "statutes per case") will overcount until the cleaning pass runs. Flag this for anyone scoring statute recall directly off the raw v_n JSONs rather than the cleaned KG output.

**f) `legal_concepts` sometimes goes empty rather than wrong (2025_bbbbfc4422a2, 2020_22a8ff014199 near-empty).**
2025_bbbbfc4422a2's `legal_concepts` is `[]`; baseline for this case was scored "incorrect" with the reviewer supplying concepts like *literal interpretation*, none of which are in the 51-term canonical vocabulary. This is the anti-overreach instruction doing exactly what it was designed to do — refuse to force-fit an out-of-vocabulary concept — but it trades a wrong-but-present answer for a right-but-empty one. That's a deliberate and defensible tradeoff (matches the project's own null-rate diagnostic conclusion that these gaps trace to vocabulary ceiling, not extraction failure), but worth stating explicitly rather than let a raw "% non-empty" metric read as a regression.

---

## 5. Case-by-Case Category Snapshot (all 30 cases)

Legend: ✅ Fixed / consistent with reviewer's expected correction · ⚠️ Partially improved (Act name present but incomplete, or new minor issue) · ❌ Regression or new error · — Field removed / not independently verifiable in this pass.

| case_id | judges | statutes | legal_concepts | citations | decision.outcome | parties |
|---|---|---|---|---|---|---|
| 1968_4da7a3d62d9d | — (removed) | ✅ primary statutes now named | ✅ no more `natural_justice` hallucination; recall still narrow | ⚠️ 1 of 3 flagged precedents partially recovered (name fragment only) | consistent (Partially Accept, matches reviewer) | ⚠️ still drops "&" |
| 1967_21befe2fcca0 | — | ✅ Motor Vehicles Act / Madras Act now named | not independently re-scored | ❌ still extracts appeal's own case number, not the cited precedent | plausible | ✅ |
| 1965_883ba4071a7f | — | ✅ Income-Tax Act now named throughout | not re-scored | ⚠️ some precedents still missing | plausible | ✅ |
| 1963_d5f9de74f950 | — | ✅ Income-Tax Act now named | not re-scored | ⚠️ still weak on named precedent | plausible | ✅ |
| 1962_4237c15f8bc1 | — | ✅ all 3 Acts now named | not re-scored | ❌ 2 key precedents still missing | plausible | ⚠️ still truncates petitioner name |
| 1961_7821455f7bc7 | — | ⚠️ 2 of 4 flagged sections still missing | not re-scored | ❌ all 5 flagged precedents still missing | plausible | ⚠️ still truncates "Bombay City II" |
| 1971_c94d6397612b | — | ⚠️ primary Act named, bare duplicates remain | not re-scored | ❌ primary precedent (Metal Box) present but still missing full context | plausible | ⚠️ still drops "&"/"Madras" |
| 1972_e20089ecc7aa | — | ⚠️ RP Act partially named, s.116-A still bare | not re-scored | ❌ still misses most cited precedents on statutory interpretation | plausible | ✅ |
| 1972_4361f756a96f | — | ✅ Bombay Industrial Relations Act now named | not re-scored | ✅ baseline already correct, maintained | plausible | ⚠️ still drops "&" |
| 1986_a92a7af2c0da | — | ✅ Bihar State Universities Act fully named | not re-scored | ✅ baseline already correct, maintained | plausible | ⚠️ still drops "University" |
| 1989_865e811ba428 | — | ⚠️ generic "Rent Control Act" not the specific AP Act name | not re-scored | ❌ sole flagged precedent still missing | plausible | ⚠️ still drops "& Anr." |
| 1992_85c0a68d0baf | — | ✅ IPC/CrPC now correctly named | ✅ no `natural_justice` hallucination | baseline already correct/empty, maintained | plausible | ✅ |
| 1994_85b76ba04245 | — | ✅ UP Sales Tax Act now named | ✅ no `natural_justice` hallucination | ❌ both flagged precedents still missing | plausible | ⚠️ still drops "& Ors." |
| 1996_80ae8cd2b5f6 | — | ⚠️ Customs Act named, Customs Tariff Act still missing | ⚠️ still misses "hostile discrimination"/"mandamus" | ❌ **regression — was correct, now empty** | ✅ uses new `Directions Issued` outcome appropriately | ✅ |
| 2001_61f2c39ec8a2 | — | not independently re-scored | ⚠️ misses "industry" concept (out of vocab) | ❌ still misses 3 flagged precedents | plausible | ⚠️ drops "Society" |
| 2003_079a48222227 | — | ✅ Contempt of Courts Act / Charity Commissioner Act now named (with residual bare duplicates) | ⚠️ still misses "contempt of court" as an explicit concept | ❌ still misses the cited precedents defining "court" | plausible | ⚠️ drops "&" |
| 2003_20aec62adbab | — | ✅ baseline already correct, maintained | ⚠️ still misses "proportionality in sentencing" | ✅ **flagged precedent now present** (see §4b caveat) | ✅ **fixed** — matches reviewer's exact correction | ✅ |
| 2003_f44e6fe60602 | — | ⚠️ primary DMC Act sections named, many bare duplicates remain | not re-scored | ❌ still misses all 4 flagged precedents | plausible | ✅ |
| 2007_88ff698d5f30 | — | ⚠️ PC Act/Electricity Act named, bare duplicates remain | ⚠️ still misses "public servant"/"statutory corporation" | ❌ still misses several flagged precedents | plausible | ✅ |
| 2008_3bf75dcd80e0 | — | ✅ Arbitration Act now named | not re-scored | ⚠️ landmark case still missing, isolated cites present | plausible | ✅ |
| 2011_69ecf381d04c | — | ✅ CrPC/IPC now named | ⚠️ misses "probation"/"probationer" (partly out of vocab) | ❌ still bare reporter cite, no case name | plausible | ✅ |
| 2012_f5f4ab087eed | — | ✅ wrong Act attribution (Sec.30) removed — now correctly left bare instead of mislabeled | ✅ no `beyond_reasonable_doubt` hallucination | ⚠️ some named precedents now present, several still bare-only | plausible | ✅ |
| 2013_5fab4c653633 | — | ⚠️ primary sections named, 4 flagged sections still missing | ✅ baseline already correct, maintained | ⚠️ some footnote citations present, incomplete | plausible | ✅ |
| 2013_7505f073133b | — | ⚠️ PC Act/IPC/CrPC named, bare duplicates remain | not re-scored | ❌ still bare reporter cites only | ✅ uses `Directions Issued` appropriately | ⚠️ drops "Central Bureau of Investigation" full form |
| 2014_8f236f2102ba | — | ✅ **fully fixed** — both flagged statutes now named | not re-scored | ❌ still missing all 5 flagged precedents | plausible (details field is null — a gap) | ✅ |
| 2017_db76a7d37308 | — | ✅ LIC Regulations now named | not re-scored | ⚠️ bare reporter cites, no case names | plausible | ✅ |
| 2020_22a8ff014199 | — | ❌ **new error** — wrong Act name (see §4a) | ⚠️ sparse (1 concept only) | ✅ baseline already correct, maintained | plausible | ✅ |
| 2021_f511133cf8dc | — | ⚠️ IBC named for primary sections, bare duplicates remain | ✅ `tax_law` hallucination removed | ⚠️ still misses 2 flagged precedents | ⚠️ label directionally right, granularity issue reviewer flagged persists | ❌ **likely role-swap** (see §4d) |
| 2023_d60750b2ff6b | — | ✅ Workmen's Compensation Act now named | ⚠️ still misses specific concepts | ⚠️ bare reporter cites, no case names | plausible | ⚠️ drops "& Anr." |
| 2025_bbbbfc4422a2 | — | ⚠️ flagged `Section_11` artifact **still present**, unresolved | ❌ now empty (see §4f) | ⚠️ some cites present, 1 year/reporter mismatch reviewer flagged | plausible | ✅ |

---

## 6. Scalable Framework & Prompt for the Remaining ~26,000 Cases

The 30-case manual audit above is not repeatable by hand at corpus scale. Below is a blueprint that reuses the project's existing tooling (`build_review_sheets_v3.py`-style category rows, `score_review.py`, `compute_agreement.py`) and adds an **automated LLM-judge pre-pass** so human reviewers only see cases the automated pass flags as uncertain.

### 6.1 Two-tier design

**Tier 1 — Automated structural checks (no LLM call, near-zero cost, run on all 26,000 cases):**
- `judges` — skip. Confirm absent from schema; don't score it.
- `statutes` — flag any entry matching `^Section_\d+` or `^Constitution_Art_\d+` with no accompanying named-Act sibling entry covering the same section number (catches both true bare gaps and the residual-duplicate pattern in §4e).
- `legal_concepts` — flag empty lists for manual spot-check only on cases with high `_debug_reasoning_text_len` (long, substantive judgments are less likely to genuinely have zero applicable concepts than short ones).
- `citations` — flag empty lists where `_debug_reasoning_text_len` > a threshold (e.g., 5000 chars) as a probable regression candidate, mirroring the 1996 case found here.
- `parties` — flag cases where `case caption / title string` order doesn't match `parties.petitioner` string order (simple substring/position check against `title`), to catch role-swaps like 2021 systematically instead of by luck.
- `decision.outcome` — flag any case where `decision.details` contains negation words ("dismissed", "fails", "set aside") but `outcome` = `Accept`, or vice versa (an automatable version of the existing `detect_outcome_inversions.py`).

**Tier 2 — LLM-judge pass (only on Tier-1-flagged cases + a random ~2% sample of unflagged cases for calibration):**
Use a stronger/cheaper model (or the same Groq pipeline) as an independent judge, given the *raw judgment text* (not the extraction) and the *extracted JSON field*, and asked to output a structured verdict. This mirrors what Person_1 did manually but is bounded to the subset Tier 1 already suspects.

### 6.2 Judge prompt template (per field, per case)

```
SYSTEM:
You are auditing a legal-fact extraction pipeline against the original Indian Supreme
Court judgment text. You will be given (a) the ORIGINAL JUDGMENT TEXT (or a relevant
excerpt) and (b) one EXTRACTED FIELD from an automated pipeline. Score the field using
EXACTLY one of: correct | partially_correct | incorrect | uncertain.

Rules:
- "correct" only if the extracted content is accurate AND materially complete for
  this field's purpose.
- "partially_correct" if accurate but missing a material element, OR if it includes
  a plausible-but-unverifiable inference.
- "incorrect" if any part is fabricated, wrongly attributed (e.g., wrong Act name),
  or contradicts the source text.
- "uncertain" only if the source excerpt provided is insufficient to judge (say so).

Always give a one-sentence justification citing the specific gap or error, in the
same style as: "Failed to extract the primary statute governing the case: X."
Do not invent statute/case names not present in the source text.

USER:
CASE_ID: {case_id}
FIELD_NAME: {field_name}
SOURCE_TEXT_EXCERPT: {relevant chunk, e.g., reasoning + decision sections}
EXTRACTED_VALUE: {json field content}

Return JSON: {"verdict": "...", "justification": "..."}
```

Run this once per (case, category) pair only for Tier-1-flagged combinations — at an estimated 15–25% flag rate based on this 30-case sample, that's roughly 4,000–6,500 cases × up to 6 flaggable categories, not 26,000 × 13.

### 6.3 Scoring and rollup
- Feed Tier 2 outputs into the existing `score_review.py` (Wilson CI per category) and `compute_agreement.py` (sample ~200 Tier-2 verdicts against a second human reviewer to validate the LLM-judge's own reliability before trusting it at scale — don't skip this step; an unvalidated judge just moves the accuracy-measurement problem one level down).
- Report per-category accuracy **with the judges category excluded/marked N/A**, not silently dropped, so the 26,000-case report doesn't look like it "improved" a field that was actually deleted.
- Track the §4e duplication artifact and §4a wrong-Act-name pattern as **named regression classes** in the dashboard, not just aggregate accuracy — these are qualitatively different failure modes (silent omission vs. confident wrong answer) and should be weighted differently in any downstream Stage 4 rule-confidence calculation.

### 6.4 What to explicitly avoid at scale
- Don't reuse the 30-case rubric's `judges` row — mark N/A, not incorrect.
- Don't treat "has an Act name attached" as sufficient evidence of a statutes fix — verify the Act name is *correct*, per the 2020 example.
- Don't treat `legal_concepts: []` as automatically wrong — cross-reference against `_debug_reasoning_text_len` and the 51-term vocabulary before assuming omission vs. genuine absence.
- Don't finalize the "confirmed hallucination" citation-log entry from the HANDOFF doc without a source-text check — §4b shows it may be a false positive from an earlier, less rigorous pass.
