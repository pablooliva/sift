# RESEARCH-046: Open Source Release Preparation

## Overview

Research for preparing this project for public open source release on GitHub, in support of a 9-post blog series titled "Building an AI-Powered Knowledge Management System: From Notes to Knowledge Graph" published on pablooliva.de. The repo is the "show your work" artifact — readers will clone it, study it, and potentially contribute.

---

## 1. Security Audit

### 1.1 Git History — Secrets Scan

**CRITICAL Finding: Production Neo4j password in tracked file**
- File: `SDD/prompts/context-management/research-compacted-2026-02-12_22-09-35.md` line 73
- Content: Literal production Neo4j password `Zzycp*W3WrrumvPHwEkzXq`
- **Action required**: Git history rewriting (BFG or git-filter-repo) + password rotation

**Production `.env` (NOT tracked — verified in .gitignore)**
- Contains real API keys: Together AI (`tgp_v1_UY9...`), Firecrawl (`fc-3a76afa7...`), Neo4j password
- `.env` IS in `.gitignore` (line 55) — should be safe, but **must verify never committed**:
  ```bash
  git log --all -- .env
  git log --all -- .env.test
  ```

**Commands to run before release** (were blocked in agent sandbox — must run manually):
```bash
# Check if .env was ever committed
git log --all -- .env
git log --all -- .env.test

# Search for actual key values in history
git log -p --all -S 'tgp_v1_UY9' 2>&1 | head -50
git log -p --all -S 'fc-3a76afa7fc014ba2990c42cc16cd2c1d' 2>&1 | head -50
git log -p --all -S 'Zzycp' 2>&1 | head -50

# Search for any sk- prefixed keys
git log -p --all -S 'sk-' -- '*.py' '*.yml' '*.yaml' '*.json' 2>&1 | head -100

# Check for any .env files ever committed
git log --all --diff-filter=A --name-only --format='' | grep -i '\.env' | sort -u
```

**Secret rotation required before release:**
1. Together AI API key
2. Firecrawl API key
3. Neo4j password

### 1.2 Hardcoded IP Addresses (YOUR_SERVER_IP)

**180+ occurrences** across the codebase. Categorized by severity:

**Category A: Code with hardcoded IPs (MUST parameterize)**

| File | Line(s) | Context |
|------|---------|---------|
| `mcp_server/populate_test_data.py` | 12, 191 | Hardcoded `TXTAI_API_URL` |
| `custom_actions/ollama_classifier.py` | 54, 196 | Default in `os.getenv()` |
| `custom_actions/ollama_captioner.py` | 52 | Default in `os.getenv()` |
| `scripts/graphiti-ingest.py` | 1296 | Default in `os.getenv()` |
| `scripts/graphiti_client.py` | 86 | Docstring example |
| `tests/test_ollama_classification.py` | 11 | Default in `os.getenv()` |
| `tests/test_workflow_caption.py` | 16 | Default in `os.getenv()` |
| `tests/test_workflow_classification.py` | 21 | Hardcoded constant |
| `tests/test_workflow_transcription.py` | 24 | Default in `os.getenv()` |
| `mcp_server/tests/test_graphiti.py` | 1637+ | Default in `os.getenv()` |
| `mcp_server/tests/test_knowledge_summary_integration.py` | 38-41 | Hardcoded test URI |
| `frontend/utils/graphiti_client.py` | 86 | Docstring example |

**Category B: Docker Compose defaults (MUST fix)**

| File | Line(s) | Context |
|------|---------|---------|
| `docker-compose.yml` | 92, 164, 214 | `OLLAMA_API_URL` default |
| `docker-compose.test.yml` | 108, 159 | `OLLAMA_API_URL` default |

**Category C: Documentation (should genericize)**

| File | Occurrences |
|------|-------------|
| `README.md` | 4 (curl examples) |
| `CLAUDE.md` | 6 (architecture docs) |
| `SDD/` directory | ~100+ across research/spec docs |
| Various MCP server docs | ~10 |

