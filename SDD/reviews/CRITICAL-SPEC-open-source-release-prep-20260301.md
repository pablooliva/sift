# Specification Critical Review: SPEC-046 Open Source Release Preparation

**Date:** 2026-03-01
**Reviewer:** Claude Sonnet 4.6 (adversarial review)
**Artifact:** `SDD/requirements/SPEC-046-open-source-release-prep.md`

## Executive Summary

SPEC-046 is well-structured and captures the research findings faithfully. However, it has one genuine **contradiction** that will cause the Phase 1 verification gate to fail unexpectedly, one **inconsistency** in phase assignment for a key task, and several **ambiguities** that implementers will have to guess about. None of these are showstoppers, but the contradiction (Phase 1 verification vs. deferred doc-IP scrubbing) will cause an implementation dead-end on the critical path. Four specific gaps from the research and critical review were also not translated into requirements.

### Severity: MEDIUM

---

## Contradiction That Will Cause Implementation Dead-End

### 1. Phase 1 Grep Verification Cannot Pass While Phase 2 Has Doc IPs (HIGH)

The Phase 1 verification checklist (line 269) states:
> `grep -r 'YOUR_SERVER_IP' .` returns zero results (excluding `.git/`)

But Appendix Phase 2 Task #23 is:
> "Genericize IPs in documentation files (README, MCP docs) — 1-2 hrs"

The research identified ~4 IP occurrences in README, ~6 in CLAUDE.md, ~10 in MCP docs. These are **not** in `.gitignore`, so they will be found by the Phase 1 grep check. If the implementer completes all of Phase 1 as described and then runs the verification, it will fail on documentation files that were intentionally deferred to Phase 2.

**Consequence:** Implementer either (a) hits a wall at the Phase 1 gate and stops, (b) silently moves doc scrubbing into Phase 1 increasing scope, or (c) weakens the grep check to exclude docs — defeating its purpose.

**Two valid resolutions:**

Option A — Move doc IP scrubbing to Phase 1:
- Phase 1 Task #3 becomes: "Replace IPs in Category A+B code files AND Category C documentation"
- Effort increases to 4-6 hrs for Phase 1 IP replacement

Option B — Narrow the Phase 1 grep to code/config only:
- Change the grep command to: `grep -r 'YOUR_SERVER_IP' --include="*.py" --include="*.yml" --include="*.yaml" --include="*.json" --include="*.toml" --include="*.sh" .`
- Add a separate Phase 2 verification: `grep -r 'YOUR_SERVER_IP' . | grep -v '.git'` returns only `<server-ip>` placeholder forms

Option A is simpler and safer. Option B creates a two-tier verification that is easy to misread.

---

## Inconsistencies

### 2. PostgreSQL Credential Parameterization: Phase 2 or Phase 3? (MEDIUM)

The progress.md summary (added in planning) says:
> "PostgreSQL credentials → Phase 2 (moved up from Phase 3)"

The SPEC body's Implementation Notes references it as "Task 25 from research" with no phase. The Appendix assigns it as **Phase 3 Task #32**, mapped to "SEC-001 adj." The Phase 2 verification checklist has no checkbox for it. The Phase 3 verification checklist also has no checkbox for it.

This task is effectively orphaned — stated as elevated to Phase 2, implemented as Phase 3, and verified nowhere.

**Resolution:** Pick Phase 2, add it explicitly to the Phase 2 Appendix task list, and add a verification checkbox: `grep 'POSTGRES_PASSWORD' docker-compose.yml` shows env var substitution, not literal `postgres:postgres`.

### 3. REQ-012 Says "2-3" Examples; EDGE-004 and Verification Say "Exactly 3" (LOW)

- REQ-012: "removed, except for **2-3** representative examples"
- EDGE-004: "retain **exactly 3**"
- Phase 2 Verification: "`ls SDD/prompts/context-management/` shows **exactly 3** curated files"

If an implementer reasonably keeps 2 examples, the verification test (`exactly 3`) fails. Either the REQ or the test is wrong; they need to agree.

**Resolution:** Change REQ-012 to say "exactly 3" (or change the verification to "2-3 files").

---

## Ambiguities That Will Cause Implementation Confusion

### 4. REQ-003: `MANUAL_CATEGORIES` Format is Undefined (MEDIUM)

REQ-003 says Search.py should "dynamically read categories from `MANUAL_CATEGORIES` env var" but does not specify:
- **Format**: Comma-separated? JSON list? Pipe-delimited?
- **Empty/unset behavior**: Fall back to hardcoded defaults? Show no categories? Error?
- **Parsing edge case**: What if a category name contains a comma?

This is critical because Search.py, CONTRIBUTING.md (to document the env var), and `.env.example` all need to agree on the format. An implementer will pick something; it may not match what the original `document_processor.py` expects.

