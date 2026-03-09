# SDD Progress

## Current State

- **Feature:** SPEC-046: Open Source Release Preparation
- **Status:** ✅ IMPLEMENTATION COMPLETE — sift is live at https://github.com/pablooliva/sift
- **Research document:** `SDD/research/RESEARCH-046-open-source-release-prep.md`
- **Critical review:** `SDD/reviews/CRITICAL-RESEARCH-046-open-source-release-prep-20260301.md`
- **Research compaction:** `SDD/prompts/context-management/research-compacted-2026-03-01_16-35-54.md`
- **Planning compaction:** `SDD/prompts/context-management/planning-compacted-2026-03-03_11-52-17.md`
- **Model:** Claude Opus 4.6

---

## Research Phase ✅ COMPLETE (2026-03-01)

### Summary

7 research areas investigated via 5 parallel agents, plus critical review and post-review updates:

1. **Security Audit** — 180+ hardcoded IPs, 3 .gitignore gaps; Neo4j password in history is moot (fresh git init)
2. **Repository Structure** — 425 SDD files (120 removable context-management), hardcoded `memodo` category, 2,146-line README → ~350
3. **Licensing** — Apache 2.0 recommended; Neo4j GPL v3 no copyleft concern (separate container)
4. **Naming** — Top pick: **knowloom** (GitHub + PyPI available)
5. **Documentation** — Need LICENSE, NOTICE, CODE_OF_CONDUCT.md, CONTRIBUTING.md; move ~1,400 lines from README to docs/
6. **CI/CD** — Day 1: Ruff + unit tests + Trivy/CodeQL; GHCR over Docker Hub
7. **Docker** — Don't publish GPU image; Compose profiles; CPU-only override

### Post-Research Updates

- **Release strategy:** Fresh `git init` (§8) — eliminates git history concerns, secret rotation downgraded to recommended
- **Critical review verified:** `.env` never committed, API keys never in git, only Neo4j password in one compaction file (moot with fresh init)
- **Critical review gaps for SPEC:** Application security posture (zero auth), first-run UX (~10+ GB model downloads undocumented), name reservation timing

### Effort Estimate (Revised)

| Phase | Effort |
|-------|--------|
| Phase 1 (Critical — blocks release) | 3-5 hours |
| Phase 2 (High — required before release) | 8-12 hours |
| Phase 3 (Medium — recommended for launch) | 3-5 hours |
| **Total pre-launch** | **14-22 hours** |

### Resolved Questions

- [x] Verify `.env` never committed — **CONFIRMED**: `git log --all -- .env` returns nothing
- [x] Git history secret scan — **MOOT**: fresh `git init` eliminates all history
- [x] Final decision: project name — **sift** (D-001 confirmed 2026-03-03) — reserved at github.com/pablooliva/sift
- [x] Final decision: license — **ProPal Ethical License v1.0** (D-002 confirmed 2026-03-03)
- [x] Final decision: keep SDD/ public — yes, minus context-management/ (D-003 confirmed 2026-03-03)
- [x] Final decision: qdrant-txtai fork — Option B, retain attribution (D-004 confirmed 2026-03-03)

---

## Planning Phase ✅ COMPLETE (2026-03-01)

### Specification Created

- **Document:** `SDD/requirements/SPEC-046-open-source-release-prep.md`
- **Status:** Draft — ready for user review and approval

### Key Decisions Required (D-001 through D-004)

Before implementation begins, the following must be resolved:

| # | Decision | Recommendation |
|---|----------|---------------|
| D-001 | Project name | `sift` ✅ CONFIRMED 2026-03-03 |
| D-002 | License | ProPal Ethical License v1.0 ✅ CONFIRMED 2026-03-03 |
| D-003 | Keep SDD/ public? | Yes, minus `context-management/` (keep 3 curated examples) ✅ CONFIRMED 2026-03-03 |
| D-004 | qdrant-txtai fork | Option B: retain as author attribution ✅ CONFIRMED 2026-03-03 |

### Critical Review Gaps Incorporated into SPEC

- **Application security posture** (zero auth) → `SECURITY.md` moved from Phase 4 to Phase 2 (REQ-009)
- **First-run UX** (~10 GB downloads undocumented) → Added to README Quick Start (REQ-011)
- **Name reservation timing** → Phase 1 Day 1 action, before all other work (FAIL-005)
- **Effort estimates revised** → 20-28 hours (was 14-22, +30% buffer from critical review)
- **PostgreSQL credentials** → Phase 2 (moved up from Phase 3)
- **SDD context-management** → Keep 3 curated examples for Blog Post 8 (EDGE-004)