**Category D: Acceptable/benign**
- `frontend/pages/1_Upload.py:865` — UI placeholder (`192.168.1.1/admin`, generic)
- `frontend/tests/unit/test_bookmark.py:98-99` — Test for private IP validation
- `mcp_server/README.md` — Uses generic `192.168.1.100`

**Recommendation**: Replace all `YOUR_SERVER_IP` defaults in code/config with `localhost`. In documentation, use `YOUR_SERVER_IP` or `<server-ip>` placeholder.

### 1.3 .gitignore Audit

**Currently covered (good):**
- `.env` / `.env.*` (with exceptions for `.env.example`, `.env.test.example`)
- Python caches, venvs, eggs
- Docker volumes (`txtai_data/`, `qdrant_storage/`, `postgres_data/`, `neo4j_data/`)
- IDE files (`.vscode/`, `.idea/`)
- Logs, backups, audit files
- Pytest cache, coverage
- Document archive directories

**MISSING (must add before release):**

| Pattern | Risk | Reason |
|---------|------|--------|
| `neo4j_logs/` | **HIGH** | Neo4j log directory exists on disk; `security.log` could contain auth info |
| `.claude/` | **HIGH** | `settings.local.json` contains personal paths, IP, permission rules |
| `.mcp.json` | **MEDIUM** | Active MCP config would contain real API keys |
| `node_modules/` | LOW | Safeguard (not currently present) |

### 1.4 Sensitive Files Currently Tracked

| Finding | Severity | File | Details |
|---------|----------|------|---------|
| Neo4j password in SDD file | **CRITICAL** | `SDD/prompts/context-management/research-compacted-2026-02-12_22-09-35.md:73` | Literal production password — requires history rewrite |
| Personal mount path | **HIGH** | `.env.example:226`, `scripts/cron-backup.sh:296`, `scripts/setup-cron-backup.sh:93` | `/path/to/external` |
| Personal path in README | **HIGH** | `README.md:45` | `/path/to/sift & Dev/AI and ML/txtai` |
| PostgreSQL `postgres:postgres` | LOW | `config.yml:17`, `docker-compose.yml:18` | Common dev default; document as "development only" |

---

## 2. Repository Structure Assessment

### 2.1 SDD/ Directory

**425 files total** across subdirectories:
- `SDD/research/` — 65 RESEARCH files
- `SDD/requirements/` — 39 SPEC files
- `SDD/prompts/` — 45 PROMPT files
- `SDD/reviews/` — 57 CRITICAL review files
- `SDD/prompts/implementation-complete/` — 38 IMPLEMENTATION-SUMMARY files
- `SDD/prompts/context-management/` — ~120 compaction/progress/archive files
- `SDD/slash-commands/` — 2 files

**Sensitive content found:**
- `/path/to/sift` paths in ~30 files
- `YOUR_SERVER_IP` in 78 files
- `Author: Claude (with Pablo)` in PROMPT headers
- **No API keys or credentials** in SDD files (except the one compacted file noted in 1.4)

**Recommendation:**
- **KEEP**: RESEARCH, SPEC, PROMPT, REVIEW, IMPLEMENTATION-SUMMARY files — valuable for blog Post 8 (SDD methodology)
- **REMOVE**: `SDD/prompts/context-management/` entirely (~120 files of transient session state, no educational value)
- **SCRUB**: Personal paths and IPs from remaining SDD files

### 2.2 Frontend Assessment

**Hardcoded personal content:**
- `frontend/utils/graphiti_client.py:86` — Personal IP in docstring
- Custom category `memodo` hardcoded as default in multiple files:
  - `frontend/utils/document_processor.py:73` — Default in `MANUAL_CATEGORIES`
  - `frontend/utils/graph_builder.py:19` — Color assignments
  - `frontend/pages/2_🔍_Search.py:505` — Hardcoded `filter_memodo` checkbox (NOT dynamic)
  - `frontend/Home.py:455` — Mentioned in instructions

**Test fixtures — ALL SYNTHETIC (safe):**
- `frontend/tests/fixtures/sample.txt` — Generic test content
- `frontend/tests/fixtures/large_document.txt` — AI-generated ML textbook (240 lines)
- `frontend/tests/fixtures/url.txt` — Single public URL
- All inline test data is synthetic

