# Specification Critical Review: SPEC-046 Open Source Release Preparation

**Review Date:** 2026-03-03
**Artifact Reviewed:** `SDD/requirements/SPEC-046-open-source-release-prep.md` (including 2026-03-02 config management refinements)
**Reviewer:** Claude Sonnet 4.6 (adversarial pass)

---

## Executive Summary

SPEC-046 is comprehensive and well-structured, with solid research backing and thorough edge case coverage. However, three HIGH severity issues require resolution before implementation begins: (1) `.env.test.example` contains a personal IP and **will be committed** to the new repository — the SPEC doesn't mention scrubbing it; (2) REQ-021's proposed `config.yml` change uses `${VAR:-default}` shell syntax that Python's `os.path.expandvars()` does not support, meaning the config.yml parameterization as written will silently produce a broken connection string; (3) D-004 (qdrant-tartai fork) is referenced throughout the SPEC but is **missing from the Open Decisions table**, making it easy to overlook as a gate. Additionally, a **stale contradiction** in the Solution Approach text still assigns PostgreSQL parameterization to Phase 3 despite REQ-021 explicitly moving it to Phase 2. The spec is **HOLD — revise before proceeding** until the HIGH items are addressed.

---

## Severity: HIGH (3 findings require spec changes before implementation)

---

## Ambiguities That Will Cause Problems

### 1. REQ-022 — Scope of `.env.example` Completeness Is Undefined

**What's unclear:** REQ-022 says "every env var consumed by any service in `docker-compose.yml`, any Python script, or any frontend module must appear in `.env.example`." `frontend/tests/conftest.py` and `frontend/tests/integration/test_graphiti_edge_cases.py` consume `TEST_QDRANT_URL`, `TEST_NEO4J_URI`, `TEST_NEO4J_USER`, `TEST_TXTAI_API_URL`, `TEST_AUDIT_LOG_DIR`, etc. These are test-only vars not appropriate for `.env.example`.

**Possible interpretations:**
- A: Only production-path env vars (consumed by `docker-compose.yml`, application code, scripts) → 5 missing vars to add
- B: All env vars in the entire codebase → 15+ test vars that would bloat and confuse `.env.example`

**Recommendation:** Add a scoping statement to REQ-022: "Test-only variables (consumed exclusively in `tests/` paths) are documented in `frontend/tests/README.md` and `docker-compose.test.yml`, not in `.env.example`."

---

### 2. REQ-003 — Where Does the `MANUAL_CATEGORIES` Default Value Live?

**What's unclear:** REQ-003 specifies "default fallback when env var is unset or empty: `reference,technical,personal,research`" but doesn't say whether this default is in:
- (A) Python code: `os.getenv('MANUAL_CATEGORIES', 'reference,technical,personal,research')` in Search.py — survives when Docker isn't used
- (B) Docker Compose: `${MANUAL_CATEGORIES:-reference,technical,personal,research}` — only applies when env var is not in `.env`

**Why it matters:** If the default is only in Docker Compose, running `streamlit run Home.py` locally without Docker yields no categories (empty string). If it's in Python, it works everywhere.

**Recommendation:** Specify "The default must live in the Python code as a `os.getenv()` fallback, not solely in Docker Compose, so it works in all execution contexts including direct Streamlit runs and tests."

---

### 3. REQ-010 — README Restructuring Has No Section-to-Docs Mapping

**What's unclear:** "README.md is reduced to ~300-400 lines; detailed sections moved to `docs/DATA-STORAGE.md`, `docs/KNOWLEDGE-GRAPH.md`, `docs/TESTING.md`, `docs/QUERY-ROUTING.md`." The current README is 2,146 lines. Which sections go to which file is not specified.

**Why it matters:** An implementer will make 20+ arbitrary content decisions. If the user reviews and disagrees, the entire README restructure needs redoing. This is a 4-6 hour task with high rework risk.

**Recommendation:** Add a "README section mapping" table to the spec:

| Current README Section | Target |
|------------------------|--------|
| Data Storage | docs/DATA-STORAGE.md |
| Knowledge Graph | docs/KNOWLEDGE-GRAPH.md |
| Testing | docs/TESTING.md |
| Intelligent Query Routing | docs/QUERY-ROUTING.md |
| Quick Start, Architecture overview, FAQ | stays in README |

---

### 4. REQ-012 — Which Specific 3 Files to Retain from `context-management/`

**What's unclear:** "retain exactly 3 representative examples (one `research-compacted-*.md`, one `implementation-compacted-*.md`, one `progress.md` snapshot)" — but there are ~50 compaction files to choose from. The current `progress.md` is the **active working file** being updated with this very planning session; using it as the "example" would expose ongoing planning details rather than demonstrating the methodology cleanly.

