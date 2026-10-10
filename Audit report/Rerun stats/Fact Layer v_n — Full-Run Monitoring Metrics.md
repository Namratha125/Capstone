# Fact Layer v\_n — Full-Run Monitoring Metrics

Oct 10, 2026 · @Dhatri

## Run coverage

All four chunks finished: 9,986 cases covering 2000–2025 with no year gaps.

| Chunk | Years seen | Cases |
| --- | --- | --- |
| B | 2000–06 | 2,496 |
| C | 2006–13 | 2,496 |
| A | 2013–19 | 2,496 |
| D | 2019–25 | 2,498 |
| **Total** |  | **9,986** |

Boundary years (2006, 2013, 2019) appear in two chunks each, so check the merge notebook's duplicate count. Chunk letters are assigned by the years seen in case IDs.

The merged folder is clean: all 9,986 files loaded with 0 load errors, 0 duplicate case IDs and 0 cases before 2000. No case used the regex fallback and both LLM calls succeeded for every case, so every empty field below is the model returning nothing, not an API failure.

By year band the counts are 2000–06: 2,765; 2007–13: 2,423; 2014–19: 2,398; 2020–25: 2,400. Chunks were split by count, so these bands are approximate.

## Field completeness (all 15 fields)

Core fields are almost always populated, but reasoning summary (64.3%) and principles (54.5%) are the weak points. Only 52.8% of cases (95% CI 51.8–53.8) have all six narrative fields (issue, facts, case summary, reasoning summary, principles, outcome), and 37.2% (36.2–38.1) have all 15 fields below. Counts come from all 9,986 merged JSONs.

| Field | Populated | 95% CI | Range across year bands |
| --- | --- | --- | --- |
| Title | 100.0% | 100.0–100.0 | 100.0% |
| Issue | 99.7% | 99.6–99.8 | 99.6% to 99.9% |
| Parties (both sides) | 99.8% | 99.7–99.9 | 99.7% to 99.9% |
| Facts | 99.2% | 99.0–99.4 | 98.9% to 99.5% |
| Outcome | 97.8% | 97.5–98.1 | 96.5% to 98.9% |
| Decision details | 95.9% | 95.5–96.3 | 94.2% to 97.9% |
| Outcome reasoning | 95.9% | 95.5–96.3 | 94.1% to 97.9% |
| Statutes | 94.7% | 94.2–95.1 | 93.4% to 96.0% |
| Petitioner arguments | 93.8% | 93.3–94.2 | 92.7% to 95.2% |
| Citations | 90.8% | 90.3–91.4 | 85.2% to 95.1% |
| Legal concepts | 86.4% | 85.7–87.1 | 84.1% to 88.4% |
| Case summary | 82.0% | 81.3–82.8 | 80.4% to 84.1% |
| Respondent arguments | 75.8% | 75.0–76.7 | 69.7% to 82.2% |
| Reasoning summary | 64.3% | 63.3–65.2 | 62.4% to 66.6% |
| Principles | 54.5% | 53.5–55.5 | 51.6% to 56.6% |

Coverage improves with recency for citations (empty in 14.8% of 2000–06 cases vs 4.9% in 2020–25) and respondent arguments (empty in 30.3% vs 17.8%). The cause is a hypothesis, not a finding. The counts for the five fields in the monitoring log match these exactly (for example 5,440 cases with principles), which confirms the earlier realignment of the scrambled log.

Concept coverage is roughly the same as the old KG's 83.9%. The old KG tagged 68% of cases "Natural Justice", which the 30-case human audit showed was often hallucinated, so the gain is in precision, not coverage, and this data cannot show that. An empty concepts list can also be correct, since the prompt returns `[]` when nothing fits.

## Reasoning gap: principles and reasoning summary fail together

When principles are empty, the reasoning summary is also null in 76.0% of cases, versus 2.1% when principles are present. That points to one shared cause, not two independent failures.

|  | Reasoning summary populated | Reasoning summary null |
| --- | --- | --- |
| Principles populated | 5,326 | 114 |
| Principles empty | 1,092 | 3,454 |

The 3,454 cases with both null (34.6% of the corpus) are the largest single quality gap. Every LLM call succeeded, so the likeliest causes are an empty or short reasoning section from Stage 1 or the model returning nothing. I could not test this: the reasoning-length field is not in the output JSONs.

The reasoning summary is also populated more often for Accept (68.1%) than Reject (63.5%), Partially Accept (61.5%) and Directions Issued (55.4%). Cases with no usable outcome have it in only 11.9%.

## Outcome labels

Accept is the majority label at 53.3%, so any Stage 4 accuracy must beat 54.5% (always predicting Accept across the 9,768 labelled cases) or 57.6% on the three-class labels.