**Recommendation**: Generalize `memodo` to generic category defaults. Refactor `Search.py` to dynamically read from `MANUAL_CATEGORIES` env var.

### 2.3 Scripts Audit

| Script | Status | Issue |
|--------|--------|-------|
| `backup.sh` | Clean | — |
| `cron-backup.sh` | **Needs fix** | Hardcoded `/path/to/external` at line 296 |
| `setup-cron-backup.sh` | **Needs fix** | Personal path in help text at line 93 |
| `restore.sh` | Clean | — |
| `reset-database.sh` | Clean | — |
| `run-tests.sh` | Clean | — |
| `graphiti-ingest.py` | **Needs fix** | Personal IP as default at line 1296 |
| `graphiti_client.py` | **Needs fix** | Personal IP in docstring at line 86 |
| Other scripts | Clean | No embedded credentials or personal paths |

### 2.4 README.md Assessment

**Current size: 2,146 lines** — excessively long for a public README.

**Content analysis:**

| Section | Lines | Verdict |
|---------|-------|---------|
| Overview/Features/Prerequisites | 1-39 | Good — keep |
| Quick Start | 41-69 | Fix personal path at line 45 |
| /ask Command + Usage | 71-133 | Good — keep |
| Project Structure | 135-149 | Outdated — update |
| Configuration | 188-275 | Good — keep |
| Intelligent Query Routing | 292-453 | **Too detailed** (160 lines) — move to docs/ |
| Data Persistence | 520-1206 | **Way too detailed** (686 lines) — move to docs/ |
| Knowledge Graph Management | 1207-1527 | **Too detailed** (320 lines) — move to docs/ |
| Testing | 1781-1975 | **Internal** (194 lines) — move to docs/ |
| Recent Updates | 2073-2093 | **Stale** (Dec 2025) |
| Roadmap | 2095-2111 | **Stale** — lists existing features as "planned" |

**Recommended public README structure (~300-400 lines):**
1. Header + Badges (5 lines)
2. Screenshot/Demo (5 lines)
3. Features (20 lines)
4. Architecture Overview (15 lines)
5. Prerequisites (10 lines)
6. Quick Start (30 lines)
7. Configuration (40 lines)
8. Usage (40 lines)
9. MCP Integration (20 lines)
10. Development (30 lines)
11. Troubleshooting (20 lines — top 5 issues)
12. License + Acknowledgments (10 lines)

**Move to `docs/`:**
- `docs/DATA-STORAGE.md` — Storage layers, archive format, recovery
- `docs/KNOWLEDGE-GRAPH.md` — Graphiti management, ingestion details
- `docs/TESTING.md` — Full test infrastructure guide
- `docs/QUERY-ROUTING.md` — Detailed RAG routing implementation

### 2.5 Additional Personal Data Found

| File | Content | Action |
|------|---------|--------|
| `mcp_server/pyproject.toml:8` | `{ name = "Pablo" }` author field | Generalize or keep (author attribution is normal) |
| `frontend/tests/helpers.py:34` | `Author: Claude (with Pablo)` | Generalize |
| `.env.example:121-125` | Categories include `memodo`, `activism` | Replace with generic examples |
| `tests/unit/backup/test-cron-backup.sh:135,149,189` | `/path/to/external/backups` | Replace with placeholder |
| `tests/integration/backup/test-edge-cases.sh:198` | `/path/to/external` | Replace with placeholder |

---

## 3. Licensing

### 3.1 Dependency License Matrix

| Dependency | License | How Used | Bundled? |
|------------|---------|----------|----------|
| txtai | Apache 2.0 | Docker container, API calls | Docker image |
| Qdrant | Apache 2.0 | Separate Docker container | No |
| Neo4j Community | **GPL v3** | Separate Docker container, Bolt protocol | No |
| Graphiti (graphiti-core) | Apache 2.0 | Python dependency | Yes (pip) |
| Neo4j Python Driver | Apache 2.0 | Python dependency (used by Graphiti) | Yes (pip) |
| Ollama | MIT | Separate service, HTTP API | No |
| Streamlit | Apache 2.0 | Python dependency | Yes (pip) |
| Together AI | Commercial API | HTTP API calls only | No |

