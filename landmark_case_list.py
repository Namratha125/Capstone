"""
Person 4 — Task B, Part 3: Landmark case list (2000-2025), Articles 14/19/20/21/22/32
Curated from established legal sources + SCI landmark-summaries pages (2020-2023, 2024, 2025, 2026 tabs).

SOURCING NOTE:
- SCI's site filters by year via client-side JS; the year query param isn't
  respected by server-side fetches, so this can't be scraped programmatically
  in one pass. The user is manually scraping each year's tab and feeding
  titles/dates/subjects back in; this file is updated incrementally.
- Once the "Subject" column is available (as it was for 2020-2023 and part
  of 2022), classification against Art 14/19/20/21/22/32 is far more
  reliable than title-only matching — prefer sending Subject lines when
  scraping further years.
- A handful of scraped 2024/2025 titles (title-only, no subject) could not
  be confidently classified — see NEEDS_REVIEW below.
- CONTINUING-MANDAMUS RULE: a few cases here (e.g. T.N. Godavarman) are part of
  multi-decade matters that opened before 2000 but produced specific, separately
  dated orders after 2000 with their own real legal/extractable content (your
  corpus is organized one-PDF-per-judgment-date, so this matches corpus
  structure). For these, `year`/`citation` reflect THAT SPECIFIC ORDER's own
  decision date, not the litigation's filing year — stated explicitly in each
  such entry's `holding` field so it's never ambiguous when cited later.
- The SCI landmark-summaries site has NO records for 2000-2016 (confirmed:
  every batch of scraped years bottoms out at 24 Aug 2017 / Puttaswamy privacy
  case). This is a real content gap on that site, not a filter bug — the
  "Centre for Research and Planning, SCI" project that produces these
  summaries appears to only cover ~mid-2017 onward. 2000-2016 cases below
  were sourced instead from general legal reference material (case law
  blogs, SCC-citing academic sources) and cross-checked citations via search,
  not scraped from the SCI site.
"""

import re

