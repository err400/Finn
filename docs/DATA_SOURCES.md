# Verified sources and access decisions

All sources were investigated from this environment before their adapters were
implemented. Source-accessibility results are in
`verification/source-accessibility.json`. HTTP 200 alone was not accepted as
success: RSS was parsed, PDFs were checked and text was extracted. For example,
BSE's old terms/robots URLs returned an HTML application shell, and Reliance's
robots URL returned a rejection page; neither was treated as a valid policy file.

## Exact datasets

| Dataset | Actual source | Stored demonstration |
| --- | --- | --- |
| Daily OHLC, adjusted close and volume | `https://query1.finance.yahoo.com/v8/finance/chart/{NSE_SYMBOL}.NS` with explicit interval/date parameters | 18 companies; January 2025 plus July–November 2026 windows. Exact URLs, hashes, dates and counts are in `verification/source-manifest.json`. |
| NSE announcements | `https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml` | Valid recent RSS retrieved; four entries in the inspected window, zero portfolio matches. |
| BSE announcements | `https://www.bseindia.com/data/xml/announcements.xml` | Valid recent RSS retrieved; one entry in the inspected window, zero portfolio matches. A non-portfolio attachment was also genuinely retrieved during accessibility testing, not mislabeled as a portfolio disclosure. |
| TCS annual report | `https://www.tcs.com/content/dam/tcs/investor-relations/financial-statements/2024-25/ar/annual-report-2024-2025.pdf` | 336 parsed PDF pages; actual publication date unknown. |
| TCS earnings-call transcript | Exact company URL in `backend/app/fixtures/primary_sources.json` and manifest | 25 parsed PDF pages; call date April 10, 2025; publication date unknown. |
| TCS exchange disclosure | `https://www.tcs.com/content/dam/tcs/pdf/discover-tcs/investor-relations/corporate-actions/2024-25/SE-Letter-CS.pdf` | Two parsed pages; signed July 11, 2024, with a later effective appointment date in the document. Not assigned a guessed exchange publication timestamp. |
| Reliance annual report | `https://www.ril.com/sites/default/files/2025-08/RIL-Integrated-Annual-Report-2024-25.pdf` | 146 parsed pages; issuer CDN URL redirects here; publication date unknown. |
| Reliance quarterly results | `https://www.ril.com/sites/default/files/2025-04/25042025_Media_Release_RIL_Q4_FY2024_25_Financial_and_Operational_Performance.pdf` | 44 parsed pages; issuer index publication date April 25, 2025; quarter ended March 31, 2025. |
| Reliance call transcript | `https://www.ril.com/sites/default/files/2025-04/Q4_FY2024_25_Transcript.pdf` | 42 parsed pages; call date April 25, 2025; publication date unknown. |
| Reliance historical announcement | `https://www.ril.com/sites/default/files/2025-07/SE_29072025.pdf` | Two parsed pages; July 29, 2025 publication date corroborated by issuer archive and signed filing. Time unknown. Explicit replay only. |
| Investor network | `backend/app/fixtures/network.json` and `app/db/network_seed.py` | Ten entirely fictional people, career/education records and explicit synthetic relationship edges. No LinkedIn/private-profile scraping. |

The manifest is generated from the actual local database, not a list of intended
integrations. Initial and current refresh reports preserve each dataset's exact
provider parameters. Financial source blobs stay in ignored local storage;
metadata manifests do not grant redistribution rights.

## Terms, throttling and limitations

Yahoo's endpoint was accessible directly, so a small HTTP adapter is used instead
of adding pandas/yfinance merely to retrieve the same chart dataset. The
[yfinance project](https://ranaroussi.github.io/yfinance/) itself notes the
personal-use restriction on Yahoo data. This is a local educational prototype,
not a public commercial market-data API. Public or commercial use needs an
appropriate source-rights decision or replacement licensed provider.

NSE's [website terms](https://www.nseindia.in/static/nse-terms-of-use) restrict
systematic automated website collection. FINN does not call undocumented website
APIs, impersonate a browser, harvest cookies or bypass bot controls. The
[official RSS page](https://www.nseindia.in/static/rss-feed) explicitly offers RSS
subscriptions and identifies the feed used here. The implementation uses that
syndication channel conservatively, not a historical scraping mechanism.
BSE access is similarly restricted to its published RSS and exact attachments;
no unrestricted BSE historical endpoint is claimed or reverse-engineered.

[TCS's disclaimer](https://www.tcs.com/who-we-are/legal/legal-disclaimer) and
[Reliance's legal notice](https://www.ril.com/legal-notice) allow limited personal
use with restrictions on redistribution. Exact reviewed PDF retrieval is used,
not crawling or republishing their archives. Retrieved copyright notices remain
intact. The data endpoints are local-only and raw files are excluded from git.
No claim is made that a public assessment deployment can redistribute these
sources without reviewing rights. Infosys IR timed out, so its PDFs were not
claimed as ingested; Screener is not used as financial evidence or scraped.

The single-host fetcher spaces requests to each origin by at least two seconds,
uses conservative TTLs, honors 429 cooldowns including Retry-After dates, and
bounds downloads, timeouts, retries and redirects. Published RSS is checked at
most once per five-minute refresh window; actual failures are negative-cached to
avoid repeated per-holding requests. Server errors do not erase
verified records. A stale capture is labeled and retains its original retrieval
time. Jobs are idempotent and serialized across local API/CLI processes.

Reported publication timestamps are normalized to UTC, with offset-free exchange
RSS timestamps interpreted as IST. Date-only issuer evidence stays date-only.
Reporting periods and call dates are stored separately. EOD trade dates use the
exchange timezone; fetch time is not a price or filing publication time.

## Actual connected verification

`verification/workflows.json` records the exact triggering values and source
snapshots for real-data price and volume alerts and the July 2025 replay category
alert. Demonstration rules were paused after checking them. `hyde-synthesis.json`
records a successful real Hyde call with ten retrieved passages and six validated
model-selected source statements. No private key or contact graph was included.

The first free-form quotation response failed citation validation and was
withheld. The adapter was changed to model selection of source sentence IDs,
then tested successfully without weakening the exact-evidence check.


### Announcement archive expansion (16 November 2026)

The reviewed catalog now contains 18 genuine Reliance issuer-hosted exchange disclosures, all successfully downloaded and PDF-identity checked. Dates come from the issuer corporate-announcements index at https://www.ril.com/investor/resource-center/corporate-announcements and its `?page=17` archive, inspected directly. Stored dates span 29 July 2025–13 November 2026. Exact document URLs and retrieval outcomes are recorded in `docs/verification/archive-backfill.json`. Redirected final URLs are retained with raw snapshot provenance.

This is selected coverage of **one of 18 portfolio companies**, not a complete portfolio archive or continuous coverage between those dates. RSS has a short window and cannot backfill ten years. `mode=all` includes both current-source and historical records without changing each record's historical label. `archive_coverage` exposes per-company imported counts. Further issuer integrations or a licensed exchange-history provider are needed for comprehensive coverage.

The live custom-window verification returned 18 events: 12 for review and 6 routine disclosures. See `docs/verification/custom-archive.json`. No additional financial observations were generated.