| Outcome | Cases | Share |
| --- | --- | --- |
| Accept | 5,319 | 53.3% |
| Reject | 3,322 | 33.3% |
| Partially Accept | 589 | 5.9% |
| Directions Issued | 538 | 5.4% |
| No usable outcome (null or Unknown) | 218 | 2.2% |

- **Shift from the old KG:** Partially Accept fell from 17.7% to 5.9% and Accept rose from 37.3% to 53.3%. The populations differ (2000+ vs all years), and I cannot say which labelling is right.
- **Trend by era:** Accept rises from 51.0% (2000–06) to 56.8% (2020–25) while Reject falls from 38.3% to 28.1%.
- **Missing outcomes:** 2.2% vs 0.1% Unknown in the old KG.
- **Inversion candidates:** 211 cases (2.11%, CI 1.85–2.41) have an outcome that contradicts the decision text under a keyword check. 158 are labelled Reject but the text says allowed (4.8% of Reject cases); 53 are labelled Accept but the text says dismissed (1.0% of Accept cases).
- **Caveat:** these are candidates, not confirmed errors. The 30-case audit found about 1% inversions. None of the 101 role-swap candidates overlaps with them, so the Reject asymmetry is unexplained.

## Statutes

40.3% of the 90,614 statute entries are bare section numbers with no Act name, and only 35.0% of cases with statutes have every entry named.

- **Volume:** 94.7% of cases have at least one statute. The mean is 9.1 per case, the median 6 and the 95th percentile 26. 93 cases have more than 50 and 10 have more than 100 (maximum 300).
- **Bare share rises with recency:** 33.1% bare in 2000–06 to 47.7% in 2020–25. The cause is a hypothesis, not a finding.
- **Residual duplicates:** 2,436 bare entries repeat a named statute across 1,126 cases (11.9% of cases with statutes). The cleaning stage should collapse these.
- **Most common entries:** Section 302 IPC (1,035), Article 226 (990), bare Section\_3 (840), Article 14 (804), Article 136 (685), Article 21 (514), Article 32 (425). Article 14 also appears 383 times as the un-normalised "Article 14 of the Constitution of India".
- **Rule keying:** a bare Section\_3 has no meaning across Acts, so rules keyed on statute IDs can only use named entries. Articles 19, 20 and 22 are not in the top 40, so the sampling frame for those rules still needs its own counts.

## Citations

Most cases have citations (90.8%), but only 19.3% of the 89,997 entries carry a case name.

- **Entry types:** 17,390 are named (19.3%), 54,871 are bare reporter cites such as SCC or AIR (61.0%), and 17,736 are neither (19.7%).
- **Cases with nothing resolvable:** 4,145 cases (45.7% of those with citations) have no named citation, so they cannot be linked to KG nodes without an external lookup table. That caps CITES edges.
- **Trend:** the named share falls from 28.9% (2000–06) to 15.4% (2020–25).
- **Volume:** the mean is 9.0 per case and the median 6.

## Legal concepts

Concept tagging is spread across the vocabulary (the top term covers 24.1% of cases), but two terms look over-assigned and two are too sparse for rule mining.

- **Volume:** 86.4% of cases have at least one concept, with a mean of 2.21 per case. 13.6% have none.
- **Top terms:** judicial\_review 2,404 cases (24.1%), natural\_justice 2,229 (22.3%), delegated\_legislation 1,674 (16.8%), precedent 1,424, rule\_of\_law 1,216.
- **Improvement:** natural\_justice was tagged in 68% of cases in the old KG and is now 22.3%.
- **Suspect term:** delegated\_legislation at 16.8% is the term the earlier A/B test showed being over-assigned. It deserves a human audit.
- **Overlap:** reasonable\_doubt (717) and beyond\_reasonable\_doubt (522) describe the same doctrine.
- **Too sparse:** force\_majeure (15 cases) and right\_against\_self\_incrimination (9) are under 20 cases. The two terms added in the vocabulary expansion are used: basic\_structure (40) and right\_to\_privacy (22).
- **Vocabulary size:** 53 distinct values appear against 52 expected, so one may be out of vocabulary. The summary file does not show which; compare the value list against the enum.

## Arguments and parties

Petitioner arguments are present in 93.8% of cases, respondent arguments in only 75.8%.

- **Volume:** petitioner arguments average 2.66 per case and respondent arguments 1.86.
- **One-sided cases:** 2,002 cases (20.0%) have petitioner arguments only and 210 (2.1%) respondent only; both are empty in 4.1%.
- **Parties:** both sides are present in 99.8% of cases.
- **Role swaps:** 101 of 9,853 testable cases (1.03%, CI 0.84–1.24) show the petitioner and respondent in the reverse of the caption order. The check is conservative, so treat it as a lower bound on caption-order mismatch.
- **Not measured:** swaps of the argument sides, which the 30-case audit put near 7% and traced to Stage 1.

