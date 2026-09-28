# LocalLens: local file search MVP

## Objective and intent
Build a fully local, read-only-on-user-files folder indexer with incremental indexing, exact duplicate detection, full-text search of text/code/Markdown and text-bearing PDFs, plus a usable CLI. No cloud, Ollama, OCR, semantic models, API, or background daemon in this MVP. User authorized publishing source to a new public `jos1411/LocalLens` repository. Do not publish indexed data or personal files.

## Repository and constraints
Repository root is `Practica Pyton`, isolated with its own Git directory; leave `/home/jose/Proyectos/.git` and siblings untouched. Work on `feat/local-lens`, one writer at a time. Use Python >=3.12, stdlib SQLite FTS5 and hashing, PyMuPDF for PDF, Typer for CLI, pytest and Ruff. Respect PyMuPDF AGPL licensing in documentation. Never scan beyond the explicitly selected root, follow symlinks outside it, index the index DB itself, or mutate source files. Runtime index database is gitignored. Optional dependencies must not silently call remote services.

## Acceptance criteria
- Index a specified local folder; unchanged files are skipped, changed files refreshed, missing files removed only within that indexed root.
- Find exact duplicates using full-content BLAKE2b, report largest files by size, and search indexed text via FTS5 with useful paths and snippets.
- Read text/Markdown/code and text-bearing PDF; unreadable and scanned files do not crash a scan and produce honest status.
- CLI usage and local-only privacy are documented; meaningful deterministic tests and lint pass.
- Source-only public GitHub repository and feature branch are pushed only after checks; user data and DB excluded.

## Delivery and review workload
Forecast: 600–900 authored diff lines, likely above ~400-line review budget. Strategy: feature-branch-chain chosen by user; publish a single feature branch with reviewable work-unit commits; no PR/merge without a further decision. Count actual committed additions/deletions and record slices. RDD switch: on; inspect/assess committed work-unit candidates under native contract. No review is inferred from TODO completion.

## Tasks
- [x] B1 — Restored delegation in this project's Git repository. Check: read-only `gentle-ai-explore` launched and confirmed root and branch. No commit (environment unblock, not source work).
- [x] T1 — Safe incremental inventory and exact duplicate detection. Route: delegated bounded writer plus independent verifier (native assessment unassessable). Checks: unittest 8/8 PASS, compileall PASS, parent spot check 8/8 PASS; pytest/Ruff unavailable (not run). Commit: `682c39d7a296a7108b20c7119d331ec12622edc0` (443 added lines). Review: inspect blocked with `empty_candidate_base_ref_required` on root commit; not approved, record unavailable and continue with ordinary checks.
- [~] T2 — Add local text/PDF extraction, SQLite FTS5 indexing/search with tests. Route: delegated bounded writer (multiple non-trivial files). Checks: pytest focused, Ruff. Commit: pending. Review: pending.
- [ ] T3 — Expose indexing/search/duplicates/largest via CLI, write README and integration tests. Route: delegated bounded writer (multiple non-trivial files). Checks: full pytest, Ruff, CLI smoke. Commit: pending. Review: pending.
- [ ] T4 — Publish source-only public repository and feature branch after verifying ignored/private paths. Route: parent git/gh state and delivery. Checks: remote identity, tracked-file audit, push outcome. Commit: n/a.

## Current progress
B1 complete. T1 implemented and committed; 8 unit tests pass, compileall passes, independent verifier and parent spot check observed. Native inspect could not establish review for the root commit (empty base ref required); no review approval claimed. Running authored total: 443 lines. T2 in progress on `feat/local-lens`.

## Next step
Implement T2 with PDF extraction, FTS5 search and deterministic tests; install isolated tooling/dependencies when possible, then rerun all checks. Keep DB and user files untracked.
