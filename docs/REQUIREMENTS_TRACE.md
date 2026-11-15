# End-to-end requirement trace

Both PDFs were successfully extracted and inspected in full: Main, pages 1–5;
Reference, pages 1–3. Page locations below refer to their PDF pages. This matrix
separates explicit submission requirements from illustrative product ideas.

| Brief location | Requirement or example | Interpretation | Implementation / status |
| --- | --- | --- | --- |
| Main 1, 4 | Mobile-first working prototype; all three layers with a working workflow | Required | Responsive React shell; working digest/alerts, source research and synthetic graph recommendations. Browser visual QA remains unverified. |
| Main 1, 3–4 | Network inside Push/Pull and directly queryable | Required product direction; scope minimum says woven into Push or Pull | Implemented in both digest/category alerts and research; direct recommendations and person search available. |
| Main 2 | Mock portfolio of 15–20 listed companies | Required | 18 companies; real Yahoo identities and price observations verified across the portfolio. Ownership is mock. |
| Main 2 | Handful of research examples, say 3–5; engine generalizes beyond demo set | Required generalization; count phrased approximately | Four selected fixtures; source access verified for TCS and Reliance. Engine accepts other supported symbols and reviewed sources without company-specific answers. Automatic universal source discovery is not implemented. |
| Main 2 | Four backend sources: EOD price/volume, exchange filings, fundamentals, profiles | Required plumbing | Yahoo EOD, both official RSS feeds, retrieved issuer annual reports/results/transcripts, and labeled synthetic profiles. Current RSS windows have no portfolio matches; historical issuer-hosted exchange disclosure is available in explicit replay. |
| Main 2–3 | Configurable-window digest, default 24h | Illustrative in PDF; explicitly requested by user | Implemented with aware timestamp windows, date-only precision handling, priority groups, routine collapse, source citations and freshness/coverage status. |
| Main 2 | Configurable price, volume and announcement triggers | Illustrative in PDF; explicitly requested by user | Price movement and previous-N-observation volume calculations use Decimal; category rules use source disclosures. Threshold evidence and timestamps persist. API monitors stored data; watcher refreshes sources periodically. |
| Main 3 | Incoming manager biography and network overlap | Example, not mandatory checklist | Synthetic career/person matching and explicit second-degree routes work. No fabricated biography or inferred relationship to a real executive; real-person enrichment omitted. |
| Main 3 | Results: revenue/EBITDA/PBT/PAT, QoQ and YoY | Example, not mandatory checklist | Four rows calculated from a real recognized Reliance results table. Gross revenue is labeled as such, not conflated with revenue from operations. Other layouts can be unsupported. |
| Main 3 | Material event → relevant person and why | Example, selected core workflow | Real July 29, 2025 operating-agreement disclosure → synthetic upstream specialist through a labeled second-degree path. |
| Main 3 | Eight Pull outputs | Menu, explicitly not a checklist | Snapshot, trajectory and guidance/actual evidence views prioritized. No invented balance-sheet/cash-quality/bull/bear conclusions. |
| Main 3 | Last four quarters promised versus delivered | Worked example | No unsupported verdict. Current evidence supports some quarterly comparisons; automated temporal promise-to-outcome matching remains a limitation. |
| Main 3; Reference 2 | Pull must use primary reports/transcripts, no broker/news/model knowledge | Required grounding discipline | Only annual reports, company results and transcripts enter financial retrieval. Exact source sentences, page URLs and hashes are validated. Secondary-note exclusion tested. |
| Main 3 | Who should I call / second-degree / diligence / expertise / reconnecting | Illustrative scenario menu | Company/sector-peer relevance, exact names/aliases, direct/two-degree paths, education/role detail and event prompts implemented. No outreach or inferred real connections. |
| Main 4 | Architecture, pipeline linkage, privacy, LLM and cloud choices in writeup | Required writeup topics | ARCHITECTURE.md and DATA_SOURCES.md document local design, boundaries, synthetic provenance, model routing and production requirements. Covering email not yet written. |
| Main 4 | Efficient model routing/caching/chunking | Encouraged, bonus | No model for ingestion/math/graph/PUSH; local FTS5 retrieval; hash-based caches; Hyde only for selected research evidence. |
| Main 5 | Easy-to-try mobile prototype link, public repo, AI build history, covering note/email | Required final deliverables | Local app implemented; deployment, public repository, history export and final submission email remain outside this milestone. |
| Reference 1 | Seventeen announcement categories | Guidance only; may adapt or ignore | Adopted as deterministic navigation categories. Priority is separate from category, including routine results publication notices. Classification can need review; no claim of regulatory materiality. |
| Reference 2–3 | Definitions and financial glossary | Domain guidance | EOD is separate from real-time; QoQ/YoY periods verified; revenue basis/currency/unit retained; missing data is not inferred. |

The current prototype does not claim complete exchange coverage, universal PDF
understanding, production privacy, real-time delivery, or a fully automated
four-quarter management scorecard. These are explicit limitations rather than
mocked functionality.
