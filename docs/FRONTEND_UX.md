# FINN frontend: interaction and verification

The frontend is an investor workspace rather than a chat dashboard. Its four
primary destinations are Briefing, Portfolio, Research and Alerts. Network
recommendations appear where a filing or research question gives them purpose;
there is no primary contact-list destination.

## Decisions

- A compact desktop sidebar and mobile bottom navigation replace the oversized
  landing-page hero. One page heading, a bounded content width and a restrained
  paper/forest palette establish a clear hierarchy. System sans-serif text and
  local serif display typography require no remote font or image service.
- Important event cards answer what happened, why it might matter, where the
  evidence is, and who could add context. Category-based review prompts are
  distinguished from claims of financial impact. Full source text and profile
  reasoning use drawers so the feed stays scannable.
- Portfolio figures are computed from stored data: company/sector counts, EOD
  coverage, primary-document coverage, actual closes and comparable changes.
  The backend computes percentages with Decimal and never compares providers
  or non-comparable dates. There are no fabricated allocation/valuation charts.
- Portfolio row → company drawer → research carries the selected ticker forward.
  Navigation preserves previously visited screens and research results. Opening
  research never automatically spends on an LLM call.
- Research separates Brief, Financial comparisons and Evidence. Missing evidence,
  unavailable synthesis, unsupported tables and historical reporting periods have
  distinct states. Source citations retain the actual PDF page. Unknown values
  read “Unavailable,” not zero or a percentage with a missing value.
- A new watch-rule drawer contains actual persisted settings. Pause switches use
  the backend-confirmed response and are protected against duplicate changes.
  Historical evaluation is explicit. Trigger receipts show formula, threshold,
  observation date, evaluation time, source and available baseline observations.
- Refresh sources performs a real bounded exchange-source check. Reads remain
  non-blocking; existing verified data stays visible during an update or failure.
  The local backend schedules source updates every five minutes, reuses fresh
  checks, skips redundant EOD downloads, and negative-caches failed requests.
  An overdue cache and an actual provider error are separate conditions.
- All app data refreshes use cancellable requests and retain the last successful
  view on a failed retry. Loading does not turn unknown coverage into a claimed
  zero. Financial data is never generated to decorate an empty state.

## Responsive and accessibility behavior

Desktop uses a bounded sidebar workspace and contextual side panels. At smaller
widths those panels stack in reading order; below 760 CSS pixels navigation moves
to a four-item bottom bar with safe-area padding. Small portfolio rows retain
observation dates and stale/missing labels. Inputs use 16px text on mobile,
controls have practical touch targets, long evidence wraps and reduced-motion
preferences are respected.

Drawers trap keyboard focus, support Escape, restore focus and handle nested
introduction drawers without closing the underlying company context. Research
result tabs support arrow/Home/End keys. Forms have labels and validation; errors
are announced and inputs survive failed saves. Skip navigation preserves the
current app route. Keyboard control outlines remain; the accidental blue outline
around the whole main workspace was removed after user screenshot review.

## Verification and boundaries

- Component integration tests exercise mobile navigation at 390 CSS pixels and
  desktop navigation at 1440, portfolio filtering/details, ticker handoff, replay,
  custom IST date windows, evidence drawers, synthetic introduction paths, saved
  rule settings, pause persistence, evaluation receipts, research citations,
  missing evidence, stale-data recovery and actual source-refresh requests.
- These tests run in jsdom. They test interactions and contracts, not rendered
  browser geometry or pixel-perfect layout; no mobile browser paint test is
  claimed. The user's desktop screenshots were inspected during implementation.
- Direct Chrome automation was denied by computer-use permissions. Actual mobile
  visual inspection remains a manual follow-up; CSS breakpoints alone do not
  prove absence of every device-specific layout issue.
- Live local API checks are recorded in `verification/frontend-live.json` and
  source-refresh checks in `verification/source-refresh.json`. They use real
  stored observations, actual citations, a real source-checked Hyde result and a
  labeled validation rule that is paused after verification.
- Fixture data in frontend tests is explicitly synthetic and is not injected
  into the running app. The app has no production fallback data or fake controls.
