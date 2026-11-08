# Update performance implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline, task-by-task.

Goal: speed computation and backup without changing research outputs, and distinguish superseded failures from a new failure.
Architecture: optional cached date axes, model-local immutable numeric matrix, fast interoperable gzip, pure browser job reconciliation.
Tech Stack: existing Python/NumPy/SQLite and vanilla JavaScript; no dependencies.
Spec: docs/superpowers/specs/2026-11-08-update-performance-design.md

## Global Constraints

Local branch only, no push/deploy. No new market assumptions, fewer samples, stale classification fallback or credential storage in repo/log/chat. User manages regenerated credential; verify Worker only through read-only requests.

## Tasks

### Task 1: Shared model axes and reconciliation indexes

Files marketlab/analytics.py, marketlab/service.py; tests/test_update_performance.py; ignored logs/local-research benchmark baselines.
Consumes identical rows/calendar/settings; produces event_outcome(..., *, dates=None), model-local _dates/_vectors, same outputs.
- [ ] Save original model/estimate/validation hash and reconciliation output; repeated timings, cProfile evidence.
- [ ] Write tests for supplied date axis with gaps/adjustments, and model parity against original outcomes; RED missing keyword.
- [ ] Build axis once per model, reuse dense float64 vectors preserving stable argsort and maturity cutoff. Reconcile maps date->index and reuses per-symbol dates without bypassing corrections.
- [ ] GREEN targeted and full Python suites; identical baseline digest. Commit.

### Task 2: Faster compatible backup

Files scripts/state_archive.py; tests/test_state_archive.py.
Produces pack_state(filename, root=Path('data'), compresslevel=1), existing CLI pack/restore still work.
- [ ] Write failing roundtrip/inclusion/exclusion test for new function. RED missing function.
- [ ] Preserve tar.gz members/data prefix, source bytes, exclusions and restore checks; gzip level1 default. Do not prune immutable raw history.
- [ ] GREEN roundtrip/security tests; benchmark level1 versus9 on the same real cached source files. Commit.

### Task 3: Honest cloud job display

Files web/cloud.js, web/app.js; tests/cloud-client.test.mjs.
Produces reconcilePublishedJob(job, publication), pure function.
- [ ] Tests RED: older failed market/all job plus newer publication becomes superseded retaining prior failure; unknown dates, equal dates, social and running unchanged; failed progress label no false completion.
- [ ] Call helper after static publication load, preserve original cloud references; superseded message retains prior failure context. Error fraction says failure and bar does not imply100% success.
- [ ] GREEN full Node+Python suites, browser markup check if available; commit, independent final review and one needed fix pass.

## Review Focus

Floating point/stable ordering parity, sparse date axes and revised outcomes; model array lifetime with immutable input assumptions; archive member names and links; invalid and timezone-free timestamps; old social job never masked by market publication; no accidental credential output or remote deployment.