### 3.2 GPL v3 (Neo4j) Analysis

**Key finding: Neo4j's GPL v3 does NOT trigger copyleft for this project.**

Three independent legal principles support this:

1. **FSF's "Separate Program" Doctrine**: The FSF GPL FAQ states that "pipes, sockets and command-line arguments are communication mechanisms normally used between two separate programs." This project communicates with Neo4j exclusively via the Bolt network protocol. The FSF's "intimacy test" (exchanging complex internal data structures) does not apply — standard Cypher queries over a well-defined protocol is analogous to SQL queries to PostgreSQL.

2. **Docker Container Isolation**: Red Hat's legal analysis (opensource.com) states: "communication between containers by way of network interfaces is analogous to such mechanisms as pipes and sockets, and a multi-container microservices scenario would seem to preclude what the FSF calls 'intimate' communication by definition."

3. **GPL v3 vs AGPL v3**: GPL v3 triggers copyleft only upon **distribution** — conveying copies to others. Running GPL software as a server does NOT count as distribution (this is the "SaaS loophole" that AGPL v3 was specifically created to close). Neo4j is GPL v3, not AGPL v3.

**Precedent**: Major projects communicating with Neo4j Community use permissive licenses:
- LangChain: MIT
- LangChain-Neo4j: MIT
- Graphiti: Apache 2.0
- Haystack: Apache 2.0
- LlamaIndex: MIT

### 3.3 License Options Comparison

| Criterion | MIT | Apache 2.0 | GPL v3 | AGPL v3 |
|-----------|-----|-----------|--------|---------|
| Attracts contributors | Best | Very Good | Fair | Poor |
| Attribution protection | Minimal | **Good** | Good | Good |
| Prevents uncredited commercial use | No | Partial (requires attribution) | No (SaaS loophole) | Yes |
| Dependency compatibility | Good | **Best** | Fair | Poor |
| Blog reader simplicity | Best | Good | Fair | Poor |
| Patent protection | None | **Yes** | Yes | Yes |

### 3.4 Recommendation: Apache 2.0

**Rationale:**

1. **Attribution protection**: Requires preserving NOTICE files and copyright notices in derivative works — directly addresses "uncredited commercial use" concern. Stronger than MIT.
2. **Patent grant**: Contributors automatically grant patent licenses with retaliation clause.
3. **Trademark protection**: Explicitly does not grant permission to use trademarks.
4. **Ecosystem alignment**: Same license as txtai, Qdrant, Streamlit, Graphiti — smoothest compatibility.
5. **Well-understood**: Widely known by companies, contributors, and legal departments.

**Implementation**: Create `LICENSE` (full Apache 2.0 text) and `NOTICE` file listing third-party dependencies with their licenses, including a note that Neo4j Community (GPL v3) runs as a separate network service.

---

## 4. Project Identity / Naming

### 4.1 Methodology

Searched GitHub and PyPI for 20+ candidate names. Assessed availability, memorability, conflicts.

### 4.2 Disqualified Names

| Name | Reason |
|------|--------|
| mindgraph | **TAKEN** — active AI project by Yohei Nakajima (1.5k+ stars) |
| neurovault | **TAKEN** — established neuroscience platform |
| semantic-vault | **TAKEN** — active project doing exactly similar work (Obsidian semantic search) |
| mindweave | **TAKEN** — `mindweave.space` is an "AI-Powered Personal Knowledge Hub" |
| synapse-search | "Synapse" massively overloaded (Matrix, Azure, Microsoft, PyPI) |
| omnimind | **TAKEN** — active Python MCP project |
| memex | Iconic name with too many claimants |
| txtai-knowledge | Could imply official NeuML/txtai affiliation |
| braindex | Taken in bioinformatics |

### 4.3 Top 5 Recommendations

#### 1. **knowloom** (Recommended)

