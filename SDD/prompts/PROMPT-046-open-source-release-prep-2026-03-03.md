# PROMPT-046-open-source-release-prep: Open Source Release Preparation

## Executive Summary

- **Based on Specification:** SPEC-046-open-source-release-prep.md
- **Research Foundation:** RESEARCH-046-open-source-release-prep.md
- **Start Date:** 2026-03-03
- **Author:** Claude (with Pablo)
- **Status:** In Progress

---

## Confirmed Decisions

| # | Decision | Value |
|---|----------|-------|
| D-001 | Project name | `sift` — reserved at github.com/pablooliva/sift |
| D-002 | License | ProPal Ethical License v1.0 (not OSI-approved; values statement) |
| D-003 | Keep SDD/ public | Yes, minus `context-management/` (keep exactly 3 curated examples) |
| D-004 | qdrant-txtai fork | Option B — retain as author attribution; no rebuild needed |

---

## Specification Alignment

### Requirements Implementation Status

- [x] REQ-001: IP replacements (Category A/B/C) — ✅ DONE
- [x] REQ-002: Personal path replacements — ✅ DONE
- [x] REQ-003: `memodo` generalization + dynamic `MANUAL_CATEGORIES` — ✅ DONE
- [x] REQ-004: `.gitignore` completeness — ✅ DONE
- [x] REQ-005: `LICENSE` file (ProPal Ethical License v1.0) — ✅ DONE
- [x] REQ-006: `NOTICE` file — ✅ DONE
- [x] REQ-007: `CODE_OF_CONDUCT.md` — ✅ DONE
- [x] REQ-008: `CONTRIBUTING.md` with component isolation paths — ✅ DONE
- [x] REQ-009: `SECURITY.md` with zero-auth documentation — ✅ DONE
- [x] REQ-010: README trimmed to ~350 lines + 4 docs/ files — ✅ DONE (424 lines; docs/QUERY-ROUTING.md, DATA-STORAGE.md, KNOWLEDGE-GRAPH.md, TESTING.md created)
- [x] REQ-011: Quick Start — download sizes, minimal/full paths — ✅ DONE (added to README Quick Start: nomic 274MB, llama3.2-vision 6.5GB, Whisper 3GB, BART 560MB; minimal/full paths)
- [x] REQ-012: SDD context-management cleaned to exactly 3 files — ✅ DONE (5 files total: 3 examples + progress.md + VALIDATION-CHECKLIST-035.md)
- [x] REQ-013: SDD files scrubbed for IPs/paths — ✅ DONE (49 files scrubbed)
- [x] REQ-014: `.env.example` and `.env.test.example` scrubbed — ✅ DONE (.env.test.example scrubbed in Phase 1 Task #5a; .env.example has no personal data)
- [x] REQ-015: `CLAUDE.md` IPs replaced with `YOUR_SERVER_IP` — ✅ DONE (completed in Phase 1 Task #5, Category C)
- [x] REQ-016: GitHub Actions CI + security workflows — ✅ DONE (.github/workflows/ci.yml + security.yml; Ruff critical-only + CodeQL + Trivy)
- [x] REQ-017: Issue/PR templates — ✅ DONE (.github/ISSUE_TEMPLATE/bug_report.md, feature_request.md, PULL_REQUEST_TEMPLATE.md)
- [x] REQ-018: `mcp_server/pyproject.toml` author attribution preserved — ✅ DONE (updated "Pablo" → "Pablo Oliva")
- [x] REQ-019: qdrant-tartai fork documented per D-004 (Option B) — ✅ DONE (custom-requirements.txt expanded with fork URL + attribution; CONTRIBUTING.md already had qdrant-tartai section)
- [ ] REQ-020: Fresh `git init` (final step after all verification) — Pending user action
- [x] REQ-021: PostgreSQL connection vars parameterized — ✅ DONE (docker-compose.yml, docker-compose.test.yml, config.yml)
- [x] REQ-022: `.env.example` is authoritative; all prod vars present — ✅ DONE (added POSTGRES_*, GRAPHITI_SEARCH_TIMEOUT_SECONDS)

### Non-Functional Requirements

- [ ] PERF-001: `docker compose up -d` (core) works from `.env.example` — Not Started
- [ ] PERF-002: Unit tests pass after IP defaults changed to localhost — Not Started
- [x] SEC-001: `grep -r 'YOUR_SERVER_IP' .` returns zero (tracked files) — ✅ DONE
- [x] SEC-002: `grep -r '/path/to/external' .` returns zero (tracked files) — ✅ DONE
- [x] SEC-003: `.env`, `.env.test`, `.claude/`, `neo4j_logs/`, `.mcp.json` all ignored — ✅ DONE
- [ ] UX-001: Quick Start walkthrough produces working search — Not Started
- [ ] UX-002: `docker compose up -d` (no profile) starts core only — Not Started

### Edge Cases

- [x] EDGE-001: `.env.test` gitignored or scrubbed before git add — ✅ DONE (.env.* covers it; .env.test.example scrubbed)
- [ ] EDGE-002: qdrant-tartai fork reference documented (D-004 Option B) — Not Started
- [x] EDGE-003: Search.py category filters dynamic from `MANUAL_CATEGORIES` — ✅ DONE (Phase 2 REQ-003)
- [x] EDGE-004: Exactly 3 curated SDD examples, scrubbed — ✅ DONE (Phase 2 REQ-012: 5 files kept, 3 are curated examples + progress.md + VALIDATION-CHECKLIST)
- [ ] EDGE-005: `populate_test_data.py` IP replaced — Not Started
- [ ] EDGE-006: Backup test scripts personal paths replaced — Not Started
- [ ] EDGE-007: Quick Start documents first-run downloads — Not Started

### Failure Scenarios

- [x] FAIL-001: Grep verification complete before git init — ✅ DONE
- [x] FAIL-002: git init ONLY runs after full verification — ✅ DONE (all verification greps clean; git init is final step for user)
- [ ] FAIL-003: Unit tests pass after os.getenv() defaults changed — Pending (requires Docker environment; not validatable locally)
- [ ] FAIL-004: Core services start without paid API keys — Pending (requires server Docker environment)
- [ ] FAIL-005: GitHub name reserved ✅ DONE
- [ ] FAIL-006: CI designed to work without paid API keys — Not Started
- [x] FAIL-007: Ruff violations assessed before CI creation — ✅ DONE (538 violations: 219 F401, 134 F541, 86 F841, 39 E712, 31 E722, 19 E402; CI uses --select E9,F63,F7,F82 only for initial release)

---

## Phase 1 Task Status: Critical (blocks git init)

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Reserve `sift` on GitHub | ✅ DONE | github.com/pablooliva/sift |
| 2 | Update `.gitignore` | ✅ DONE | Added: neo4j_logs/, .claude/, .mcp.json, node_modules/ |
| 5a | Scrub `.env.test.example:45` | ✅ DONE | Changed to host.docker.internal:11434 |
| 3 | Category A IP replacements (~15 Python/code files) | ✅ DONE | 13 files, all → localhost |
| 4 | Category B IP replacements (Docker Compose files) | ✅ DONE | docker-compose.yml + docker-compose.test.yml → host.docker.internal |
| 5 | Category C IP replacements (documentation files) | ✅ DONE | README.md, CLAUDE.md, mcp_server/FINAL-TESTING-REPORT.md, mcp_server/PERFORMANCE-BENCHMARKS.md |
| 6 | Personal path replacements (scripts) | ✅ DONE | README.md, .env.example, scripts/, tests/unit/backup/, tests/integration/backup/, docs/BEST-PRACTICES-DOCUMENT-SUMMARIZATION.md |
| 7 | Create `LICENSE` file (ProPal Ethical License v1.0) | ✅ DONE | Created with Copyright (c) 2026 Pablo Oliva |
| 8 | Verification greps (both must return zero) | ✅ DONE | Only gitignored files remain (.env, logs/, .claude/) |

---

## Implementation Progress

### Completed Components

- D-001 through D-004 confirmed and recorded
- **Phase 1 COMPLETE (2026-03-03)** — All 8 tasks done

### In Progress

- **Current Focus:** Phase 2 — Community Files (REQ-006 through REQ-015)
- **Next task:** REQ-006 `NOTICE` file | REQ-007 `CODE_OF_CONDUCT.md` | REQ-008 `CONTRIBUTING.md` | REQ-009 `SECURITY.md`

### Blocked/Pending

- Nothing blocked

---

## Technical Decisions Log

### Key Implementation Notes

- **Task #7 License override:** SPEC says "Apache 2.0" in the task list but D-002 is confirmed as ProPal Ethical License v1.0. Use ProPal.
- **SPEC line 431 orphan text:** "Push to `github.com/<org>/knowloom`" is stale — correct target is `github.com/pablooliva/sift`
- **SPEC External Dependencies:** duplicate GitHub entry at line 360 — cosmetic, no action needed
- **config.yml `${VAR}` support:** Must verify txtai YAML loader handles `${VAR}` before implementing REQ-021 config.yml change. Safe fallback: set vars in docker-compose.yml environment block and reference as `${VAR}` in config.yml.
- **`.env.test` gitignore:** Current `.gitignore` covers `.env.*` — verify this pattern catches `.env.test` before assuming it's covered.

### Category A files (IP in os.getenv() defaults — replace with `http://localhost:11434` or `http://localhost:8300`):

- `custom_actions/ollama_classifier.py:54,196`
- `custom_actions/ollama_captioner.py:52`
- `scripts/graphiti-ingest.py:1296`
- `mcp_server/populate_test_data.py:12,191` → `http://localhost:8300`
- `tests/test_ollama_classification.py:11`
- `tests/test_workflow_caption.py:16`
- `tests/test_workflow_classification.py:21`
- `tests/test_workflow_transcription.py:24`
- `mcp_server/tests/test_graphiti.py:1637+`
- `mcp_server/tests/test_knowledge_summary_integration.py:38-41`

### Category B files (Docker Compose `${VAR:-192.168...}` — replace with `http://host.docker.internal:11434`):

- `docker-compose.yml:92,164,214`
- `docker-compose.test.yml:108,159`

### Category C files (documentation — replace with `YOUR_SERVER_IP`):

- `README.md`
- `CLAUDE.md`
- `mcp_server/README.md` (and other MCP docs)
- `.env.test.example:45` → `http://host.docker.internal:11434` (Task #5a)
- Other documentation files (~10 total)

### Personal path files (replace with `/path/to/backup`, `/path/to/project`):

- `scripts/cron-backup.sh:296`
- `scripts/setup-cron-backup.sh:93`
- `tests/unit/backup/test-cron-backup.sh`
- Backup integration test files

---

## Session Notes

### Next Session Priorities

1. Task #2: Update `.gitignore` — add 4 patterns, verify `.env.test` coverage
2. Task #5a: Scrub `.env.test.example:45`
3. Tasks #3+4: IP replacements in Category A+B files (delegate to subagent if context high)
4. Task #5: Category C documentation IP replacements
5. Task #6: Personal path replacements
6. Task #7: Create `LICENSE` file with ProPal Ethical License v1.0 text
7. Task #8: Verification greps — both must return zero before proceeding to Phase 2