**Verification**: Existing `MANUAL_CATEGORIES` usage in `document_processor.py:73` should be checked first — whatever format is already established there must be the spec.

### 5. PERF-001 and UX-002 Cannot Be Tested Until Phase 3 Is Complete (MEDIUM)

- **PERF-001**: "`docker compose up -d` (core services, no GPU) must start successfully"
- **UX-002**: "`docker compose up -d` (without profiles) starts **only** core services"

Docker Compose profiles are Phase 3 Task #33 (listed as Post-Launch in the Appendix!). Before profiles are implemented, `docker compose up -d` starts ALL services including Neo4j and MCP. So PERF-001 and UX-002 are literally untestable until a feature that's in **Phase 4 (Post-Launch)** is implemented.

This means either:
(a) Docker Compose profiles must move to Phase 3 (pre-launch) — consistent with the Implementation Notes narrative but contradicted by the Appendix Phase 4 assignment
(b) PERF-001/UX-002 must be marked as "Phase 4+ requirements"

The Implementation Notes say "Docker Compose profiles (Phase 3)" but the Appendix puts them in Phase 4. Another phase-assignment inconsistency (same issue as finding #2).

### 6. EDGE-001: `.env.test` Not in .gitignore List or SEC-003 (MEDIUM)

EDGE-001 correctly identifies that `.env.test` must be gitignored or scrubbed before `git add -A`. However:
- REQ-004 lists four `.gitignore` additions: `neo4j_logs/`, `.claude/`, `.mcp.json`, `node_modules/` — **`.env.test` is absent**
- SEC-003 lists what `git status` must show as ignored: `.env`, `.claude/`, `neo4j_logs/`, `.mcp.json` — **`.env.test` is absent**

If `.env.test` still exists on disk (it was removed from tracking but may still be a file) and isn't gitignored, `git add -A` will commit it with its personal IP.

**Resolution:** Add `.env.test` to the REQ-004 `.gitignore` list (the existing `.gitignore` may already have `.env.*` covered, but the spec should call this out explicitly) and add it to SEC-003.

---

## Missing Requirements

### 7. No REQ Covering D-004's Downstream File Impacts (MEDIUM)

D-004 (qdrant-txtai fork ownership) has REQ-019: "decision documented — either migrate or retain as attribution." But if the fork IS migrated:

- `custom-requirements.txt` contains a GitHub URL pointing to `pablooliva/qdrant-txtai` — needs updating
- The `.whl` file checked into git may have internal metadata referencing the old URL
- CONTRIBUTING.md needs to document how to rebuild the wheel if someone forks the new repo
- The old `pablooliva/qdrant-txtai` fork may need to be kept (or a redirect established) to not break existing cloners of the old repo

There's no REQ for any of these. REQ-019 says the decision must be documented but says nothing about what changes if Option A (migrate) is chosen vs Option B (retain). An implementer who chooses to migrate the fork will have incomplete guidance.

### 8. No REQ for GitHub Secret Scanning Mention (LOW)

The research critical review explicitly noted: "GitHub secret scanning — Public repos get automatic secret scanning. This is a safety net but should be mentioned." SPEC-046 has no corresponding requirement. SECURITY.md (REQ-009) should include a note that GitHub automatically scans public repos for known secret patterns and will alert on any API key patterns — this is a secondary defense layer that users should know about.

### 9. No FAIL Scenario for Ruff Revealing Large-Scale Lint Violations (LOW)

Phase 3 correctly notes "there will be lint errors" from Ruff migration. But there's no failure scenario for what happens if Ruff reports 300+ violations requiring substantial refactoring. The CI-first approach (fix Ruff before writing `ci.yml`) is correct, but there's no contingency specified (e.g., "if Ruff error count exceeds 100, start with a minimal ruleset: `ruff check --select=E,F` and incrementally expand").

Without this, an implementer may either (a) try to fix 300+ violations before launch, adding 10+ hours, or (b) disable Ruff rules without a principled approach.

---

## Questionable Assumptions

### 10. "15-30 Minutes on Good Internet" Is Not Testable (MEDIUM)

UX-001 requires: "total time from clone to first search must be achievable in 15-30 minutes on good internet."

- "Good internet" is undefined (100 Mbps? 1 Gbps?)
- 10+ GB of downloads on 100 Mbps = ~14 minutes download time alone
- Docker image pulls are additional
- If models aren't pre-pulled for Ollama, first search won't work until `ollama pull nomic-embed-text` completes (~274 MB = ~2 min on 100 Mbps)

On a reasonable home connection (100 Mbps), the 15-30 minute target is borderline optimistic. This requirement cannot be verified objectively.

**Alternative**: Define UX-001 as "all steps to reach first search are documented with expected time ranges" — testable, achievable, and more honest.

### 11. "Comprehensible to Someone Unfamiliar" Is Untestable (LOW)

Manual Verification includes: "README is comprehensible to someone unfamiliar with the project." This is not verifiable by an implementer reviewing their own work.

**Alternative**: Replace with "README Quick Start walkthrough executed from scratch produces a working system" — the same thing, but testable.

### 12. Line Numbers in Implementation Constraints May Be Stale (LOW)

The spec lists `mcp_server/tests/test_graphiti.py:1637+` as a file requiring IP replacement. A test file with 1,637+ lines is unusual and suggests either the line number is wrong or the file has grown unexpectedly. If this line reference is wrong, the implementer will waste time looking at the wrong location.

**Recommendation:** Verify this line number against the actual file before implementation begins.

---

## Research Disconnects

### 13. Together AI Elevation to Quick Start Not Enforced by a REQ

The critical review said "local Ollama alternative should be a first-class option, not buried in docs/OLLAMA_INTEGRATION.md." REQ-011 requires documenting the Together AI requirement and "local Ollama alternative," but this could be satisfied with a one-line mention. There's no REQ specifying that the local Ollama path must be in Quick Start, must include the specific `ollama pull` commands, and must have its own step alongside the Together AI path. The intent is clear in the research but not enforced in the spec.

### 14. Contributor Perspective Missing Guidance on Component Isolation

The research critical review noted: "How to contribute to just ONE component (e.g., frontend only) without full stack." REQ-008 (CONTRIBUTING.md) mentions "local test workflow (unit tests without Docker)" but doesn't specify that CONTRIBUTING.md must document partial-stack development (e.g., "frontend development needs only Postgres + Qdrant, not GPU services"). This is an important contributor experience gap that didn't make it into the spec.

---

## Risk Reassessment

- **RISK-003** (zero-auth posture): Severity should be **HIGH**, not just medium concern. The research verified ALL services bind `0.0.0.0`. A user who deploys on a VPS or office server will have ALL their personal documents publicly accessible. This deserves a more prominent mitigation — consider making the `localhost`-only binding configuration a documented easy option, not just a footnote in SECURITY.md.

- **RISK-006** (qdrant-txtai fork): Understated. If the fork at `pablooliva/qdrant-txtai` is migrated away and the old fork is deleted, any existing user who cloned the pre-release repo and tries to rebuild would have a broken install. The spec should note that the old fork URL must be kept active (as a redirect or preserved fork) even if the canonical fork moves.

---

## Recommended Actions Before Proceeding

### Priority 1 (Must Fix — Will Block Implementation)

1. **Resolve the Phase 1 grep vs Phase 2 doc-IP contradiction** (Finding #1) — Choose Option A (move doc scrubbing to Phase 1) or Option B (narrow the grep to code/config files). Update the Phase 1 task list and verification checklist accordingly.

2. **Assign PostgreSQL credential parameterization to a definitive phase** (Finding #2) — Pick Phase 2 or Phase 3 (not both), add to the appropriate Appendix table, and add a verification checkbox.

3. **Add `.env.test` to the .gitignore list in REQ-004 and SEC-003** (Finding #6) — This is a git safety gap on the critical path.

### Priority 2 (Should Fix — Will Cause Confusion)

4. **Specify `MANUAL_CATEGORIES` env var format** (Finding #4) — Check `document_processor.py:73` for the existing format and encode it in REQ-003.

5. **Resolve Docker Compose profiles phase assignment** (Finding #5) — Move from Phase 4 to Phase 3, or explicitly mark PERF-001/UX-002 as Phase 4 requirements. Ensure Appendix and Implementation Notes agree.

6. **Align REQ-012 and EDGE-004 on "2-3" vs "exactly 3" examples** (Finding #3).

7. **Add downstream impacts for D-004 "migrate" option** (Finding #7) — What files change if the fork moves.

### Priority 3 (Nice to Have)

8. Make UX-001 testable (Finding #10) — Reframe as "all steps documented with time estimates" rather than "achievable in 15-30 minutes."

9. Add GitHub secret scanning mention to REQ-009/SECURITY.md scope (Finding #8).

10. Add a Ruff failure contingency to Phase 3 (Finding #9).

11. Verify `mcp_server/tests/test_graphiti.py:1637+` line reference (Finding #12).

---

## Proceed/Hold Decision

**PROCEED WITH FIXES.** The spec is implementable and the research is well-translated. The one genuine blocker (Phase 1 grep vs Phase 2 doc scrubbing) will cause an unexpected dead-end on the critical path but is easily resolved by choosing one of two clear options. The inconsistencies and ambiguities are all fixable with small spec edits before implementation begins. No fundamental rethinking of the approach is needed.

Minimum required before implementation: Fix Findings #1, #2, and #6.