- GitHub: **Available**
- PyPI: **Available**
- "Know" (knowledge) + "loom" (weaves threads together)
- Metaphor extends naturally: documents are "threads," knowledge graph is the "weave," system creates a "tapestry" of knowledge
- 8 characters, easy to spell, memorable, zero conflicts
- Blog series: "Building KnowLoom: A Personal Knowledge Graph with AI"

#### 2. **graphvault**

- GitHub: **Available**
- PyPI: **Available**
- Directly communicates knowledge graphs + secure document storage
- More technical-sounding — advantage for developers, slight disadvantage for broader appeal

#### 3. **knowledge-forge**

- GitHub: **Available** (no exact match; `knowledge-production/forge` unrelated)
- PyPI: **Available**
- "Forge" evokes crafting raw documents into refined knowledge
- Downside: slightly generic at 15 characters

#### 4. **cognilake**

- GitHub: **Available**
- PyPI: **Available**
- "Cogni" (cognition) + "lake" (deep reservoir)
- Downside: "data lake" connotation; "cogni-" prefix getting crowded

#### 5. **neuralark**

- GitHub: **Available**
- PyPI: **Available**
- "Neural" (AI) + "ark" (archive preserving knowledge)
- Downside: "neural" could imply specifically neural networks

### 4.4 Additional Available Names

- **knowmesh** — "mesh" suggests interconnected knowledge; clean availability
- **knowlens** — "lens" = focused view into knowledge; minor conflict with `knowledgelens` org

---

## 5. Documentation for External Users

### 5.1 Current State

- `README.md` — 2,146 lines (needs major trimming)
- `CLAUDE.md` — Comprehensive but contains personal data
- `frontend/README.md` — Frontend-specific setup
- `mcp_server/README.md` — MCP setup guide (uses generic IPs, good)
- `docs/DATA_STORAGE_GUIDE.md` — PostgreSQL/Qdrant details
- `docs/OLLAMA_INTEGRATION.md` — Local LLM setup
- `docs/QDRANT_SETUP.md` — Qdrant configuration
- `docs/LOGGING.md` — Logging configuration
- No `CONTRIBUTING.md`, no `LICENSE` file, no `CODE_OF_CONDUCT.md`

### 5.2 Required Documentation for Launch (Post 1)

| Document | Purpose | Effort |
|----------|---------|--------|
| `LICENSE` | Apache 2.0 full text | 5 min |
| `NOTICE` | Third-party dependency attribution | 15 min |
| `CODE_OF_CONDUCT.md` | Contributor Covenant v2.1 | 10 min |
| `CONTRIBUTING.md` | Dev setup, workflow, testing, SDD methodology | 45 min |
| Trimmed `README.md` | ~300-400 lines, public-friendly | 2-3 hours |
| `.env.example` cleanup | Remove personal data, improve comments | 30 min |

### 5.3 Documentation to Move from README to docs/

| New file | Content moved from README |
|----------|--------------------------|
| `docs/DATA-STORAGE.md` | Storage layers, archive format, recovery procedures (686 lines) |
| `docs/KNOWLEDGE-GRAPH.md` | Graphiti management, ingestion, rate limiting (320 lines) |
| `docs/TESTING.md` | Full test infrastructure guide (194 lines) |
| `docs/QUERY-ROUTING.md` | Detailed RAG routing implementation (160 lines) |

### 5.4 CLAUDE.md Strategy

`CLAUDE.md` is committed and contains personal IPs and network topology. Options:
1. **Scrub and keep** — Replace IPs with placeholders, genericize network diagram. Valuable as a reference for how Claude Code project instructions work (supports blog content).
2. **Move to `.claude/`** — Not standard; CLAUDE.md in root is the expected location.
3. **Gitignore** — Loses value as a public artifact.

**Recommendation**: Scrub and keep. CLAUDE.md is a showcase of Claude Code integration (relevant to the blog series).

---

## 6. CI/CD and Community Infrastructure

### 6.1 GitHub Actions — Day 1 Pipeline

**Workflow 1: CI (Lint + Unit Tests)** — runs on every push/PR, ~2 min
- Ruff linting (replaces flake8+black, 10-100x faster)
- Unit tests via pytest