## Stage 4 readiness

About 71.5% of cases have the minimum fields a rule needs. These counts show fields are present, not that they are correct, so they are upper bounds on usable cases.

| Requirement (cumulative) | Cases | Share of 9,986 |
| --- | --- | --- |
| Three-class outcome, at least 1 statute and 1 petitioner argument | 8,310 | 83.2% |
| ...and at least 1 named statute | 8,072 | 80.8% |
| ...and at least 1 legal concept | 7,141 | 71.5% |

## Tier 1 grounding check

80 of 9,986 cases (0.80%, 95% CI 0.64–1.00) have at least one statute whose number does not appear in the source text.

| Chunk | Flagged cases | Rate | Flagged statute entries | Letter-suffix entries |
| --- | --- | --- | --- | --- |
| B | 12 | 0.48% | 27 | 22 (81%) |
| C | 6 | 0.24% | 6 | 5 (83%) |
| A | 26 | 1.04% | 40 | 37 (92%) |
| D | 36 | 1.44% | 56 | 42 (75%) |
| **Pooled** | **80** | **0.80%** | **129** | **106 (82%)** |

- **Possible false positives:** 82% of flagged entries are letter-suffix sections (120B, 498A, 304B…). Many are likely "120-B"-style formatting misses, but this has not been checked against the source text.
- **What it measures:** only that a number appears somewhere in the text, so it is an upper bound on one failure mode (invented section numbers). It says nothing about wrong-Act attribution.
- **Denominator:** monitoring does not record how many statutes were checked, so a per-statute rate cannot be given.

## Tier 2 LLM judge

These numbers should not go on a slide as accuracy: the judge is unvalidated and appears to penalise content outside the excerpt it sees.

The sample is 274 cases: all 80 Tier 1-flagged cases plus a random 2%. Chunk B is excluded from the pooled figures because most of its verdicts are "Local token budget exhausted" errors; D lost about a third of its verdicts the same way.

| Field (pooled A+C+D, valid verdicts only) | Valid n | Correct | Partially correct | Incorrect |
| --- | --- | --- | --- | --- |
| Statutes | 178 | 15.2% | 14.6% | 70.2% (CI 63–77) |
| Legal concepts | 167 | 19.2% | 19.8% | 61.1% (CI 54–68) |

- **Absence from excerpt:** 87% of "incorrect" justifications say the item is not in the source excerpt (a rough keyword count), suggesting the judge penalises content outside what it sees.
- **No link to Tier 1:** flagged and unflagged cases score the same (70–71% incorrect for statutes), so Tier 1 does not predict Tier 2 failures.
- **Conflict with the human audit:** the 30-case audit found about 70% of statutes correctly named. Trust the human audit over the judge until the judge is calibrated against a human reviewer.

## What is still unmeasured

Everything above measures whether a field is present or how it is shaped, not whether it is correct. The only human-validated accuracy is the 30-case audit.

- **Wide intervals on the audit:** if the 90% outcome figure was 27/30, its 95% CI is about 74–97%, too wide to lean on.
- **Tier 2 judge:** unvalidated against a human, so its verdicts are not usable as accuracy.
- **Tier 1:** not recomputed here because it needs the source text from the original CSV.
- **Unconfirmed candidates:** the outcome-inversion (211) and role-swap (101) counts are heuristics.
- **Fields missing from the output:** reasoning-text length and timestamps are not in the JSONs, so the reasoning gap cannot be tested and throughput cannot be reported.

## Next steps, in priority order

1. **Diagnose the 3,454 cases with both principles and reasoning summary empty.** Count the sentences labelled Reasoning for them in the source CSV. If the input is short, it is a Stage 1 problem; if not, re-run call 2 on that subset.
2. **Human-review about 100 inversion candidates** (50 of the 158 Reject-vs-allowed, 50 of the 211 overall mix with the 53 Accept-vs-dismissed) to estimate the true inversion rate before Stage 4 learns from the outcome field.
3. **Audit delegated\_legislation:** sample 50 tagged cases and check them against the text. Decide whether to merge reasonable\_doubt with beyond\_reasonable\_doubt.
4. **Re-run the cleaning stage** to normalise statute strings and drop bare duplicates, then recompute statute stats and the counts for Articles 14, 19, 20, 21, 22 and 32 for the sampling frame.
5. **Fix the Tier 1 matcher and calibrate Tier 2:** handle "120-B"-style numbers, re-run Tier 2 with a larger excerpt and token budget, and compare about 200 verdicts to a human reviewer.
6. **Decide on a citation lookup table:** 45.7% of cases with citations have no named citation, so CITES edges stay limited without one.