landmark_cases = [
    # ---------------- Article 21 (personal liberty / right to life) ----------------
    {"name": "Selvi v. State of Karnataka", "year": 2010, "citation": "(2010) 7 SCC 263",
     "article": "21", "holding": "Narcoanalysis/polygraph/BEAP without consent violates Art 20(3)/21"},
    {"name": "Justice K.S. Puttaswamy (Retd.) v. Union of India", "year": 2017, "citation": "(2017) 10 SCC 1",
     "article": "21", "holding": "Right to privacy recognized as a fundamental right under Art 21"},
    {"name": "Common Cause v. Union of India", "year": 2018, "citation": "(2018) 5 SCC 1",
     "article": "21", "holding": "Passive euthanasia and living wills recognized under Art 21"},
    {"name": "Common Cause v. Union of India (Modification of Guidelines)", "year": 2023, "citation": "2023 INSC 77",
     "article": "21", "holding": "Simplified procedure for executing Advance Medical Directives — reduced role of JMFC"},
    {"name": "Navtej Singh Johar v. Union of India", "year": 2018, "citation": "(2018) 10 SCC 1",
     "article": "21", "holding": "Decriminalized consensual homosexuality; dignity/autonomy under Art 21"},
    {"name": "Shafin Jahan v. Asokan K.M. (Hadiya case)", "year": 2018, "citation": "(2018) 16 SCC 368",
     "article": "21", "holding": "Right to marry a person of one's choice under Art 21"},
    {"name": "Joseph Shine v. Union of India", "year": 2018, "citation": "(2018) 2 SCC 189",
     "article": "21", "holding": "Adultery law (§497 IPC) struck down — dignity/autonomy under Art 21 (also Art 14)"},
    {"name": "PUCL v. Union of India (Right to Food case)", "year": 2001, "citation": "W.P. (Civil) 196/2001",
     "article": "21", "holding": "Right to food recognized as facet of Art 21"},
    {"name": "Suchita Srivastava v. Chandigarh Administration", "year": 2009, "citation": "(2009) 9 SCC 1",
     "article": "21", "holding": "Reproductive rights, incl. of mentally disabled woman, as facet of Art 21 personal liberty"},
    {"name": "Swamy Shraddananda v. State of Karnataka", "year": 2008, "citation": "(2008) 13 SCC 767",
     "article": "21", "holding": "Recognized special category life sentence (without remission) as alternative to death penalty"},
    {"name": "Union of India v. V. Sriharan", "year": 2015, "citation": "(2016) 7 SCC 1",
     "article": "21", "holding": "Constitution bench on life imprisonment, remission powers, and Art 21 in sentencing"},
    {"name": "Deepika Singh v. Central Administrative Tribunal", "year": 2022, "citation": "2022 INSC 833",
     "article": "21", "holding": "Maternity leave entitlement not defeated by non-traditional family structure"},
    {"name": "Vijay Madanlal Choudhary v. Union of India", "year": 2022, "citation": "2022 INSC 757",
     "article": "21", "holding": "PMLA constitutionality upheld; bail/liberty under Art 21, also touches Art 20(3) self-incrimination and Art 22 arrest safeguards"},
    {"name": "X v. Principal Secretary, Health and Family Welfare Dept., Govt. of NCT of Delhi", "year": 2022, "citation": "2022 INSC 740",
     "article": "21", "holding": "Unmarried woman's right to abortion between 20-24 weeks — reproductive autonomy under Art 21"},
    {"name": "Aparna Ajinkya Firodia v. Ajinkya Arun Firodia", "year": 2023, "citation": "2023 INSC 146",
     "article": "21", "holding": "Child's right to privacy/identity limits compelled DNA testing in matrimonial disputes"},
    {"name": "Animal Welfare Board of India v. Union of India (Jallikattu case)", "year": 2023, "citation": "2023 INSC 548",
     "article": "21", "holding": "Confirms Art 14/21 fundamental rights do not extend to animals"},
    {"name": "Sundar @ Sundarrajan v. State by Inspector of Police", "year": 2023, "citation": "2023 INSC 264",
     "article": "21", "holding": "Courts must genuinely weigh mitigating circumstances before imposing death penalty"},
    {"name": "Supriyo @ Supriya Chakraborty v. Union of India", "year": 2023, "citation": "2023 INSC 920",
     "article": "21", "holding": "No fundamental right to marry, but queer persons have right to relationships/choice of partner under Art 21"},
    {"name": "V. Senthil Balaji v. State Represented by Deputy Director", "year": 2023, "citation": "2023 INSC 677",
     "article": "21", "holding": "Habeas corpus/PMLA custody computation — 'custody' means actual physical custody; Art 21/22"},
    {"name": "Manish Sisodia v. Central Bureau of Investigation", "year": 2023, "citation": "2023 INSC 956",
     "article": "21", "holding": "Prolonged incarceration and right to speedy trial under Art 21 in bail determination"},
    {"name": "Dr. Balram Singh v. Union of India (Manual Scavenging case)", "year": 2023, "citation": "2023 INSC 950",
     "article": "21", "holding": "Directions on eliminating manual scavenging — dignity under Art 21"},
    {"name": "K. Umadevi v. Government of Tamil Nadu", "year": 2025, "citation": "2025 INSC 781",
     "article": "21", "holding": "Reproductive rights / maternity leave as part of Art 21"},
    {"name": "M.K. Ranjitsingh v. Union of India (GIB conservation)", "year": 2025, "citation": "2025 INSC 1472",
     "article": "21", "holding": "Balances environmental protection against climate/energy policy"},
    {"name": "Radhika Agarwal v. Union of India", "year": 2025, "citation": "2025 INSC 273",
     "article": "21", "holding": "Arrest powers of GST/Customs officers subject to Art 21/22 procedural safeguards"},
    {"name": "V. Senthil Balaji v. Deputy Director, Directorate of Enforcement", "year": 2024, "citation": "2024 INSC 739",
     "article": "21", "holding": "Prolonged incarceration without trial and bail under PMLA — Art 21"},
    {"name": "Manish Sisodia v. Directorate of Enforcement", "year": 2024, "citation": "2024 INSC 595",
     "article": "21", "holding": "Reaffirmed 'bail is the rule, jail is the exception' — Art 21 liberty"},
    {"name": "Arvind Kejriwal v. Directorate of Enforcement", "year": 2024, "citation": "2024 INSC 512",
     "article": "21", "holding": "Arrest/bail of sitting Chief Minister under PMLA — Art 21/22 safeguards"},
    {"name": "Md. Rahim Ali @ Abdur Rahim v. State of Assam", "year": 2024, "citation": "2024 INSC 41",
     "article": "21", "holding": "Burden of proof in Foreigners Tribunal proceedings — liberty under Art 21"},
    {"name": "Frank Vitus v. Narcotics Control Bureau", "year": 2024, "citation": "2024 INSC 372",
     "article": "21", "holding": "Onerous bail conditions (passport surrender, movement restriction) struck down under Art 21"},
    {"name": "Devu G. Nair v. State of Kerala", "year": 2024, "citation": "2024 INSC 764",
     "article": "21", "holding": "Habeas corpus for queer couple; right to cohabit as part of Art 21"},
    {"name": "Dr Sohail Malik v. Union of India", "year": 2025, "citation": "2025 INSC 1415",
     "article": "21", "holding": "POSH Act jurisdiction case — grounded partly in Art 14/21 dignity of workplace"},
    {"name": "Justice K.S. Puttaswamy (Retd.) v. Union of India (Aadhaar case)", "year": 2018, "citation": "(2019) 1 SCC 1",
     "article": "21", "holding": "Upheld Aadhaar Act 4:1 but struck down Section 57 (private-party use) and the national security exception, applying privacy proportionality test from Puttaswamy I"},
    {"name": "Anita Kushwaha v. Pushap Sudan", "year": 2016, "citation": "(2016) 8 SCC 509",
     "article": "21", "holding": "Access to justice recognized as a fundamental right under Art 21 (and Art 14), enabling case transfer under Art 32/142"},
    {"name": "Shatrughan Chauhan v. Union of India", "year": 2014, "citation": "(2014) 3 SCC 1",
     "article": "21", "holding": "Inordinate, unexplained delay in disposing mercy petitions violates Art 21 and grounds commutation of death sentence"},
    {"name": "T.N. Godavarman Thirumulpad v. Union of India (NPV / Compensatory Afforestation order)", "year": 2002, "citation": "(2002) 10 SCC 646",
     "article": "21", "holding": "Order dated 29 Oct 2002 in the continuing-mandamus forest matter (opened 1995/1996); Net Present Value/afforestation framework tied explicitly to Art 21 healthy-environment right. Included per project rule: cited by the specific order's own decision date, not the matter's filing year — see sourcing note"},
    {"name": "Bachpan Bachao Andolan v. Union of India", "year": 2011, "citation": "(2011) 5 SCC 1",
     "article": "21", "holding": "Ban on child employment in circuses; rescue/rehabilitation directions grounded in Art 14/21/21A/23/24 (freedom from exploitation)"},
    {"name": "Harish Rana v. Union of India", "year": 2026, "citation": "2026 INSC 222",
     "article": "21", "holding": "Streamlines Common Cause; CANH withdrawal, best-interest test (just outside 2000-2025 window, flag for context)"},

    # ---------------- Article 32 (writ jurisdiction) ----------------
    {"name": "I.R. Coelho v. State of Tamil Nadu", "year": 2007, "citation": "(2007) 2 SCC 1",
     "article": "32", "holding": "Ninth Schedule laws post-1973 subject to judicial review via Art 32/basic structure"},
    {"name": "Lalita Kumari v. Government of U.P.", "year": 2014, "citation": "(2014) 2 SCC 1",
     "article": "32", "holding": "Mandatory FIR registration — enforceable via writ jurisdiction"},
    {"name": "Skill Lotto Solutions Pvt. Ltd. v. Union of India", "year": 2020, "citation": "(2021) 5 SCC 391",
     "article": "32", "holding": "Art 32 as integral to basic structure; rule of law enforcement mechanism"},
    {"name": "State of Uttaranchal v. Balwant Singh Chaufal", "year": 2010, "citation": "2010 INSC 47",
     "article": "32", "holding": "Landmark guidelines curbing abuse of PIL jurisdiction under Art 32/226 — cost/screening safeguards against publicity/private-interest litigation"},
    {"name": "Third All India Judges Association case", "year": 2002, "citation": "(2002) 4 SCC 247",
     "article": "32", "holding": "Continuing Art 32 writ (since 1989) — subordinate judiciary service conditions"},
    {"name": "Fifth All India Judges' Association case", "year": 2022, "citation": "2022 INSC 445",
     "article": "32", "holding": "Continuing Art 32 writ — Delhi Judicial Service modifications"},
    {"name": "All India Judges Association v. Union of India", "year": 2025, "citation": "2025 INSC 735",
     "article": "32", "holding": "Continuing Art 32 writ since 1989 — judicial service reforms"},
    {"name": "In Re: Assent, Withholding or Reservation of Bills by the Governor and President",
     "year": 2025, "citation": "2025 INSC 1333",
     "article": "32", "holding": "Presidential Reference under Art 143 — justiciability limits adjacent to writ remedy scope"},
    {"name": "Association for Democratic Reforms v. Election Commission of India (Bihar SIR case)", "year": 2026, "citation": "2026 INSC 564",
     "article": "32", "holding": "Upholds ECI's Special Intensive Revision of electoral rolls under Art 324; citizenship scrutiny in voter rolls (just outside 2000-2025 window, flag for context)"},

    # ---------------- Article 14 (equality) ----------------
    {"name": "Shayara Bano v. Union of India", "year": 2017, "citation": "(2017) 9 SCC 1",
     "article": "14", "holding": "Triple talaq unconstitutional — manifest arbitrariness test under Art 14"},
    {"name": "Joseph Shine v. Union of India", "year": 2018, "citation": "(2018) 2 SCC 189",
     "article": "14", "holding": "Struck down §497 IPC (adultery) — also an Art 14 classification case"},
    {"name": "National Legal Services Authority v. Union of India (NALSA)", "year": 2014, "citation": "(2014) 5 SCC 438",
     "article": "14", "holding": "Transgender persons' right to self-identify gender under Art 14/15/21"},
    {"name": "State of Kerala v. Leesamma Joseph", "year": 2021, "citation": "2021 INSC 309",
     "article": "14", "holding": "Persons with disabilities entitled to reservation in promotion, not just initial appointment"},
    {"name": "Janhit Abhiyan v. Union of India", "year": 2022, "citation": "2022 INSC 1175",
     "article": "14", "holding": "103rd Amendment (EWS reservation) upheld 3:2; reasonable classification under Art 14"},
    {"name": "Tej Prakash Pathak v. Rajasthan High Court", "year": 2024, "citation": "2024 INSC 847",
     "article": "14", "holding": "7-judge bench: recruitment rules can't be changed mid-process — Art 14 fairness in public employment"},
    {"name": "In Re: Section 6A of the Citizenship Act, 1955", "year": 2024, "citation": "2024 INSC 789",
     "article": "14", "holding": "Constitutional validity of Assam Accord citizenship provision upheld — Art 14 classification"},
    {"name": "Sukanya Shantha v. Union of India", "year": 2024, "citation": "2024 INSC 753",
     "article": "14", "holding": "Caste-based discrimination in prison manuals/labour division struck down — Art 14/15/17/21"},
    {"name": "State of Punjab v. Davinder Singh", "year": 2024, "citation": "2024 INSC 562",
     "article": "14", "holding": "7-judge bench: sub-classification within SC/ST for reservation is permissible — Art 14/15/16"},
    {"name": "Anjuman Ishaat E Taleem Trust v. State of Maharashtra", "year": 2025, "citation": "2025 INSC 1063",
     "article": "14", "holding": "TET mandatory for minority-institution teachers — Art 14 classification test"},
    {"name": "Indian Young Lawyers Association v. State of Kerala (Sabarimala case)", "year": 2018, "citation": "(2018) 10 SCC 689",
     "article": "14", "holding": "5-judge bench (4:1): exclusion of women aged 10-50 from Sabarimala Temple is manifestly arbitrary — violates Art 14/15/17"},
    {"name": "Vijaya Bank v. Prashant B Narnaware", "year": 2025, "citation": "2025 INSC 691",
     "article": "14", "holding": "Restrictive employment covenant tested against Art 14/19 public policy"},

    # ---------------- Article 19 (speech, movement, association, profession) ----------------
    {"name": "Union of India v. Association for Democratic Reforms", "year": 2002, "citation": "(2002) 5 SCC 294",
     "article": "19", "holding": "Voters' right to know candidates' antecedents flows from Art 19(1)(a)"},
    {"name": "T.K. Rangarajan v. Government of Tamil Nadu", "year": 2003, "citation": "(2003) 6 SCC 581",
     "article": "19", "holding": "No fundamental right to strike for government employees"},
    {"name": "Ramlila Maidan Incident v. Home Secretary, Union of India", "year": 2012, "citation": "(2012) 5 SCC 1",
     "article": "19", "holding": "Police action against peaceful protestors violated Art 19(1)(a)/(b)"},
    {"name": "Krishnamoorthy v. Shivakumar", "year": 2015, "citation": "(2015) 3 SCC 467",
     "article": "19", "holding": "Non-disclosure of criminal antecedents undermines informed electoral choice — Art 19(1)(a)"},
    {"name": "Shreya Singhal v. Union of India", "year": 2015, "citation": "(2015) 5 SCC 1",
     "article": "19", "holding": "§66A IT Act struck down — vague/overbroad restriction on Art 19(1)(a)"},
    {"name": "Subramanian Swamy v. Union of India", "year": 2016, "citation": "(2016) 7 SCC 221",
     "article": "19", "holding": "Upheld criminal defamation (§499/500 IPC) as reasonable restriction under Art 19(2)"},
    {"name": "Adivasis for Social and Human Rights Action v. Union of India", "year": 2023, "citation": "2023 INSC 512",
     "article": "19", "holding": "Non-tribals' right to settle in Scheduled Areas under Art 19(1)(e); right to vote not tribe-restricted"},
    {"name": "Madhyamam Broadcasting Limited v. Union of India", "year": 2023, "citation": "2023 INSC 324",
     "article": "19", "holding": "Denial of security clearance to news channel on undisclosed grounds violates Art 19(1)(a) press freedom"},
    {"name": "Bar Council of India v. Bonnie Foi Law College", "year": 2023, "citation": "2023 INSC 116",
     "article": "19", "holding": "BCI empowered to mandate Bar exam — quality control tied to Art 19(1)(g) right to practice"},
    {"name": "Anuradha Bhasin v. Union of India", "year": 2020, "citation": "(2020) 3 SCC 637",
     "article": "19", "holding": "Internet shutdowns must satisfy Art 19(1)(a)/(g) proportionality test"},
    {"name": "Vinod Dua v. Union of India", "year": 2021, "citation": "(2021) 4 SCC 574",
     "article": "19", "holding": "Journalist's prosecution unlawful under Art 19(1)(a); sedition-adjacent speech protection"},
    {"name": "Kaushal Kishore v. State of U.P.", "year": 2023, "citation": "2023 INSC 4",
     "article": "19", "holding": "5-judge bench on restrictions on ministers' free speech beyond Art 19(2) grounds"},
    {"name": "Gaurav Kumar v. Union of India", "year": 2024, "citation": "2024 INSC 443",
     "article": "19", "holding": "Excessive Bar Council enrollment fees restrict right to practice under Art 19(1)(g)"},
    {"name": "Javed Ahmad Hajam v. State of Maharashtra", "year": 2024, "citation": "2024 INSC 65",
     "article": "19", "holding": "WhatsApp status expressing solidarity quashed as sedition-type FIR — Art 19(1)(a)"},
    {"name": "Association for Democratic Reforms v. Union of India (Electoral Bonds case)", "year": 2024, "citation": "2024 INSC 113",
     "article": "19", "holding": "Electoral Bonds Scheme struck down — voters' right to information under Art 19(1)(a)"},
    {"name": "Imran Pratapgadhi v. State of Gujarat", "year": 2025, "citation": "2025 INSC 190",
     "article": "19", "holding": "FIR over a poem quashed; 'reasonable person' standard for prosecuting speech under Art 19(1)(a)"},
    {"name": "Poonam v. Dule Singh", "year": 2025, "citation": "2025 INSC 1284",
     "article": "19", "holding": "Voters' right to know candidate's criminal antecedents flows from Art 19(1)(a)"},

    # ---------------- Article 20 (protection against conviction) ----------------
    {"name": "Selvi v. State of Karnataka", "year": 2010, "citation": "(2010) 7 SCC 263",
     "article": "20", "holding": "Self-incrimination protection (Art 20(3)) against narcoanalysis/polygraph"},
    {"name": "C.B.I. v. Dr. R.R. Kishore", "year": 2023, "citation": "2023 INSC 817",
     "article": "20", "holding": "Retrospective invalidation of a procedural provision does not offend Art 20(1) (no new offence/enhanced punishment created)"},
    {"name": "O.P. Dahiya v. Union of India", "year": 2003, "citation": "(2003) 1 SCC 122",
     "article": "20", "holding": "Retrial of an accused neither convicted nor acquitted in the first trial does not amount to double jeopardy under Art 20(2)"},
    {"name": "State of Rajasthan v. Hat Singh", "year": 2003, "citation": "AIR 2003 SC 791",
     "article": "20", "holding": "Prosecution/punishment under two distinct sections of an Act for the same conduct does not violate Art 20(2) double jeopardy"},
    {"name": "M/S A.K. Sarkar & Co. v. State of West Bengal", "year": 2024, "citation": "2024 INSC 186",
     "article": "20", "holding": "Art 20(1) bars only a higher/retroactive punishment — courts may apply a new law's lesser punishment to a past offence (ameliorative exception)"},
    {"name": "In Re: Summoning Advocates Who Give Legal Opinion or Represent Parties During Investigation",
     "year": 2025, "citation": "2025 INSC 1275",
     "article": "20", "holding": "Client's Art 20(3) protection extended via attorney-client privilege"},
    # NOTE: Art 20 remains the thinnest article overall, but the R.R. Kishore case
    # is a genuine post-2000 Art 20(1) precedent worth citing on ex post facto
    # reasoning. Most classic Art 20 cases (Kedar Nath Bajoria, Maqbool Hussain,
    # Nandini Satpathy) still predate 2000.

    # ---------------- Article 22 (arrest and detention) ----------------
    {"name": "Arnesh Kumar v. State of Bihar", "year": 2014, "citation": "(2014) 8 SCC 273",
     "article": "22", "holding": "Restricts automatic/routine arrest, esp. in §498A-type cases; arrest guidelines"},
    {"name": "Ahmed Noormohmed Bhatti v. State of Gujarat", "year": 2005, "citation": "(2005) 3 SCC 647",
     "article": "22", "holding": "Upheld §151 CrPC (arrest without warrant to prevent a cognizable offence) as a reasonable, non-arbitrary restriction consistent with Art 21/22"},
    {"name": "Pankaj Bansal v. Union of India", "year": 2023, "citation": "2023 INSC 866",
     "article": "22", "holding": "Written grounds of arrest mandatory under PMLA/Art 22(1) — direct precursor to Vihaan Kumar/Mihir Rajesh Shah line"},
    {"name": "Ameena Begum v. The State of Telangana", "year": 2023, "citation": "2023 INSC 788",
     "article": "22", "holding": "Detailed guidelines for reviewing preventive detention orders; distinguishes 'law and order' from 'public order'"},
    {"name": "Prabir Purkayastha v. State (NCT of Delhi)", "year": 2024, "citation": "(2024) SCC OnLine SC 934",
     "article": "22", "holding": "Failure to inform grounds of arrest in writing/timely renders detention illegal"},
    {"name": "Sharif Ahmad v. State of Uttar Pradesh", "year": 2024, "citation": "2024 INSC 91",
     "article": "22", "holding": "Safeguards on cognizance/process-issuance orders — Art 21/22 procedural fairness"},
    {"name": "Vihaan Kumar v. State of Haryana", "year": 2025, "citation": "2025 INSC 162",
     "article": "22", "holding": "Grounds of arrest must be communicated in a manner the arrestee understands — Art 22(1)"},
    {"name": "Mihir Rajesh Shah v. State of Maharashtra", "year": 2025, "citation": "2025 INSC 1288",
     "article": "22", "holding": "Grounds of arrest mandatory in writing, all statutes, ≤2 hrs before remand"},
]