**Workflow 2: Security Scanning** — runs on push to main + weekly
- Trivy filesystem scan (dependencies, IaC)
- CodeQL SAST (free for public repos)

**Workflow 3: Docker Build Validation** — runs on PRs touching Dockerfiles
- Build frontend and MCP images
- Note: txtai-api (GPU) cannot be built on standard runners

**Dependabot**: Zero-config dependency vulnerability alerts via `dependabot.yml`

### 6.2 Incremental CI Additions (Post-Launch)

| Priority | Addition |
|----------|----------|
| P1 | Docker image Trivy scan (post-build) |
| P2 | Integration tests with docker-compose services |
| P2 | Coverage reporting with badge |
| P3 | E2E tests (Playwright + test services) |
| P3 | Release automation (tag → GitHub Release) |

### 6.3 Community Infrastructure

**Issue templates** (`.github/ISSUE_TEMPLATE/`):
- Bug report (YAML form with component dropdown)
- Feature request
- Question

**PR template** (`.github/pull_request_template.md`):
- Description, components affected, testing checklist

**Code of Conduct**: Contributor Covenant v2.1 (widely adopted; v3.0 too new)

**GitHub Discussions**: Enable on Day 1. No Discord needed until 50+ active community members.

**Badges** (README header):
- CI status, License, Security scan, Docker Compose ready, Python version

**CODEOWNERS**: Lightweight single-maintainer file; more valuable if contributors join.

### 6.4 Linting Migration

Current: `black>=23.12.0` + `flake8>=6.1.0` in `frontend/requirements.txt`
Recommended: Replace with **Ruff** (from Astral/uv team) — single tool, 10-100x faster, covers pycodestyle, pyflakes, isort, black formatting, 800+ rules.

---

## 7. Docker Image Strategy

### 7.1 Registry: GHCR (not Docker Hub)

| Factor | Docker Hub | GHCR |
|--------|-----------|------|
| Pull rate limits | 100/6h anonymous | None (public) |
| CI integration | Requires Docker Hub token | Native `GITHUB_TOKEN` |
| Cost | Free (rate-limited) | Free (unlimited) |

### 7.2 GPU Considerations

- **Do NOT publish txtai-api GPU image** on Day 1 — base is `neuml/txtai-gpu:latest` (~8 GB), users must rebuild anyway when txtai updates. `docker compose build` is the right approach.
- **DO publish** frontend and MCP images (CPU-only, `python:3.12-slim` based, small).

### 7.3 Multi-Architecture

**amd64 only** for now. The txtai-api container requires NVIDIA GPU (exclusively x86_64). Multi-arch builds add CI complexity with minimal audience benefit.

### 7.4 CPU-Only Mode

**Recommended**: Create `docker-compose.cpu.yml` override for:
- Blog readers without GPU
- CI testing
- Development on laptops

Requires parameterizing `Dockerfile.txtai` base image via build arg:
```dockerfile
ARG BASE_IMAGE=neuml/txtai-gpu:latest
FROM ${BASE_IMAGE}
```

Limitations to document: No GPU-accelerated Whisper/BLIP-2, slower embeddings. Search and RAG still work.

### 7.5 Simplifying "Clone and Run"

Current setup requires 7 steps. Recommendations:
1. **`make setup` target** or setup script (copy `.env.example`, prompt for API keys, validate prerequisites)
2. **Docker Compose profiles** for optional services:
   ```yaml
   services:
     neo4j:
       profiles: ["graphiti"]
     txtai-mcp:
       profiles: ["mcp"]
   ```
   Then `docker compose up -d` starts only core services.
3. **Document minimal vs full setup** — which services are strictly required vs optional
4. **Pre-seed model cache docs** — expected download sizes and first-run times

### 7.6 Image Naming Convention

```
ghcr.io/<org>/knowloom-frontend:latest
ghcr.io/<org>/knowloom-frontend:v1.0.0
ghcr.io/<org>/knowloom-mcp:latest
```

---

## 8. Release Strategy: Fresh Git History

**Decision (2026-03-01):** The repository will be reset with a fresh `git init` in the same project directory. All existing git history will be discarded. The repo has never been pushed to a public remote.