### Critical Review of SPEC-046

- **Review document:** `SDD/reviews/CRITICAL-SPEC-open-source-release-prep-20260301.md`
- **Status:** All 14 findings addressed and applied to SPEC-046

**Key changes made to SPEC-046:**
- Phase 1 grep check now valid: documentation IP scrubbing (Category C) moved from Phase 2 Task #23 into Phase 1 as Task #5
- PostgreSQL credential parameterization definitively assigned to Phase 2 (REQ-021 added)
- `.env.test` added to REQ-004, SEC-003, and .gitignore list
- `MANUAL_CATEGORIES` format specified in REQ-003 (comma-separated, matches existing document_processor.py parsing)
- Docker Compose profiles moved from Phase 4 to Phase 3 Task #34 (required by PERF-001 and UX-002)
- REQ-012/EDGE-004 aligned: "exactly 3" curated SDD examples
- REQ-019 extended with D-004 migrate-option downstream impacts (wheel, old fork URL, CONTRIBUTING.md)
- UX-001 reframed as testable (documented steps with time estimates, not "15-30 minutes")
- RISK-003 elevated to HIGH; RISK-006 extended with wheel file concerns
- FAIL-007 added for Ruff large-scale lint violations
- REQ-009 extended with GitHub secret scanning and HTTPS/TLS documentation requirement
- REQ-008 extended with contributor component isolation documentation
- REQ-011 strengthened: local Ollama alternative as first-class Quick Start option with minimal/full paths
- Effort estimates updated: 23-32 hours total (was 20-28)

### SPEC Refinement (2026-03-02)

Added three requirements based on config management review:

- **REQ-001 tightened**: Python `os.getenv()` defaults → `http://localhost:11434`; Docker Compose `${VAR:-}` defaults → `http://host.docker.internal:11434` (containers can reach host via extra_hosts mapping)
- **REQ-021 expanded**: Full PostgreSQL parameterization — all 5 vars (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) converted to `${VAR:-default}` in docker-compose.yml (postgres service + MCP service), docker-compose.test.yml, and config.yml connection string
- **REQ-022 added**: `.env.example` is the sole config mechanism (Option A — no separate app.yml); every consumed env var must appear in .env.example with generic default + comment; gaps to close: `POSTGRES_HOST/PORT/USER/DB`, `GRAPHITI_SEARCH_TIMEOUT_SECONDS`

### Critical Review (2026-03-03)

Review document: `SDD/reviews/CRITICAL-SPEC-open-source-release-prep-20260303.md`
Status: All 3 HIGH findings applied to SPEC. MEDIUM/LOW items addressed inline.

**HIGH findings resolved:**
- **FINDING-001**: `.env.test.example` line 45 has personal IP — added Phase 1 Task #5a + updated REQ-014
- **FINDING-002**: REQ-021 `config.yml` `${VAR:-default}` unsupported by Python — changed to `${VAR}` only with pre-implementation check note
- **FINDING-003**: D-004 missing from Open Decisions table — added (recommend Option B: retain fork as author attribution)

**MEDIUM findings resolved:**
- **FINDING-004**: Solution Approach Phase 3 text still had PostgreSQL parameterization — fixed to Phase 2
- **FINDING-005**: Neo4j/MCP profile transitive dependency — resolved: Neo4j included in both `graphiti` and `mcp` profiles; Task #34 updated
- **FINDING-006**: PERF-001 misclassified as general NFR — noted as Phase 3 acceptance criterion
- **FINDING-007**: FAIL-005 name urgency understated — added explicit urgency note to D-001

**LOW findings resolved:**
- REQ-015 now specifies `YOUR_SERVER_IP` format (consistency with REQ-001)
- REQ-022 scope clarified: test-only vars excluded from `.env.example`
- REQ-003 default value location specified as Python code (not only Compose)

### Planning Compaction (2026-03-03)

Compaction file: `SDD/prompts/context-management/planning-compacted-2026-03-03_11-52-17.md`
Contains: all critical review findings + resolutions + full Phase 1 task order + implementation constraints

### Next Steps — COMPLETE

All decisions confirmed. GitHub reserved. Implementation started.

---

## Implementation Phase (2026-03-03)

- **Prompt document:** `SDD/prompts/PROMPT-046-open-source-release-prep-2026-03-03.md`
- **Status:** In Progress — Phase 1, Task #2 next (`.gitignore` update)

### Decisions Confirmed

| D-001 | `sift` — github.com/pablooliva/sift |
| D-002 | ProPal Ethical License v1.0 |
| D-003 | Keep SDD/ public, minus context-management/ (3 curated examples) |
| D-004 | Option B — retain fork as author attribution |