NEEDS_REVIEW = [
    # Titles scraped from SCI 2024/2025 tabs (title-only, no subject given) that
    # could not be confidently classified against Art 14/19/20/21/22/32. Send
    # back the case's "Subject" line if you want these checked.
    "RUTU MIHIR PANCHAL vs UNION OF INDIA",
    "VARSHATAI vs THE STATE OF MAHARASHTRA",
    "AMIT KUMAR vs UNION OF INDIA",
    "SUKHDEV SINGH vs SUKHBIR KAUR",
    "TANVI BEHL vs SHREY GOEL",
    "AJAY MALIK vs STATE OF UTTARAKHAND",
    "RAJEEB KALITA vs UNION OF INDIA",
    "RINA KUMARI @ RINA DEVI @ REENA vs DINESH KUMAR MAHTO @ DINESH KUMAR MAHATO",
    "N. Chandrababu Naidu v. Union of India",
    "NOBLE M PAIKADA vs UNION OF INDIA",
    "NAVAS @ MULANAVAS vs STATE OF KERALA",
    "KULDEEP KUMAR vs U.T. CHANDIGARH",
    "SITA SOREN vs UNION OF INDIA",  # likely Art 105/194 legislator-privilege, not core 6
]


def match_filename_key(title_or_name: str) -> str:
    """Normalize a case name for matching against the corpus's stable `filename`
    field (NOT the LLM-generated `title` field, which is known to drift)."""
    s = re.sub(r"[^a-z0-9]+", "_", title_or_name.lower()).strip("_")
    return s


def match_landmark_cases_to_corpus(landmark_cases, all_filenames):
    """
    all_filenames: iterable of corpus filenames (pull from your CSV or the
    current v0 KG's `filename` field — NOT `title`).
    Returns landmark_cases with a `corpus_match_candidates` field added.
    """
    for case in landmark_cases:
        key = match_filename_key(case["name"])
        anchor = key.split("_")[0]
        candidates = [fn for fn in all_filenames if anchor in fn.lower()]
        case["corpus_match_candidates"] = candidates
        case["corpus_match_status"] = (
            "matched" if candidates else "not_found_in_corpus"
        )
    return landmark_cases


if __name__ == "__main__":
    print(f"Total landmark cases: {len(landmark_cases)}")
    from collections import Counter
    by_article = Counter(c["article"] for c in landmark_cases)
    for art in ["14", "19", "20", "21", "22", "32"]:
        print(f"  Art {art}: {by_article.get(art, 0)} cases")
    print(f"\nFlagged for manual review (title unclear): {len(NEEDS_REVIEW)}")
