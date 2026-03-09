# SPEC-046: Open Source Release Preparation

## Executive Summary

- **Based on Research:** RESEARCH-046-open-source-release-prep.md
- **Critical Review:** CRITICAL-RESEARCH-046-open-source-release-prep-20260301.md
- **Creation Date:** 2026-03-01
- **Author:** Claude (with Pablo)
- **Status:** Implemented ✓
- **Completed:** 2026-03-09
- **Implementation:** SDD/prompts/PROMPT-046-open-source-release-prep-2026-03-03.md
- **Summary:** SDD/prompts/implementation-complete/IMPLEMENTATION-SUMMARY-046-2026-03-09_21-57-59.md
- **Live:** https://github.com/pablooliva/sift

## Research Foundation

### Production Issues Addressed

- **180+ hardcoded IP addresses** (`YOUR_SERVER_IP`) in code, config, and documentation — must be generalized for any user to deploy
- **Personal paths** (`/path/to/external`, `/path/to/sift`) embedded in scripts and documentation
- **Personal category `memodo`** hardcoded in frontend UI (search filter, category defaults) — blocks generic use
- **2,146-line README** — too long for public consumption; key content buried
- **Missing community files** — no LICENSE, CONTRIBUTING.md, CODE_OF_CONDUCT.md
- **Application security posture** — all services bind `0.0.0.0` with zero authentication; not documented
- **First-run experience gap** — ~10 GB of model downloads undocumented; external dependencies unclear

### Stakeholder Validation

- **Blog author (Pablo)**: Repository is the "show your work" artifact for a 9-post series on pablooliva.de; readers will clone, study, and potentially contribute
- **Blog readers (first-time users)**: Need working system from clone in 15-30 minutes; need clear prereqs and download sizes
- **Contributors**: Need CONTRIBUTING.md, dev environment setup guide, test workflow
- **Security-conscious deployers**: Need SECURITY.md with auth considerations and network isolation guidance

### System Integration Points

- `docker-compose.yml:92,164,214` — `OLLAMA_API_URL` hardcoded default
- `docker-compose.test.yml:108,159` — `OLLAMA_API_URL` hardcoded default
- `mcp_server/populate_test_data.py:12,191` — hardcoded `TXTAI_API_URL`
- `custom_actions/ollama_classifier.py:54,196` — IP in `os.getenv()` default
- `custom_actions/ollama_captioner.py:52` — IP in `os.getenv()` default
- `scripts/graphiti-ingest.py:1296` — IP in `os.getenv()` default
- `scripts/cron-backup.sh:296` — `/path/to/external` path
- `scripts/setup-cron-backup.sh:93` — personal path in help text
- `frontend/pages/2_🔍_Search.py:505` — hardcoded `filter_memodo` checkbox (not dynamic)
- `frontend/utils/document_processor.py:73` — `memodo` in `MANUAL_CATEGORIES` default
- `frontend/utils/graph_builder.py:19` — `memodo` in color assignments
- `frontend/Home.py:455` — `memodo` mentioned in instructions

---

## Intent

### Problem Statement

The project is currently a private personal tool with personal data (IPs, paths, categories) embedded throughout the codebase. It cannot be open-sourced as-is without exposing personal information, confusing external users, or providing an insecure default deployment. The blog series will direct readers to this repository, so it must be polished, secure, and deployable by anyone.

### Solution Approach

Execute a phased remediation before the public `git init` and push:

1. **Phase 1 (Critical)** — Scrub all personal data; update `.gitignore`; create `LICENSE`; decide on project name/license/SDD visibility
2. **Phase 2 (High)** — Trim README; create community files (CONTRIBUTING, CODE_OF_CONDUCT, NOTICE, SECURITY); document application security posture; generalize `memodo`; scrub SDD files; parameterize PostgreSQL connection vars; add first-run experience documentation
3. **Phase 3 (Medium)** — GitHub Actions CI/CD; community infrastructure (issue templates, Discussions, badges); linting migration to Ruff; `.dockerignore` files; Docker Compose profiles
4. **Fresh git init** — After all scrubbing is complete, reset git history with `rm -rf .git && git init` and push to the public remote

### Expected Outcomes

- Any developer can clone the repo and have a working system in 15-30 minutes with documented prerequisites
- No personal data (IPs, paths, names, API keys) in the committed codebase
- Security posture clearly documented so users make informed deployment decisions
- Community infrastructure in place for contributors
- CI pipeline provides automated quality gates from day one

---

## Open Decisions (Must Resolve Before Implementation)

These three decisions gate all naming, licensing, and structural work. They should be resolved before or during Phase 1:

| # | Decision | Recommendation | Implication |
|---|----------|---------------|-------------|
| D-001 | **Project name** | `sift` ✅ CONFIRMED — reserved at github.com/pablooliva/sift | Personal repo under pablooliva account |
| D-002 | **License** | ProPal Ethical License v1.0 ✅ CONFIRMED | Values statement; not OSI-approved — expected tradeoff |
| D-003 | **Keep SDD/ public?** | Yes, minus `context-management/` + keep exactly 3 curated examples (see REQ-012) ✅ CONFIRMED | Blog Post 8 covers SDD methodology; curated SDD is a showcase |
| D-004 | **qdrant-tartai fork handling** | Option B — retain as author attribution ✅ CONFIRMED | Add comment to `custom-requirements.txt` and note to CONTRIBUTING.md; no URL changes, no `.whl` rebuild needed |

---

## Success Criteria

### Functional Requirements