### Phase 1 Progress — ✅ COMPLETE (2026-03-03)

- [x] Task #1: Reserve `sift` on GitHub
- [x] Task #2: Update `.gitignore` — added neo4j_logs/, .claude/, .mcp.json, node_modules/
- [x] Task #5a: Scrub `.env.test.example:45` — → host.docker.internal:11434
- [x] Task #3: Category A IP replacements — 13 Python files → localhost
- [x] Task #4: Category B IP replacements — docker-compose.yml + docker-compose.test.yml → host.docker.internal
- [x] Task #5: Category C IP replacements — README.md, CLAUDE.md, mcp_server docs → YOUR_SERVER_IP
- [x] Task #6: Personal path replacements — README.md, .env.example, scripts/, tests/backup/, docs/
- [x] Task #7: Create `LICENSE` (ProPal Ethical License v1.0) — Copyright (c) 2026 Pablo Oliva
- [x] Task #8: Verification greps — clean (only gitignored files remain)

### Phase 2 — In Progress (2026-03-03)

**Completed in Phase 2:**
- [x] REQ-006: `NOTICE` file — created
- [x] REQ-007: `CODE_OF_CONDUCT.md` — created (adapted Contributor Covenant v2.1)
- [x] REQ-008: `CONTRIBUTING.md` — created (component isolation, dev setup, SDD methodology, qdrant-tartai attribution)
- [x] REQ-009: `SECURITY.md` — created (zero-auth posture, network security, HTTPS guidance)
- [x] REQ-003: `memodo` generalization — Search.py dynamic categories, document_processor.py + graph_builder.py defaults updated, .env.example updated
- [x] REQ-012: SDD context-management — 5 files remain (3 curated examples + progress.md + VALIDATION-CHECKLIST-035.md)
- [x] REQ-013: SDD file scrubbing — 49 files scrubbed; 0 personal IPs/paths remaining
- [x] REQ-021: PostgreSQL parameterization — docker-compose.yml (postgres service + txtai-mcp + txtai service), docker-compose.test.yml, config.yml
- [x] REQ-022: `.env.example` authoritative — added POSTGRES_HOST/PORT/USER/PASSWORD/DB + GRAPHITI_SEARCH_TIMEOUT_SECONDS

### Phase 2 — ✅ COMPLETE (2026-03-04)

All REQ-010 through REQ-022 done. Key completions this session:
- [x] REQ-010: README trimmed 2146→424 lines; 4 docs/ files created (QUERY-ROUTING, DATA-STORAGE, KNOWLEDGE-GRAPH, TESTING)
- [x] REQ-011: Quick Start expanded with first-run download sizes (nomic 274MB, llama 6.5GB, Whisper 3GB, BART 560MB) + minimal/full paths
- [x] REQ-014/REQ-015: Already done in Phase 1 — marked complete

### Phase 3 — ✅ COMPLETE (2026-03-04)

- [x] FAIL-007: Ruff assessment — 538 violations (219 F401, 134 F541, 86 F841); CI uses --select E9,F63,F7,F82 only
- [x] REQ-016: GitHub Actions CI (`ci.yml`: Ruff critical + MCP unit tests) + security (`security.yml`: CodeQL + Trivy)
- [x] REQ-017: Issue/PR templates (bug_report.md, feature_request.md, PULL_REQUEST_TEMPLATE.md)
- [x] REQ-018: `mcp_server/pyproject.toml` author: "Pablo" → "Pablo Oliva"
- [x] REQ-019: `custom-requirements.txt` expanded with qdrant-tartai fork URL + attribution; CONTRIBUTING.md already had section
- [x] Final verification greps: 0 IPs, 0 personal paths, 0 memodo in tracked files

### Session 2026-03-06 — Final Pre-Push Work

- [x] REQ-020: Fresh `git init` — complete (499 files, single clean initial commit)
- [x] Critical review (FINDING-001 to FINDING-006) — all fixed
- [x] Gitleaks GitHub Action added to ci.yml
- [x] `.gitleaks.toml` allowlist configured; local scan: no leaks in tracked files
- [x] CHANGELOG.md created
- [x] Push to github.com/pablooliva/sift — ✅ COMPLETE (2026-03-07)
- [ ] PERF-001/PERF-002/FAIL-003/FAIL-004: Docker validation (deferred to server, optional)

**Status:** ✅ SPEC-046 COMPLETE — sift is live at https://github.com/pablooliva/sift

**Compaction file:** `SDD/prompts/context-management/implementation-compacted-2026-03-06_22-38-41.md`