**Recommendation:** Designate specific files to retain by timestamp. Suggested candidates:
- Research: `research-compacted-2026-02-07_10-17-42.md` (SPEC-030 era, mature example)
- Implementation: `implementation-compacted-2026-02-09_21-34-19.md` (substantive, representative)
- Progress: Create a purpose-built `progress-example-for-blog.md` that shows a clean mid-project state rather than live content

---

## Missing Specifications (HIGH severity)

### FINDING-001 [HIGH]: `.env.test.example` Contains Personal IP and WILL Be Committed

**Evidence:** `.env.test.example` line 45: `OLLAMA_API_URL=http://YOUR_SERVER_IP:11434`. The `.gitignore` explicitly **whitelists** this file with `!.env.test.example` (line 57 of `.gitignore`). It will be included in `git add -A` and committed.

**Impact:** SEC-001 verification (`grep -r 'YOUR_SERVER_IP' .`) will catch this — but only if the implementer runs it before `git add -A`. If they run it after committing, the IP is already in history. The SPEC's Phase 1 verification checklist correctly includes the grep, but there's no explicit task or REQ that names `.env.test.example` as a file to scrub.

**Affected requirements:** REQ-001 (Category B/C scope doesn't mention `.env.test.example`), REQ-014 (only mentions `.env.example` cleanup), SEC-001 (the verification catches it, but there's no remediation task).

**Recommendation:** Add to Phase 1 Task #5 or as a standalone task: "Scrub `.env.test.example`: replace `OLLAMA_API_URL=http://YOUR_SERVER_IP:11434` with `OLLAMA_API_URL=http://host.docker.internal:11434`." Also add to REQ-014's scope.

---

### FINDING-002 [HIGH]: REQ-021 `config.yml` Parameterization May Silently Break txtai

**Evidence:** Current `config.yml` line 17 uses a literal connection string: `postgresql+psycopg2://postgres:postgres@postgres:5432/txtai`. No existing value in `config.yml` uses `${VAR}` syntax — the LLM path is hardcoded (`together_ai/Qwen/Qwen2.5-7B-Instruct-Turbo`), not `together_ai/${RAG_LLM_MODEL}`. This indicates txtai's YAML loader either doesn't support `${VAR}` in values or the feature was never used.

**The core problem:** REQ-021 specifies changing config.yml to use `${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@${POSTGRES_HOST:-postgres}:${POSTGRES_PORT:-5432}/${POSTGRES_DB:-txtai}`. Python's `os.path.expandvars()` — the most common mechanism for YAML env var expansion — supports `$VAR` and `${VAR}` but **NOT** `${VAR:-default}` (the `:-` default syntax is bash-specific, not POSIX-portable to Python). If txtai uses `os.path.expandvars()`, the `:-` syntax would silently leave the literal string `${POSTGRES_USER:-postgres}` as the username, breaking all database connections at startup.

**Verification needed before implementing:** Check txtai's `Application` class source to confirm whether `${VAR:-default}` is supported. Two safe alternatives exist:
- **Alt A (recommended):** In `docker-compose.yml`, set `POSTGRES_USER=${POSTGRES_USER:-postgres}` in the txtai service's `environment:` block (Docker Compose resolves this to a real value). Then `config.yml` uses `${POSTGRES_USER}` without a default — the env var is always set by Compose.
- **Alt B:** Leave `config.yml` with the literal default connection string and add a comment: "Override by setting `DATABASE_URL` env var" — but this requires code changes to how txtai reads the connection.

**Recommendation:** Replace REQ-021's `config.yml` instruction with: "The `docker-compose.yml` txtai service environment block explicitly passes resolved PostgreSQL vars so `config.yml` can use `${VAR}` (no default) syntax. Verify txtai YAML variable interpolation supports this form before implementing; if not, use Alt A above."

---

### FINDING-003 [HIGH]: D-004 Is Missing from the Open Decisions Table

**Evidence:** The "Open Decisions" table (line 76-81) lists only D-001, D-002, D-003. D-004 (`qdrant-tartai` fork handling) is referenced in REQ-019, EDGE-002, RISK-006, Phase 1 Day 1 actions (line 387: "Finalize decisions D-001/D-002/D-003/D-004"), and Phase 2 Task #25 — but is absent from the formal table.