**Method:**
```bash
# After all scrubbing is complete:
rm -rf .git
git init
git add -A
git commit -m "Initial open-source release"

# Push to public repo
git remote add origin git@github.com:<org>/knowloom.git
git push -u origin main
```

**Key principles:**
1. **Audit the working tree first** — all scrubbing (IPs, personal paths, secrets in file content) must be complete BEFORE `git init`
2. **`.gitignore` must be correct** before `git add -A` — prevents accidental inclusion of `.env`, `.claude/`, `neo4j_logs/`, `.mcp.json`
3. **SDD context-management files** should be removed/curated before the initial commit
4. **Back up the old `.git/` directory** before deleting, in case you need to reference history later

**Implications:**

| Original Concern | Impact |
|-------------------|--------|
| Neo4j password in git history (§1.4) | **Eliminated** — no history to leak |
| Git history secret scan (§1.1) | **Unnecessary** — no history to scan |
| BFG/git-filter-repo rewrite | **Unnecessary** — no history to rewrite |
| Secret rotation (Together AI, Firecrawl, Neo4j) | **Downgraded from mandatory to recommended** — secrets were never publicly exposed; rotation is good hygiene but not a release blocker |
| `.env.test` with personal IP in history | **Eliminated** |
| Incompatible clones/forks after rewrite | **N/A** — no external clones exist |

**Revised Phase 1 effort:** ~3-5 hours (down from 5-8 hours — Tasks 1-3 eliminated).

---

## 9. Priority-Ordered Remediation Plan

### Phase 1: CRITICAL — Blocks Release

| # | Task | Effort | Details |
|---|------|--------|---------|
| ~~1~~ | ~~Run git history secret scan~~ | ~~30 min~~ | **ELIMINATED** — fresh git init, no history (§8) |
| ~~2~~ | ~~Rewrite git history~~ | ~~1-2 hrs~~ | **ELIMINATED** — fresh git init (§8) |
| ~~3~~ | ~~Rotate all secrets~~ | ~~15 min~~ | **DOWNGRADED** — recommended but not blocking (§8) |
| 4 | Replace hardcoded IPs in code/config | 2-3 hrs | ~30 files in code + docker-compose (§1.2 Category A+B) |
| 5 | Replace personal paths | 1-2 hrs | `/path/to/external`, `/path/to/sift` in ~15 files |
| 6 | Add missing .gitignore entries | 10 min | `neo4j_logs/`, `.claude/`, `.mcp.json` — must be done BEFORE `git init` |
| 7 | Choose project name | Decision | Top pick: **knowloom** |
| 8 | Create LICENSE file | 5 min | Apache 2.0 |

### Phase 2: HIGH — Required Before Release

| # | Task | Effort | Details |
|---|------|--------|---------|
| 9 | Trim README.md | 2-3 hrs | 2,146 → ~350 lines; move content to docs/ |
| 10 | Generalize "memodo" category | 1-2 hrs | Replace with generic defaults; refactor Search.py |
| 11 | Scrub personal data from SDD files | 1-2 hrs | IPs and paths in ~100 files |
| 12 | Remove SDD context-management dir | 10 min | ~120 files of transient session state |
| 13 | Create NOTICE file | 15 min | Third-party dependency attribution |
| 14 | Create CODE_OF_CONDUCT.md | 10 min | Contributor Covenant v2.1 |
| 15 | Create CONTRIBUTING.md | 45 min | Dev setup, workflow, testing, SDD methodology |
| 16 | Scrub CLAUDE.md | 30 min | Replace IPs with placeholders |
| 17 | Clean .env.example | 30 min | Remove personal paths, genericize categories |
| 18 | Genericize documentation IPs | 1-2 hrs | README, MCP docs (~10 files) |

### Phase 3: MEDIUM — Recommended for Launch

