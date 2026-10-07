# Stage two implementation plan

Spec: ../specs/2026-10-08-stage-two-design.md
User authorization: finish inline locally; final acceptance only unless a real decision is required.

## Global constraints

Existing local/research-upgrade checkout; no push, merge, Actions or deployment. Keep original rankings and archived policy reports intact. Data under data/local-research-dev; GET reads only. Immutable source observations, conservative available_at, no historical hindsight features. ETF revenue N/A. Missing values are never zero. Windows PowerShell equivalents for skill bookkeeping scripts.

## Task 1: Official parsers

Files: marketlab/official.py, tests/test_official.py.
Produces: parse_source(source, payload, requested_date=None) -> normalized rows with symbol, key, data_date/period, published_at, unit, values.
Write tests first: T86 exact names/duplicate symbols/date; MI_MARGN validated group spans/repeated names; revenue ROC periods/invalid percentages; announcement normalized keys/070004/invalid time; exdates. Run unittest discovery test_official.py: Expected RED import failure. Implement strict pure parsing, rerun: Expected GREEN. Commit parser task.

## Task 2: Immutable observations and features

Files: marketlab/official_store.py, tests/test_official_store.py.
Consumes Task 1 rows + TwseClient evidence; produces OfficialStore.ingest/query/summary/detail/features.
Tests first: dedup preserves first_seen; corrections append; published cutoff; cached fetch time; future data_date excluded; complete five-session volume; stale/missing/ETF; raw evidence reference retained. Expected RED then GREEN. SQLite own tables with append-only rows. Point-in-time latest version per data key and conservative availability. Commit task.

## Task 3: Collectors and local API

Files: marketlab/official_jobs.py, marketlab/server.py, tests/test_official_jobs.py.
Consumes Tasks 1/2; produces five-source update coordinator with OS-owned lock, persisted per-source health, recovery; GET /api/official[?symbol=&id=], /api/official/job, /api/shadow; POST /api/official/update accepts empty object. Date from saved latest snapshot, five recent actual sessions for T86/margin, TTL cached evidence honored. Individual failure retains old rows. Tests first for failure isolation, concurrent update rejection, recovery, GET read-only, body/host guards. Expected RED then GREEN, existing server tests pass. Commit task.

## Task 4: Frozen shadow experiments

Files: marketlab/shadow.py, tests/test_shadow.py.
Consumes OfficialStore.features + saved snapshot candidates/calendar + Stage 1 simulation; produces immutable definition hash and read-only report.
Tests first: fixed deterministic ranking, same cohort, no future features, late entry exclusion, terminal-only comparison, rolling purge disjoint dates, day weighting/block bootstrap seed/min30, insufficient data. Expected RED then GREEN. Freeze definition file once at authorized update time, reject conflicts. Warmup30/purge10/test10, block10/bootstrap2000/seed20261008. Use saved original candidate rank + original policy outcomes; no promotion. Commit task.

## Task 5: Local research UI

Files: web/official.js, web/app.js, web/index.html, web/style.css, server static map; tests/official.test.mjs.
Consumes Tasks 3/4 report contracts; produces source summary, update/job controls, detail context and shadow comparison section. Escape text, source links only official HTTPS allowlist, async generation guards, static mode no requests. Tests first markup missing/zero/stale/ETF/escaping/static/races; RED then GREEN. Existing Node tests remain green. Commit task.

## Task 6: Real data and final verification

Run full Python/Node suites, official update against local data only, restart loopback server, GET smoke and desktop/mobile UI check if browser runtime available. Save evidence logs and user acceptance guide including uncertainty. Expected five real sources or honest per-source failure; current sample status insufficient. Commit documentation. Independent final review, one Important/Critical fix pass with failing regression tests then full suite. Keep local branch/server.

## Review Focus

Check cross-source unit mismatches; duplicate credit columns; timezone and correction leakage; early/later-created snapshot entry assumptions; no mature-return leakage in selection; missing price sessions; rolling horizon overlap; joint eligible cohort and selected-trade denominator; stale API versus historical cutoff; API GET writes/network; startup recovery and locks; static mode and detail request races; honest insufficient-data presentation. Do not treat synthetic test success as empirical forecasting improvement.
