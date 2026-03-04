# Production Validation Guide - SPEC-031 Knowledge Summary Header

**Date:** 2026-02-04
**Feature:** Knowledge Summary Header
**Status:** Ready for Production Validation

## Prerequisites

- [ ] Frontend running at configured URL (e.g., http://YOUR_SERVER_IP:8501)
- [ ] txtai API with Graphiti enabled
- [ ] Documents indexed with Graphiti entities/relationships
- [ ] Search functionality working

## Validation Queries

Execute the following 5 queries using the live Streamlit Search page and document the results.

### Query 1: Known Person Name

**Query:** `[Insert name of person from your documents]`

**Expected Behavior:**
- Primary entity should be the person's name
- Entity type should be "person" (👤)
- Documents mentioning the person should appear
- Documents should be ordered by search score (highest first)

**Observations:**
- [ ] Summary displayed above search results
- [ ] Primary entity matches query
- [ ] Document ordering correct (score-based)
- [ ] Display mode: ☐ Full ☐ Sparse ☐ None

**Notes:**


---

### Query 2: Company/Organization Name

**Query:** `[Insert organization name from your documents]`

**Expected Behavior:**
- Primary entity should be the organization name
- Entity type should be "organization" (🏢)
- Documents mentioning the organization should appear
- Related entities may show in relationships

**Observations:**
- [ ] Summary displayed above search results
- [ ] Primary entity matches query
- [ ] Document ordering correct (score-based)
- [ ] Display mode: ☐ Full ☐ Sparse ☐ None

**Notes:**


---

### Query 3: Topic Search

**Query:** `[Insert topic like "payment terms", "contract renewal", etc.]`

**Expected Behavior:**
- Primary entity should be the most query-relevant concept
- May have multiple entities related to the topic
- Should show key relationships if sufficient data

**Observations:**
- [ ] Summary displayed above search results
- [ ] Primary entity selection makes sense for query
- [ ] Display mode: ☐ Full ☐ Sparse ☐ None
- [ ] Relationships shown (if full mode): ☐ Yes ☐ No

**Notes:**


---

### Query 4: Document Type

**Query:** `[Insert document type like "invoice", "agreement", etc.]`

**Expected Behavior:**
- Primary entity may be document type or related concept
- Multiple documents of that type should appear
- May show sparse mode (document type less likely to have rich relationships)

**Observations:**
- [ ] Summary displayed above search results
- [ ] Primary entity selection appropriate
- [ ] Display mode: ☐ Full ☐ Sparse ☐ None
- [ ] Document count matches expectations

**Notes:**


---

### Query 5: Ambiguous Query

**Query:** `[Insert query that could match multiple entity types]`

**Expected Behavior:**
- Primary entity should be the most query-matched entity (not necessarily highest frequency)
- Entity selection algorithm should prioritize query relevance
- Should handle multiple entity types gracefully

**Observations:**
- [ ] Summary displayed above search results
- [ ] Primary entity selection reasonable (query-matched, not just most frequent)
- [ ] Display mode: ☐ Full ☐ Sparse ☐ None
- [ ] Multiple entity types present: ☐ Yes ☐ No

**Notes:**


---

## Summary Statistics

**Query Results Distribution:**
- Full mode: ___ out of 5 queries
- Sparse mode: ___ out of 5 queries
- No summary: ___ out of 5 queries

**Document Ordering Validation:**
- [ ] All queries showed documents in descending score order
- [ ] Highest relevance documents appeared first
- [ ] Document ordering matches REQ-003

**Entity Selection Validation:**
- [ ] Primary entities matched query intent (not just highest frequency)
- [ ] Query-matched entities prioritized over generic entities
- [ ] Entity selection meets REQ-002

**Performance Observations:**
- Summary display delay: ☐ None ☐ Barely noticeable ☐ Noticeable
- Search result load time: ☐ <1s ☐ 1-2s ☐ >2s
- Any errors or crashes: ☐ No ☐ Yes (describe below)

**Error Notes:**


---

## Acceptance Criteria

Production validation PASSES if:

- [x] All 5 queries execute without errors
- [x] At least 3 out of 5 queries show a summary (full or sparse)
- [x] Primary entity selection is logical and query-relevant for all summaries
- [x] Document ordering matches search scores (highest first)
- [x] No crashes, errors, or display issues
- [x] Summary displays above results with clear visual separation

---

## Next Steps

After completing this validation:

1. **If validation PASSES:**
   - Mark production validation complete in progress.md
   - Update critical review status
   - Proceed with `/sdd:implementation-complete`

2. **If validation FAILS:**
   - Document specific failures
   - Create tasks for fixes
   - Re-run validation after fixes

---

## Validation Completed By

**Name:** _________________
**Date:** _________________
**Result:** ☐ PASS ☐ FAIL

**Overall Notes:**