- **REQ-001**: All occurrences of `YOUR_SERVER_IP` in Category A (code defaults) and Category B (Docker Compose) replaced with appropriate generic defaults. Category C (documentation) uses `<server-ip>` or `YOUR_SERVER_IP`. Generic defaults by context:
  - **Python scripts running outside Docker** (e.g., `os.getenv('OLLAMA_API_URL', ...)` in `custom_actions/`, `scripts/`): use `http://localhost:11434`
  - **Docker Compose `${VAR:-default}` fallbacks** (e.g., `${OLLAMA_API_URL:-http://YOUR_SERVER_IP:11434}`): use `http://host.docker.internal:11434` — this is the correct way for containers to reach a host service; the `extra_hosts: host.docker.internal:host-gateway` mapping in `docker-compose.yml` makes this work on Linux as well as Mac/Windows
  - **Note**: Hardcoded values in Docker Compose that are Docker-internal network addresses (e.g., `QDRANT_HOST=qdrant`, `TXTAI_API_URL=http://txtai:8000`) are not personal data and may remain hardcoded — they are correct Docker DNS names, not deployment-specific IPs
- **REQ-002**: All personal filesystem paths (`/path/to/external`, `/path/to/sift`) replaced with documented placeholders (`/path/to/backup`, `/path/to/project`).
- **REQ-003**: The `memodo` personal category is removed from all code; frontend Search.py dynamically reads categories from `MANUAL_CATEGORIES` env var at startup; default categories use generic examples. Format: comma-separated string, whitespace around commas is trimmed, empty tokens are ignored (matches existing parsing in `frontend/utils/document_processor.py:73`). Default fallback when env var is unset or empty: `reference,technical,personal,research`. **The default must be defined in Python code** (`os.getenv('MANUAL_CATEGORIES', 'reference,technical,personal,research')`) so it works in all execution contexts — including direct `streamlit run` without Docker and during unit tests — not solely as a Docker Compose `${MANUAL_CATEGORIES:-...}` fallback.
- **REQ-004**: `.gitignore` includes `neo4j_logs/`, `.claude/`, `.mcp.json`, `node_modules/`, and `.env.test` before the fresh `git init`. Note: the existing `.gitignore` already covers `.env.*` patterns — verify `.env.test` is captured by the existing rule OR add an explicit entry. (`.env.test` was previously committed with a personal IP at `OLLAMA_API_URL`; it must not appear in the new history.)
- **REQ-005**: `LICENSE` file contains the full Apache 2.0 text (or the chosen license per D-002).
- **REQ-006**: `NOTICE` file lists all bundled third-party dependencies with their licenses, noting that Neo4j Community (GPL v3) runs as a separate network service.
- **REQ-007**: `CODE_OF_CONDUCT.md` contains Contributor Covenant v2.1.
- **REQ-008**: `CONTRIBUTING.md` covers: dev environment setup (GPU optional), local test workflow (unit tests without Docker), full stack setup, SDD methodology overview, code style (Ruff), and component-isolation development paths — specifically: (a) frontend-only development requires only Postgres + Qdrant (not GPU services); (b) MCP server development requires only the txtai API; (c) which tests can run without any Docker services (unit tests only).
- **REQ-009**: `SECURITY.md` documents: (a) the zero-authentication posture, which services bind to `0.0.0.0`, why (intended home-network use), and how to secure for broader deployments (localhost-binding, reverse proxy with auth, firewall rules); (b) that GitHub automatically scans public repositories for known secret patterns and will alert if any API keys are accidentally committed — this is a secondary safety net that users should be aware of; (c) that HTTPS is not provided by default and a reverse proxy (nginx/Caddy) is required for TLS.
- **REQ-010**: `README.md` is reduced to ~300-400 lines; detailed sections moved to `docs/DATA-STORAGE.md`, `docs/KNOWLEDGE-GRAPH.md`, `docs/TESTING.md`, `docs/QUERY-ROUTING.md`.
- **REQ-011**: README "Quick Start" section documents all external dependencies: Ollama install, required model pulls (nomic-embed-text ~274 MB, llama3.2-vision ~6.5 GB), Whisper large-v3 auto-download (~3 GB on first transcription), total first-run download estimate (~10+ GB), and Together AI account requirement. The local Ollama RAG alternative (`docs/OLLAMA_INTEGRATION.md`) must be presented as a **first-class option** in Quick Start — not a footnote — with its specific `ollama pull` commands. Quick Start must provide a "minimal setup" path (search-only, no Whisper/vision, no Together AI key) and a "full setup" path (all features enabled).
- **REQ-012**: `SDD/prompts/context-management/` directory is removed, except for **exactly 3** representative examples (one `research-compacted-*.md`, one `implementation-compacted-*.md`, one `progress.md` snapshot) retained for Blog Post 8. These 3 files must be scrubbed for personal IPs and paths before inclusion.
- **REQ-013**: All remaining SDD files (RESEARCH, SPEC, PROMPT, REVIEW, IMPLEMENTATION-SUMMARY) have personal IPs and paths replaced with generic placeholders.
- **REQ-014**: Both `.env.example` and `.env.test.example` contain no personal data. `.env.test.example` is explicitly whitelisted in `.gitignore` (`!.env.test.example`) and WILL be committed — it currently contains `OLLAMA_API_URL=http://YOUR_SERVER_IP:11434` at line 45, which must be replaced with `http://host.docker.internal:11434`. In `.env.example`: generic category examples replace `memodo`/`activism`; all personal paths replaced.
- **REQ-015**: `CLAUDE.md` personal IPs replaced with `YOUR_SERVER_IP` (consistent with REQ-001 Category C format); network diagram IP addresses generalized to `<your-server-ip>`.
- **REQ-016**: GitHub Actions workflows created: `ci.yml` (Ruff lint + unit tests, triggers on push/PR) and `security.yml` (Trivy + CodeQL, triggers on push to main + weekly).
- **REQ-017**: GitHub issue templates created for bug report, feature request, and question. PR template created.
- **REQ-018**: The `mcp_server/pyproject.toml` author attribution is preserved (author attribution is normal open-source practice).
- **REQ-019**: `qdrant-tartai` fork reference decision documented (D-004). If **Option A (migrate to new org)**: (a) fork must be created under the new org before release; (b) `custom-requirements.txt` GitHub URL updated to new org; (c) the `.whl` file checked into git must be verified — if its internal metadata references the old fork URL, it must be rebuilt; (d) CONTRIBUTING.md must document how to rebuild the wheel; (e) the old `pablooliva/qdrant-tartai` fork should be kept active or a redirect established to avoid breaking any pre-release cloners. If **Option B (retain as author attribution)**: a comment in `custom-requirements.txt` and a note in CONTRIBUTING.md must explain that the fork at `pablooliva/qdrant-tartai` is maintained by the project author.
- **REQ-020**: Fresh `git init` is the final step after ALL scrubbing is verified complete and `.gitignore` is correct.
- **REQ-021**: All PostgreSQL connection parameters are replaced with environment variable references throughout `docker-compose.yml`, `docker-compose.test.yml`, and `config.yml`. This is Phase 2 work (not Phase 3), given that default credentials give full read access to all document content. Specific changes:
  - **`docker-compose.yml` postgres service** (currently hardcoded): `POSTGRES_DB=txtai` → `POSTGRES_DB=${POSTGRES_DB:-txtai}`, `POSTGRES_USER=postgres` → `POSTGRES_USER=${POSTGRES_USER:-postgres}`, `POSTGRES_PASSWORD=postgres` → `POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-postgres}`
  - **`docker-compose.yml` txtai-mcp service** (currently hardcoded): all five vars (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`) converted to `${VAR:-default}` syntax
  - **`config.yml`**: the connection string `postgresql+psycopg2://postgres:postgres@postgres:5432/txtai` replaced with `postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}` (no `:-default` syntax — Python's `os.path.expandvars()` does not support bash `:-` default notation; use `${VAR}` only, relying on the `docker-compose.yml` txtai service's `environment:` block to resolve all vars from `.env` before passing them to the container). **Pre-implementation check:** verify that txtai's YAML loader calls `os.path.expandvars()` or equivalent that handles `${VAR}` syntax; if not, use the environment variable passthrough pattern instead (set the full `DATABASE_URL` in Compose and read it in config.yml).
  - **`.env.example`**: adds `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` with generic defaults and a note: "Change POSTGRES_USER and POSTGRES_PASSWORD for any non-local deployment."

- **REQ-022**: `.env.example` is the single authoritative reference for all **production-path** environment variables (Option A — `.env` as sole config mechanism; no separate `app.yml` or `settings.yml` is introduced). Test-only variables (consumed exclusively in `tests/` directories, e.g., `TEST_QDRANT_URL`, `TEST_NEO4J_URI`) are documented in `docker-compose.test.yml` and `frontend/tests/README.md`, not in `.env.example`. Every env var consumed by any service in `docker-compose.yml`, any application Python script, or any frontend module must appear in `.env.example` with: (a) a generic, non-personal default value; (b) a comment explaining what it controls and when a user would change it. Gaps to close as part of this requirement:
  - `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_DB` — currently hardcoded in `docker-compose.yml`, not documented in `.env.example` (covered by REQ-021 changes)
  - `GRAPHITI_SEARCH_TIMEOUT_SECONDS` — hardcoded as `10` in the MCP service; add to `.env.example` with default `10` and a comment
  - Docker-internal service addresses (`QDRANT_HOST=qdrant`, `NEO4J_URI=bolt://neo4j:7687` within the compose network) may remain hardcoded; add inline comments in `docker-compose.yml` noting they are Docker network DNS names, not user-configurable IPs

### Non-Functional Requirements

- **PERF-001**: `docker compose up -d` (core services, no GPU) must start successfully using only `.env.example` values on a fresh clone.
- **PERF-002**: Unit tests (`./scripts/run-tests.sh --unit`) must pass after all `os.getenv()` fallback defaults are changed from personal IP to `localhost`.
- **SEC-001**: No occurrence of `YOUR_SERVER_IP` in any file that will be committed in the initial `git init` (verified via `grep -r 'YOUR_SERVER_IP' .` after all scrubbing).
- **SEC-002**: No occurrence of any personal filesystem path (`/path/to/external`, `/path/to/sift`) in any committed file.
- **SEC-003**: `git status` after scrubbing must show `.env`, `.env.test`, `.claude/`, `neo4j_logs/`, `.mcp.json`, `SDD/prompts/context-management/` (except the 3 preserved examples) as untracked/ignored.
- **Note on PERF-001 and UX-002**: These requirements ("only core services start without profiles") depend on Docker Compose profiles being implemented (REQ-021 adj., Phase 3 Task #33). They can only be verified after Phase 3 is complete.
- **UX-001**: The README Quick Start section documents every step from clone to first successful search, with expected time ranges per step (e.g., "Ollama model pull: ~2 min on 100 Mbps"). A manual walkthrough of the Quick Start steps from a fresh `.env.example` must produce a working search result with no undocumented steps required.
- **UX-002**: `docker compose up -d` (without profiles) starts only core services; optional services (Neo4j/Graphiti, MCP) require explicit profile selection.

---

## Edge Cases (Research-Backed)

### EDGE-001: `.env.test` contained personal IP

- **Research reference:** Critical review §"Items Not Addressed"
- **Current behavior:** `.env.test` was committed (commit `3405689`) with `OLLAMA_API_URL=http://YOUR_SERVER_IP:11434`; it was later removed from tracking but the IP survives in git history
- **Desired behavior:** With fresh `git init`, this is eliminated — no history to scan; `.env.test` must be gitignored or scrubbed before `git add -A`
- **Test approach:** `git status` after fresh init must not show `.env.test`; if present, verify it's in `.gitignore` or contains only generic values

### EDGE-002: `qdrant-txtai` fork reference reveals personal GitHub account

- **Research reference:** Critical review §"Items Not Addressed" item 2
- **Current behavior:** `custom-requirements.txt` and README reference `github.com/pablooliva/qdrant-txtai`
- **Desired behavior:** Either (a) migrate fork to new org before release and update references, or (b) explicitly retain as author attribution with a note in CONTRIBUTING.md
- **Test approach:** Decision D-004 must be documented; reference in README/custom-requirements.txt updated accordingly

### EDGE-003: `memodo` category in search filter is hardcoded, not dynamic

- **Research reference:** RESEARCH-046 §2.2
- **Current behavior:** `frontend/pages/2_🔍_Search.py:505` has a hardcoded `filter_memodo` checkbox that is independent of the `MANUAL_CATEGORIES` env var
- **Desired behavior:** Search filter categories are derived from `MANUAL_CATEGORIES` env var at runtime; no hardcoded category names
- **Test approach:** Unit test verifying category filter options match `MANUAL_CATEGORIES`; E2E test verifying filter UI renders correctly with generic categories

### EDGE-004: `SDD/prompts/context-management/` removal must preserve examples

- **Research reference:** Critical review §5 (LOW finding)
- **Current behavior:** ~120 compaction/progress files; one contains the Neo4j password (but this is moot with fresh git init)
- **Desired behavior:** Remove ~117 files; retain exactly 3: one `research-compacted-*.md`, one `implementation-compacted-*.md`, one `progress.md` snapshot; the retained files must be scrubbed for personal IPs/paths
- **Test approach:** `ls SDD/prompts/context-management/` shows exactly 3 files after cleanup

### EDGE-005: `mcp_server/populate_test_data.py` is a utility, not production code

- **Research reference:** RESEARCH-046 §1.2 Category A
- **Current behavior:** Lines 12, 191 hardcode the personal `TXTAI_API_URL`
- **Desired behavior:** Replace with `os.getenv('TXTAI_API_URL', 'http://localhost:8300')`
- **Test approach:** Manual verification; this file is not covered by automated tests

### EDGE-006: `tests/unit/backup/test-cron-backup.sh` and integration backup tests

- **Research reference:** RESEARCH-046 §2.5
- **Current behavior:** References `/path/to/external/backups` and `/path/to/external`
- **Desired behavior:** Replace with `/path/to/backup` or `$TEST_BACKUP_DIR` placeholder
- **Test approach:** Grep for `/path/to/external` after scrubbing returns zero results

### EDGE-007: First-run model download on `docker compose up`

- **Research reference:** Critical review §2 (HIGH finding)
- **Current behavior:** Whisper large-v3 (~3 GB) auto-downloads on first transcription with no user warning; Ollama models must be manually pulled
- **Desired behavior:** README Quick Start documents all download sizes; provides "minimal" vs "full" setup paths; CPU-only path (Phase 3 `docker-compose.cpu.yml`) documented
- **Test approach:** Walk through Quick Start with fresh `.env.example` and verify all steps are documented

---

## Failure Scenarios

### FAIL-001: Personal IP found post-scrub in `.gitignore` gap

- **Trigger condition:** Running `grep -r 'YOUR_SERVER_IP' .` after scrubbing returns results in files not covered by `.gitignore`
- **Expected behavior:** Fix before proceeding to `git init`; add pattern to `.gitignore` or scrub the file
- **User communication:** Error message in release checklist: "STOP — personal IP found, do not proceed to git init"
- **Recovery approach:** Fix the file; re-run the grep verification; proceed only when clean

### FAIL-002: Fresh `git init` run before scrubbing is complete

- **Trigger condition:** `git add -A` committed files still containing personal data or missing `.gitignore` entries
- **Expected behavior:** This is the highest-risk failure — there is no history rewrite available since the new repo IS the history
- **User communication:** Release checklist requires all verification steps completed and signed off before running `rm -rf .git`
- **Recovery approach:** If caught immediately (before public push): `rm -rf .git && git init` again after fixing; if after push: delete GitHub repo, fix, re-create

### FAIL-003: Unit tests fail after IP replacement in `os.getenv()` defaults

- **Trigger condition:** Test files that relied on `YOUR_SERVER_IP` as a default now fail connection because `localhost` has no service
- **Expected behavior:** Tests that need live services should use `TEST_TXTAI_URL` env var; pure unit tests should mock the client
- **User communication:** Test failure output identifies affected test and fallback default
- **Recovery approach:** Update test to mock external dependency or add the env var to test configuration

### FAIL-004: `docker compose up -d` fails with `.env.example` values only

- **Trigger condition:** A service startup requires a real API key (Together AI, Firecrawl) that isn't set
- **Expected behavior:** Services that require optional keys should fail gracefully (log error, remain stopped) rather than crash-loop; core services (embeddings, search) must work without Together AI key
- **User communication:** README documents which keys are required vs optional; startup failure messages are clear
- **Recovery approach:** Verify that RAG-only failures (no Together AI key) don't prevent core search from working

### FAIL-005: `knowloom` name taken before repo is made public

- **Trigger condition:** Another project registers `sift` on GitHub between research and launch
- **Expected behavior:** Name should have been reserved immediately (Phase 1, Day 1 action)
- **User communication:** Reserve the name NOW — create GitHub org/repo immediately
- **Recovery approach:** If taken: choose an alternative name; no PyPI reservation needed (project is not a pip-installable package)

### FAIL-007: Ruff Migration Reveals Excessive Lint Violations

- **Trigger condition:** Running Ruff on the codebase reveals 100+ violations requiring significant refactoring before CI can be enabled
- **Expected behavior:** Start with a minimal Ruff ruleset (`--select=E,F` — pycodestyle errors + pyflakes) for the initial CI pipeline; expand to additional rules incrementally post-launch rather than blocking release
- **User communication:** `pyproject.toml` documents which Ruff rules are enabled and notes that additional rules will be enabled in future PRs
- **Recovery approach:** If violation count is manageable (<50): fix all before `git init`. If >50: enable only `E,F` rules in CI; add a `# ruff: noqa` comment strategy for irreducible violations; create a post-launch issue to expand coverage incrementally

### FAIL-006: CI fails on public repo due to missing secrets

- **Trigger condition:** GitHub Actions workflows reference `TOGETHERAI_API_KEY` or other secrets that aren't set in the public repo's Actions secrets
- **Expected behavior:** CI should not require real API keys; unit tests and linting should work with mocked/no credentials
- **User communication:** CI workflow README section documents which GitHub Actions secrets must be set
- **Recovery approach:** Mock API calls in CI; use free-tier equivalents where possible; skip integration tests in CI that require paid APIs

---

## Implementation Constraints

### Context Requirements

- **Maximum context utilization:** <40% during implementation
- **Config architecture decision (REQ-022):** `.env` (and `.env.example`) is the single authoritative config mechanism for the project (Option A — 12-factor app). No separate `app.yml` or `settings.yml` is introduced. `config.yml` remains txtai-only and unchanged except for the PostgreSQL connection string.
- **Essential files for Phase 1:**
  - `.gitignore` — add 4 new patterns
  - `docker-compose.yml` — 3 IP replacements (lines 92, 164, 214); replace with `http://host.docker.internal:11434`
  - `docker-compose.test.yml` — 2 IP replacements (lines 108, 159); replace with `http://host.docker.internal:11434`
  - `custom_actions/ollama_classifier.py:54,196` — IP in os.getenv defaults; replace with `http://localhost:11434`
  - `custom_actions/ollama_captioner.py:52` — IP in os.getenv default; replace with `http://localhost:11434`
  - `scripts/cron-backup.sh:296` — path replacement
  - `scripts/setup-cron-backup.sh:93` — path replacement
  - `scripts/graphiti-ingest.py:1296` — IP in os.getenv default; replace with `http://localhost:11434`
  - `mcp_server/populate_test_data.py:12,191` — IP replacements; replace with `http://localhost:8300`
  - `tests/test_ollama_classification.py:11` — IP in os.getenv default; replace with `http://localhost:11434`
  - `tests/test_workflow_caption.py:16` — IP in os.getenv default; replace with `http://localhost:11434`
  - `tests/test_workflow_classification.py:21` — IP hardcoded constant; replace with `http://localhost:11434`
  - `tests/test_workflow_transcription.py:24` — IP in os.getenv default
  - `mcp_server/tests/test_graphiti.py:1637+` — IP in os.getenv default
  - `mcp_server/tests/test_knowledge_summary_integration.py:38-41` — hardcoded URI

- **Files that can be delegated to subagents:**
  - SDD file scrubbing (~78 RESEARCH/SPEC/PROMPT/REVIEW files with IPs) — systematic find/replace
  - `.env.example` cleanup — straightforward substitution
  - `README.md` restructuring — content reorganization to docs/

### Technical Constraints

- **Order constraint**: `.gitignore` MUST be correct BEFORE `git init` — there is no second chance
- **Order constraint**: All scrubbing MUST be complete BEFORE `git init` — no history to rewrite after
- **Verification constraint**: `grep -r 'YOUR_SERVER_IP' .` and `grep -r '/path/to/external' .` must return zero results before `git init`
- **Testing constraint**: Unit tests (`--unit`) must pass after IP replacements — these are the only tests runnable without live services
- **Naming constraint**: `memodo` must not appear in any user-facing string after Phase 2; generic defaults (`reference`, `technical`, `personal`, `research`) replace it
- **Linting constraint**: Ruff (not flake8+black) is the linter for the new public repo; `pyproject.toml` with Ruff config must exist before CI pipeline is created

### Docker Constraints

- **Do NOT publish txtai-api GPU image** — too large (~8 GB base), users must rebuild; Dockerfile.txtai stays in repo
- **DO publish** frontend and MCP images to GHCR (Phase 4, post-launch)
- **Docker Compose profiles** (Phase 3): core services start without profiles; `graphiti`/`neo4j` profile for knowledge graph; `mcp` profile for MCP server
- **CPU-only override** (Phase 3): `docker-compose.cpu.yml` with `neuml/txtai-cpu:latest` base for blog readers without GPU

---

## Validation Strategy

### Phase 1 Verification Checklist

- [ ] `grep -r 'YOUR_SERVER_IP' .` returns zero results (excluding `.git/`) — covers code, Docker Compose defaults, and documentation
- [ ] `grep -r '/path/to/external' .` returns zero results (excluding `.git/`)
- [ ] `git status` shows `.env`, `.claude/`, `neo4j_logs/`, `.mcp.json` as ignored
- [ ] `LICENSE` file exists with chosen license text
- [ ] `make verify` (or manual checklist) confirms all Phase 1 items complete
- [ ] Project name `sift` reserved on GitHub

### Phase 2 Verification Checklist

- [ ] `wc -l README.md` outputs ≤ 450 lines
- [ ] `docs/DATA-STORAGE.md`, `docs/KNOWLEDGE-GRAPH.md`, `docs/TESTING.md`, `docs/QUERY-ROUTING.md` exist
- [ ] `grep -i 'memodo' frontend/` returns zero results
- [ ] `CONTRIBUTING.md` exists and covers: setup, testing, SDD workflow, code style
- [ ] `CODE_OF_CONDUCT.md` exists (Contributor Covenant v2.1)
- [ ] `NOTICE` file exists listing dependency licenses
- [ ] `SECURITY.md` exists documenting zero-auth posture
- [ ] `.env.example` contains no personal data; `grep 'pablo\|memodo\|8TB' .env.example` returns zero
- [ ] `CLAUDE.md` scrubbed; `grep 'YOUR_SERVER_IP' CLAUDE.md` returns zero
- [ ] `ls SDD/prompts/context-management/` shows exactly 3 curated files
- [ ] `grep -r 'YOUR_SERVER_IP\|/path/to/external' SDD/` returns zero (after scrubbing)
- [ ] `grep 'POSTGRES_PASSWORD=postgres' docker-compose.yml` returns zero (all PostgreSQL vars parameterized per REQ-021)
- [ ] `grep 'POSTGRES_USER=postgres\|POSTGRES_DB=txtai' docker-compose.yml` returns zero (hardcoded values replaced with `${VAR:-default}`)
- [ ] `grep 'GRAPHITI_SEARCH_TIMEOUT_SECONDS' .env.example` returns a match (REQ-022 completeness)
- [ ] `grep 'POSTGRES_HOST\|POSTGRES_PORT\|POSTGRES_USER\|POSTGRES_DB' .env.example` returns matches for all four vars (REQ-022)

### Phase 3 Verification Checklist

- [ ] `.github/workflows/ci.yml` exists; Ruff runs clean on current codebase
- [ ] `.github/workflows/security.yml` exists
- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml`, `feature_request.yml` exist
- [ ] `.github/pull_request_template.md` exists
- [ ] `frontend/requirements.txt` has `ruff` replacing `black` and `flake8`
- [ ] `pyproject.toml` exists with Ruff configuration
- [ ] Docker Compose profiles configured: `docker compose up -d` (no profile) starts only core services; `docker compose --profile graphiti up -d` adds Neo4j/Graphiti; `docker compose --profile mcp up -d` adds MCP server

### Automated Testing

- Unit Tests:
  - [ ] `./scripts/run-tests.sh --unit` passes after all `os.getenv()` defaults changed to `localhost`
  - [ ] Frontend unit tests pass with generic category defaults (no `memodo` assertions)
- Integration Tests (with test services):
  - [ ] `docker compose up -d` succeeds using `.env.example` values only (minus paid API keys)
  - [ ] Core search workflow functional without Together AI key
- Edge Case Tests:
  - [ ] Search.py dynamically loads category filters from `MANUAL_CATEGORIES` env var
  - [ ] Backup scripts accept configurable `BACKUP_DIR` instead of hardcoded path

### Manual Verification

- [ ] Fresh clone → `cp .env.example .env` → `docker compose up -d` → first search works
- [ ] Quick Start walkthrough: all documented steps work as written
- [ ] Quick Start walkthrough completed from a fresh `.env.example` with no prior knowledge — every step is documented; no undocumented prerequisites encountered
- [ ] `SECURITY.md` clearly explains what is and isn't secure about the default deployment

### Performance Validation

- [ ] `docker compose up -d` (core services) completes within 5 minutes on first pull
- [ ] First search query returns results within 10 seconds (after models loaded)

---

## Dependencies and Risks

### External Dependencies

- **Together AI API**: Required for RAG; free tier available but limited. Local Ollama path must be prominently documented as alternative.
- **Ollama**: Must be installed on the host (not in Docker) for embedding model. Install documented in Quick Start.
- **GitHub**: Repository hosting; GitHub Actions for CI; GHCR for image publishing (Phase 4).
- **GitHub**: Repository hosting; GitHub Actions for CI; GHCR for image publishing (Phase 4). No PyPI — project is a self-hosted application, not a pip-installable package.

### Identified Risks

- **RISK-001: Name availability window** — `sift` needs to be reserved on GitHub immediately. **Mitigation**: Create GitHub org/repo before any other work (Phase 1, Day 1).

- **RISK-002: Effort underestimate** — Research estimates 14-22 hours for Phases 1-3; critical review suggests realistic is 20-32 hours. **Mitigation**: Plan for 30 hours; don't schedule blog post go-live with tight implementation deadline.

- **RISK-003: Zero-auth posture misunderstood** [**HIGH**] — All services bind `0.0.0.0` with zero authentication. Users who deploy on a VPS, office network, or shared WiFi will have all their personal documents publicly readable and writable. **Mitigation**: `SECURITY.md` + a prominent "Security Warning" callout block at the top of the README; document a localhost-binding configuration as an easy option for users who want more security.

- **RISK-004: Together AI as hard dependency** — RAG doesn't work without a paid key; may deter adoption. **Mitigation**: Local Ollama alternative elevated from `docs/OLLAMA_INTEGRATION.md` to Quick Start as a first-class option.

- **RISK-005: `git init` run prematurely** — If personal data remains when the repo is initialized, there is no clean recovery path. **Mitigation**: A release verification checklist (Phase 1) must be signed off before running `rm -rf .git`.

- **RISK-006: qdrant-txtai fork attribution** — `pablooliva/qdrant-tartai` revealed in `custom-requirements.txt`; if moving to a new org: (a) the GitHub URL in `custom-requirements.txt` breaks; (b) the checked-in `.whl` file's internal metadata may reference the old fork URL and need to be rebuilt; (c) any user who cloned a pre-release snapshot will have a broken dependency if the old fork is deleted. **Mitigation**: Decide D-004 in Phase 1; if migrating, keep the old fork alive as a redirect; explicitly check `.whl` metadata and rebuild if needed.

- **RISK-007: CI secrets** — GitHub Actions workflows may reference API keys not available in the public repo. **Mitigation**: Design CI to work without paid API keys; unit tests + Ruff linting require no external services.

---

## Implementation Notes

### Suggested Approach (Phased Execution)

#### Phase 1 (~5-7 hours) — Critical path before git init

**Day 1 Actions (do first, before any coding):**
1. Reserve `sift` GitHub org/repo (10 min)
2. Finalize decisions D-001/D-002/D-003/D-004

**Scrubbing (can be parallelized with subagents):**
3. Update `.gitignore` — add `neo4j_logs/`, `.claude/`, `.mcp.json`, `node_modules/`; verify `.env.test` is covered
4. Replace all Category A+B IPs in code/Docker files (~15 files) — use `sed` or subagent
5. Replace Category C IPs in documentation files (README, CLAUDE.md, MCP docs, ~10 files) — use `<server-ip>` or `YOUR_SERVER_IP` placeholders
6. Replace personal paths in scripts (~5 files)
7. Create `LICENSE` file

**Verification:**
8. Run `grep -r 'YOUR_SERVER_IP' .` — must return zero (all files: code + docs + config)
9. Run `grep -r '/path/to/external' .` — must return zero

#### Phase 2 (~10-14 hours) — Content and documentation

**Documentation (delegate README restructuring to subagent):**
9. Trim README to ~350 lines; create 4 `docs/` files
10. Add security section to README + create `SECURITY.md`
11. Add first-run experience to Quick Start (download sizes, minimal vs full setup)
12. Create `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `NOTICE`
13. Scrub `CLAUDE.md`
14. Clean `.env.example`

**Code changes:**
15. Generalize `memodo` in frontend code (Search.py refactor is the largest task here)
16. Parameterize PostgreSQL credentials in `docker-compose.yml` and `config.yml` (REQ-021)
17. Scrub SDD files — delegate to subagent (find/replace IPs + paths in ~100 files)
18. Remove `SDD/prompts/context-management/` except exactly 3 curated examples

#### Phase 3 (~6-8 hours) — CI/CD and polish

19. Replace flake8+black with Ruff; create `pyproject.toml`. **Ruff contingency**: run `ruff check .` first; if >50 violations, start with `--select=E,F` in CI and expand incrementally post-launch (see FAIL-007)
20. Create `.github/workflows/ci.yml` and `security.yml`
21. Create issue/PR templates
22. Add README badges
23. Create `.dockerignore` for frontend and MCP
24. Implement Docker Compose profiles: `graphiti` (Neo4j/Graphiti), `mcp` (MCP server); core services run without any profile (verifies PERF-001 and UX-002)

**Final verification and git init:**
25. Complete Phase 1 verification checklist (both greps return zero — all code + docs)
26. Complete Phase 2 verification checklist (PostgreSQL parameterized, memodo removed, community files present)
27. Complete Phase 3 verification checklist (CI workflows run clean, Ruff passes, profiles work)
28. `rm -rf .git && git init && git add -A && git commit -m "Initial open-source release"`
29. Push to `github.com/<org>/knowloom`

### Areas for Subagent Delegation

- **SDD file scrubbing** — ~100 files with IPs/paths; systematic pattern replacement; no reasoning required
- **README restructuring** — move content sections from README to 4 new `docs/` files; pure content reorganization
- **Category A IP replacement** — ~15 files; mechanical `os.getenv()` default replacements; verify with grep
- **Issue/PR template creation** — boilerplate GitHub community files; no project-specific knowledge needed

### Critical Implementation Considerations

1. **`.gitignore` before `git init`** — This is the single most important order constraint. The `.gitignore` must be complete and correct before `rm -rf .git` is run.

2. **Verification before `git init`** — The two grep commands (`YOUR_SERVER_IP` and personal paths) must return zero results across ALL files (code, config, and documentation). This is a hard gate. Documentation IPs are scrubbed in Phase 1 (Task #5) to ensure the verification passes at the end of Phase 1.

3. **`memodo` refactor scope** — The Search.py refactor (EDGE-003) is the most complex code change in Phase 2. `MANUAL_CATEGORIES` is currently an env var but the filter UI is hardcoded. The refactor requires: (a) reading categories from env at startup, (b) generating filter checkboxes dynamically, (c) updating default category list in `.env.example`.

4. **Ruff migration** — Before creating CI workflow, Ruff must run clean on the codebase. There will be lint errors. Fix them before writing `ci.yml` or the CI will fail from day one.

5. **Together AI alternative** — The local Ollama RAG path exists (`docs/OLLAMA_INTEGRATION.md`) but is buried. Quick Start should mention it prominently as a free alternative for readers without a Together AI account.

6. **Application security documentation tone** — `SECURITY.md` should be factual and non-alarmist. The system is designed for home network use; binding to `0.0.0.0` is intentional for LAN access. Document this clearly along with mitigations for users who want more security.

---

## Appendix: Full Remediation Task List

### Phase 1: Critical (blocks git init)

| # | Task | Effort | REQ |
|---|------|--------|-----|
| 1 | Reserve `sift` on GitHub ✅ DONE — github.com/pablooliva/sift | 10 min | FAIL-005 |
| 2 | Verify/update `.gitignore`: add `neo4j_logs/`, `.claude/`, `.mcp.json`, `node_modules/`; confirm `.env.test` is covered | 10 min | REQ-004 |
| 3 | Replace IPs in Category A code files (~15 files): Python `os.getenv()` defaults → `http://localhost:11434`; Docker Compose `${VAR:-192.168...}` defaults → `http://host.docker.internal:11434` | 3-5 hrs | REQ-001 |
| 4 | Replace IPs in Category B Docker Compose files (5 occurrences in docker-compose.yml + docker-compose.test.yml) with `http://host.docker.internal:11434` | 30 min | REQ-001 |
| 5 | Replace IPs in Category C documentation files (README, CLAUDE.md, MCP docs ~10 files) with `YOUR_SERVER_IP` | 1-2 hrs | REQ-001 |
| 5a | Scrub `.env.test.example` line 45: replace `OLLAMA_API_URL=http://YOUR_SERVER_IP:11434` with `http://host.docker.internal:11434` — this file is whitelisted in `.gitignore` and WILL be committed | 5 min | REQ-014 |
| 6 | Replace personal paths in scripts + test scripts | 1-2 hrs | REQ-002 |
| 7 | Create `LICENSE` file (Apache 2.0) | 5 min | REQ-005 |
| 8 | Verification: `grep -r 'YOUR_SERVER_IP' .` and `grep -r '/path/to/external' .` both return zero | 15 min | SEC-001, SEC-002 |

### Phase 2: High (required before public release)

| # | Task | Effort | REQ |
|---|------|--------|-----|
| 9 | Trim README.md to ~350 lines | 4-6 hrs | REQ-010 |
| 10 | Create `docs/DATA-STORAGE.md` | 1 hr | REQ-010 |
| 11 | Create `docs/KNOWLEDGE-GRAPH.md` | 1 hr | REQ-010 |
| 12 | Create `docs/TESTING.md` | 30 min | REQ-010 |
| 13 | Create `docs/QUERY-ROUTING.md` | 30 min | REQ-010 |
| 14 | Add first-run experience (minimal + full paths, time estimates) to README Quick Start | 1 hr | REQ-011 |
| 15 | Create `SECURITY.md` with zero-auth documentation and GitHub secret scanning note | 45 min | REQ-009 |
| 16 | Generalize `memodo` in frontend code (Search.py refactor, graph_builder.py, document_processor.py) | 2-3 hrs | REQ-003 |
| 17 | Parameterize all PostgreSQL connection vars in `docker-compose.yml` (postgres service + MCP service), `docker-compose.test.yml`, and `config.yml` connection string | 45 min | REQ-021 |
| 18 | Scrub SDD files — IPs + paths in ~100 files (delegate to subagent) | 2-4 hrs | REQ-013 |
| 19 | Remove `SDD/prompts/context-management/` (keep exactly 3 curated examples, scrubbed) | 30 min | REQ-012 |
| 20 | Create `NOTICE` file | 15 min | REQ-006 |
| 21 | Create `CODE_OF_CONDUCT.md` | 10 min | REQ-007 |
| 22 | Create `CONTRIBUTING.md` (including component isolation paths per REQ-008) | 1.5 hrs | REQ-008 |
| 23 | Scrub `CLAUDE.md` | 30 min | REQ-015 |
| 24 | Clean `.env.example`: remove personal data; add missing vars (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_DB`, `GRAPHITI_SEARCH_TIMEOUT_SECONDS`); add inline comments for Docker-internal addresses | 45 min | REQ-014, REQ-022 |
| 25 | Decide D-004 (qdrant-tartai fork) and update all affected files (custom-requirements.txt, README, wheel if needed) | 30 min | REQ-019, EDGE-002 |

### Phase 3: Medium (recommended before launch)

| # | Task | Effort | REQ |
|---|------|--------|-----|
| 26 | Run Ruff check; if <50 violations fix all; if ≥50 violations configure minimal ruleset (E,F) with plan to expand | 1-2 hrs | REQ-016, FAIL-007 |
| 27 | Create `pyproject.toml` with Ruff configuration | 15 min | REQ-016 |
| 28 | Create `.github/workflows/ci.yml` (Ruff + unit tests) | 1 hr | REQ-016 |
| 29 | Create `.github/workflows/security.yml` (Trivy + CodeQL) | 30 min | REQ-016 |
| 30 | Create issue/PR templates | 30 min | REQ-017 |
| 31 | Enable GitHub Discussions (repository settings) | 5 min | — |
| 32 | Add README badges (CI, license, Docker, Python) | 15 min | — |
| 33 | Create `.dockerignore` for frontend and MCP | 15 min | — |
| 34 | Implement Docker Compose profiles: `graphiti` (Neo4j/Graphiti) and `mcp`; core services run without profile. **Neo4j dependency resolution required:** MCP service depends on Neo4j; chosen approach: include Neo4j in both `graphiti` and `mcp` profiles so `--profile mcp` starts Neo4j automatically. Document in `docker-compose.yml` comments and MCP README. | 1.5-2.5 hrs | UX-002, PERF-001 |

### Phase 4: Post-launch

| # | Task | Effort | Notes |
|---|------|--------|-------|
| 35 | CPU-only compose override `docker-compose.cpu.yml` | 1-2 hrs | EDGE-007 |
| 36 | GHCR image publishing (frontend + MCP) — amd64 + arm64 | 2-3 hrs | — |
| 37 | Coverage reporting + badge | 1 hr | — |
| 38 | Setup script (`make setup`) | 1-2 hrs | — |
| 39 | Dependabot config | 10 min | — |
| 40 | CODEOWNERS file | 5 min | — |

### Revised Effort Estimates

| Phase | Research Estimate | SPEC Estimate (with 30% buffer + scope additions) |
|-------|------------------|--------------------------------------------------|
| Phase 1 (Critical) | 3-5 hours | **6-9 hours** (doc IP scrubbing added) |
| Phase 2 (High) | 8-12 hours | **12-16 hours** (PostgreSQL full parameterization + REQ-022 .env.example completeness added) |
| Phase 3 (Medium) | 3-5 hours | **6-8 hours** (Docker Compose profiles moved here from Phase 4) |
| **Total pre-launch** | **14-22 hours** | **24-33 hours** |
