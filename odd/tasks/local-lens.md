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
- [x] T1 — Safe incremental inventory and exact duplicate detection. Route: delegated bounded writer plus independent verifier (native assessment unassessable). Checks: unittest 8/8 PASS, compileall PASS, parent spot check 8/8 PASS; pytest/Ruff unavailable initially (later both passed). Commit: `682c39d7a296a7108b20c7119d331ec12622edc0` (443 added lines); lint correction `fc3591252d9403d3c7273ffdeefb6ce179f0ea38`. Review: inspect blocked with `empty_candidate_base_ref_required` on root commit; not approved, record unavailable and continue with ordinary checks.
- [x] T2 — Local text/PDF extraction and SQLite FTS5 search. Route: delegated writer, safety corrections, independent verifier. Checks: 18 pytest PASS, Ruff PASS, compileall PASS, parent spot check PASS. Commit: `b2a7b8b4c75968a46fb5e7df1765bd1d6dd3de71` (520 additions, 63 deletions). Review: inspect again blocked with `empty_candidate_base_ref_required`; no approval claimed. Linux descriptor-relative safe traversal; unsupported systems explicitly rejected.
- [x] T3 — CLI, README and integration tests. Route: delegated bounded writer plus independent verifier. Checks: 21 pytest PASS, Ruff PASS, compileall PASS, installed console entry point `locallens --help` PASS, parent end-to-end smoke index/search PASS. Commit: `a24a888759dfe2d070b36fa10084de907dea47b1` (254 additions, 2 deletions). Review: inspect offered a workspace diff of this task document only, not the committed work unit; no native review claimed.
- [x] T4 — Published public source repository and feature branch. Route: parent git/gh state and delivery. Checks: tracked path audit (12 source/config/test/task/README paths, no DB/.venv/personal documents), GitHub repository `PUBLIC`, remote `origin` points to `https://github.com/jos1411/LocalLens.git`, pushed `feat/local-lens`, remote HEAD and README verified. No PR or merge. Completion evidence: final task-state commit follows this update.

## Current progress
B1 and T1–T4 complete. 21 pytest PASS, Ruff PASS, compileall PASS, installed CLI and local index/search smoke PASS. RDD inspect did not freeze any committed work unit; no approval claimed. Running authored total: 443 + 16 + 583 + 256 = 1298 lines in reviewable work-unit commits. Public repository verified on GitHub: `https://github.com/jos1411/LocalLens`, default branch `feat/local-lens`.

## Next step
User can install from the README and try indexing a small non-sensitive local folder. Future work (API, OCR, semantic search, Windows support) requires separate scope and authorization. No PR or merge requested.