| # | Task | Effort | Details |
|---|------|--------|---------|
| 19 | Set up GitHub Actions CI | 1-2 hrs | Ruff lint + unit tests + Trivy/CodeQL |
| 20 | Create issue/PR templates | 30 min | Bug report, feature request, question, PR template |
| 21 | Enable GitHub Discussions | 5 min | Repository settings |
| 22 | Add README badges | 15 min | CI, license, security, Docker, Python |
| 23 | Replace flake8+black with Ruff | 1 hr | Update requirements.txt, add pyproject.toml config |
| 24 | Create .dockerignore files | 15 min | Frontend and MCP server |
| 25 | Parameterize PostgreSQL credentials | 30 min | Environment variable substitution in config.yml |

### Phase 4: POST-LAUNCH — Nice to Have

| # | Task | Effort | Details |
|---|------|--------|---------|
| 26 | Docker Compose profiles | 1-2 hrs | Separate core vs optional services |
| 27 | CPU-only compose override | 1-2 hrs | `docker-compose.cpu.yml` |
| 28 | GHCR image publishing | 2-3 hrs | Frontend + MCP images |
| 29 | Coverage reporting + badge | 1 hr | pytest-cov + shields.io |
| 30 | Setup script (`make setup`) | 1-2 hrs | Interactive first-run setup |
| 31 | Dependabot config | 10 min | `dependabot.yml` |
| 32 | CODEOWNERS file | 5 min | Single maintainer default |
| 33 | SECURITY.md | 15 min | Vulnerability reporting policy |

### Estimated Total Effort

| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 1 (Critical) | 3-5 hours | Reduced from 5-8 hrs — git history tasks eliminated (§8) |
| Phase 2 (High) | 8-12 hours | |
| Phase 3 (Medium) | 3-5 hours | |
| Phase 4 (Post-launch) | 8-12 hours | |
| **Total pre-launch (Phases 1-3)** | **14-22 hours** | Reduced from 16-25 hrs |

---

## Files That Matter

### Core files requiring changes
- `.gitignore` — add missing patterns
- `docker-compose.yml` — parameterize IPs
- `docker-compose.test.yml` — parameterize IPs
- `README.md` — major trimming and scrubbing
- `CLAUDE.md` — IP scrubbing
- `.env.example` — remove personal paths/categories
- `config.yml` — parameterize PostgreSQL credentials
- `frontend/pages/2_🔍_Search.py` — refactor hardcoded `memodo` filter
- `frontend/utils/document_processor.py` — generalize category defaults
- `frontend/utils/graph_builder.py` — generalize category colors

### New files to create
- `LICENSE` — Apache 2.0
- `NOTICE` — dependency attribution
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- `CONTRIBUTING.md` — contributor guide
- `.github/workflows/ci.yml` — lint + unit tests
- `.github/workflows/security.yml` — Trivy + CodeQL
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- `docs/DATA-STORAGE.md` — moved from README
- `docs/KNOWLEDGE-GRAPH.md` — moved from README
- `docs/TESTING.md` — moved from README
- `docs/QUERY-ROUTING.md` — moved from README

### Files to remove
- `SDD/prompts/context-management/` — ~120 transient session files

---

## Security Considerations

- **Fresh git history eliminates history-based secret exposure** — no rewriting needed, no rotation mandatory (see §8)
- **Secret rotation still recommended** as good hygiene before the repo goes public, even though keys were never in git
- **All current files must be clean** before the first `git init` + commit — this is the only exposure vector
- **PostgreSQL `postgres:postgres` default** — document clearly as "development only, change for production"
- **`.env.example` must NOT contain real values** — verified clean except for personal paths (no actual keys)

## Testing Strategy

- Run full test suite (`./scripts/run-tests.sh`) after IP/path scrubbing to catch any broken defaults
- Verify all `os.getenv()` fallbacks work with `localhost` instead of personal IP
- Test `docker compose up -d` with only `.env.example` values (fresh clone simulation)
- Verify `.gitignore` additions with `git status` after changes

## Documentation Needs

- **User-facing**: Trimmed README, Quick Start guide, `.env` reference
- **Developer-facing**: CONTRIBUTING.md, TESTING.md (moved from README), SDD methodology overview
- **API docs**: Already available via Swagger UI (self-documenting)
- **MCP docs**: `mcp_server/README.md` already good (uses generic IPs)