**Impact:** D-004 gates Phase 2 Task #25 and affects CONTRIBUTING.md, `custom-requirements.txt`, and potentially the `.whl` file rebuild. If a developer reads only the decisions table (the natural starting point), they'll miss D-004 entirely. Phase 2 Task #25 has a 30-minute estimate, but Option A (migrate fork to new org) is actually 2-4 hours including `.whl` verification and rebuild.

**Recommendation:** Add D-004 to the decisions table:
```
| D-004 | **qdrant-tartai fork** | Option B (retain as author attribution) | custom-requirements.txt comment + CONTRIBUTING.md note; no URL changes needed |
```
Also update Phase 2 Task #25 effort estimate to reflect Option A vs Option B divergence.

---

## Stale Contradiction (MEDIUM)

### FINDING-004 [MEDIUM]: Solution Approach Text Still Assigns PostgreSQL Parameterization to Phase 3

**Evidence:** "Solution Approach" section line 59: `3. **Phase 3 (Medium)** — GitHub Actions CI/CD; community infrastructure (issue templates, Discussions, badges); linting migration to Ruff; .dockerignore files; **PostgreSQL credential parameterization**`

**Conflict:** REQ-021 explicitly states: "This is Phase 2 work (not Phase 3)." The Phase 2 task list (Task #17) correctly places it in Phase 2. The Phase 3 task list (Task #26-34) correctly omits it.

**Impact:** A developer reading the executive "Solution Approach" summary will think PostgreSQL parameterization is Phase 3 work and may defer it incorrectly. This could result in a Phase 2 completion checkpoint being declared done without the credentials being parameterized.

**Recommendation:** Update Solution Approach bullet 3 to remove "PostgreSQL credential parameterization" and move it to bullet 2 (Phase 2): `2. **Phase 2 (High)** — ...generalize memodo; scrub SDD files; parameterize PostgreSQL connection vars; add first-run experience documentation`.

---

## Risk Reassessment (MEDIUM)

### FINDING-005 [MEDIUM]: Docker Compose Profiles — Neo4j/MCP Transitive Dependency Unresolved

**Context:** Phase 3 Task #34 plans: "Implement Docker Compose profiles: `graphiti` (Neo4j/Graphiti) and `mcp`; core services run without profile."

**Problem:** The MCP service (`txtai-mcp`) depends on Neo4j (lines 227-229 of `docker-compose.yml`: `depends_on: - txtai - neo4j`). If Neo4j is in the `graphiti` profile, running `--profile mcp` alone will fail because Neo4j won't start. Docker Compose profiles don't automatically start dependencies from other profiles.

**User experience consequence:** A user enabling only MCP (`docker compose --profile mcp up -d`) will get a startup error about Neo4j not running — confusing for new users. The SPEC says "core services run without any profile" but doesn't address this dependency graph.

**Recommendation:** Add a sub-task to Task #34: "Resolve Neo4j/MCP profile dependency: either (a) include Neo4j in both `graphiti` and `mcp` profiles, (b) make `mcp` profile depend on `graphiti`, or (c) document that `docker compose --profile graphiti --profile mcp up -d` is required to run MCP." Document chosen approach in `docker-compose.yml` comments and in the MCP README.

---

### FINDING-006 [MEDIUM]: PERF-001 Misclassified — It's a Phase 3 Acceptance Criterion, Not a General NFR

**Evidence:** PERF-001: "`docker compose up -d` (core services, no GPU) must start successfully using only `.env.example` values on a fresh clone." The spec's own note below it says: "These requirements... depend on Docker Compose profiles being implemented (Phase 3 Task #34). They can only be verified after Phase 3 is complete."

**Problem:** PERF-001 is listed alongside SEC-001 and PERF-002, which are Phase 1 verifiable. This creates a false sense of completeness — Phase 1 and 2 checklists look satisfied while this NFR cannot actually be verified until Phase 3.

**Recommendation:** Move PERF-001 and UX-002 to the Phase 3 Verification Checklist rather than the general NFR section, or add an explicit "(Phase 3 only)" label.

---

### FINDING-007 [MEDIUM]: FAIL-005 — Name Reservation Urgency Understated by 2 Days

**Evidence:** `knowloom` was confirmed available on 2026-03-01. Today is 2026-03-03. The SPEC says "Phase 1 Day 1 action, before all other work" — but the SPEC was just declared ready for implementation today, meaning 2 days have elapsed without reservation.

**Risk:** The availability window is indeterminate. PyPI squatting of appealing names can happen within hours of a name being mentioned in any public context. If Pablo discussed the name publicly (blog drafts, social media, etc.), risk increases.

**Recommendation:** Add an explicit urgency note to FAIL-005: "As of the specification date (2026-03-01), `knowloom` was available. Each day of delay increases risk. Reserve before any other implementation work — this is the single highest-priority action." Consider reserving it today, before any other SPEC refinements.

---

## Low Severity Findings

### FINDING-008 [LOW]: REQ-015 Placeholder Format Inconsistent with REQ-001

**REQ-001** (Category C): Use `<server-ip>` or `YOUR_SERVER_IP`.
**REQ-015** (CLAUDE.md): "personal IPs replaced with placeholders" — format unspecified.

An implementer working on CLAUDE.md in isolation might use `{YOUR_SERVER_IP}` or `[server-ip]` or `x.x.x.x`. The resulting CLAUDE.md would be inconsistent with REQ-001 documentation files.

**Recommendation:** REQ-015: "...replaced with `YOUR_SERVER_IP` (consistent with REQ-001 Category C format)."

---

### FINDING-009 [LOW]: REQ-011 Time Estimates Are Network-Speed-Anchored Without Caveat

"Ollama model pull: ~2 min on 100 Mbps" is accurate for 100 Mbps but will be 20 min on 10 Mbps (common for home fiber in many countries) or 45 min on 4 Mbps. Blog readers in lower-bandwidth regions will think the Quick Start is broken.

**Recommendation:** Add a parenthetical: "(times assume 100 Mbps; scale proportionally for your connection speed)" or provide a low/high range: "nomic-embed-text (~274 MB): 2-30 min depending on connection."

---

## Research Disconnects

None significant — the SPEC is well-grounded in RESEARCH-046. The config management refinements (REQ-022, expanded REQ-021) are extensions not anticipated in the research but internally consistent.

---

## Recommended Actions Before Proceeding

**Must fix before implementation starts (HIGH):**

1. **Add `.env.test.example` to Phase 1 scrubbing scope** — Add as Phase 1 Task #5a: "Scrub `.env.test.example` line 45: replace personal IP with `http://host.docker.internal:11434`." Update REQ-014 to include this file explicitly. (15 min effort)

2. **Resolve REQ-021 config.yml approach** — Before implementing, verify whether txtai's YAML loader supports `${VAR}` interpolation. Replace the `${VAR:-default}` instruction with Alt A (Docker Compose resolves PostgreSQL vars; config.yml uses `${VAR}` without defaults). If txtai doesn't support any interpolation, document the alternative approach (environment variable passed as full connection string). (1 hour to verify and update spec)

3. **Add D-004 to the Open Decisions table** — Insert the row and recommend Option B (retain fork as author attribution) to avoid the `.whl` rebuild risk. Update Task #25 effort estimate to reflect the chosen option. (10 min)

**Should fix before implementation starts (MEDIUM):**

4. **Fix Solution Approach Phase 3 text** — Remove "PostgreSQL credential parameterization" from Phase 3 bullet; add to Phase 2 bullet. (5 min)

5. **Add section-to-docs mapping for REQ-010** — Prevents arbitrary decisions during the highest-effort task in Phase 2. (30 min of planning conversation)

6. **Document Neo4j/MCP profile dependency resolution** — Add sub-task to Task #34; choose one of the three options and document it. (15 min)

7. **Reserve `knowloom` TODAY** — Don't wait for implementation-start. Do it now.

**Can be addressed during implementation (LOW):**

8. Standardize REQ-015 to use `YOUR_SERVER_IP` format.
9. Add network speed caveat to REQ-011 time estimates.
10. Clarify REQ-022 to exclude test-only vars.
11. Designate specific files for REQ-012 retention.
12. Specify REQ-003 default value location as Python code (not only Compose).
13. Reclassify PERF-001/UX-002 as Phase 3 acceptance criteria.

---

## Proceed/Hold Decision

**HOLD — Revise before proceeding.**

The three HIGH findings are real blockers:
- FINDING-001 is a **data leak risk**: if the implementer runs `git add -A` before the Phase 1 grep verification, personal data goes into the commit. The spec's verification catches it, but there's no explicit task to fix it.
- FINDING-002 is a **silent breakage risk**: `config.yml` with `${POSTGRES_PASSWORD:-postgres}` as a literal string would start the txtai container successfully (no parse error) but fail all database writes with an authentication error, likely attributed to wrong cause during debugging.
- FINDING-003 is a **planning gap**: D-004 resolution gates Task #25 and could cascade to a `.whl` rebuild that adds 2-4 hours of unplanned work mid-Phase 2.

All three can be resolved in under 2 hours of spec editing. Given the SPEC is otherwise strong, this is a targeted revision, not a rethink.
