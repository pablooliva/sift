# Critical Research Review: Knowledge Summary Header (RESEARCH-031)

**Review Date:** 2026-02-03
**Reviewer:** Claude Opus 4.5
**Artifact:** `SDD/research/RESEARCH-031-knowledge-summary-header.md`

## Executive Summary

The research document is generally thorough and builds well on the existing SPEC-030 enrichment infrastructure. However, there are **critical gaps** in the "primary entity" selection algorithm that could produce confusing or misleading summaries, and **missing edge cases** that will cause problems in production. The research correctly identifies the data sources but **underestimates the complexity** of generating a useful summary from them.

**Overall Severity: MEDIUM** - Proceed with caution, address gaps in specification phase.

---

## Critical Gaps Found

### 1. **CRITICAL: Primary Entity Selection Algorithm is Flawed**

**Description:** The proposed algorithm selects the "primary entity" by counting `source_docs`:

```python
primary_entity = max(entities, key=lambda e: len(e.get('source_docs', [])))
```

**Why it matters:** This algorithm will often select the WRONG entity as primary:

- **High-frequency generic entities dominate**: An entity like "Payment" or "Agreement" may appear in many documents but isn't what the user searched for.
- **Query intent ignored**: If user searches "the other party", the primary entity should relate to "the other party", not the most-mentioned entity across all results.
- **Tie-breaking undefined**: Multiple entities with same source_docs count will return arbitrary winner from `max()`.

**Evidence:** The research does not analyze the actual distribution of entity mention counts or validate the algorithm against real queries.

**Risk:** Users see a summary for a different topic than they searched for, causing confusion and mistrust.

**Recommendation:**
1. Match entities against query terms (fuzzy/semantic) to find query-relevant primary
2. Fall back to most-mentioned only if no query match
3. Document tie-breaking behavior explicitly

---

### 2. **Missing: Query-Entity Alignment Analysis**

**Description:** No research was done on how well Graphiti entities align with user queries.

**Why it matters:**
- If user searches "invoices from 2024", do entities include "2024" or "Invoice"?
- If user searches "payments to Company X", is "Company X" extracted as an entity?
- Without this analysis, we can't know if summaries will be relevant.

**Evidence:** The research documents data structures but never validates that the data will produce useful summaries.

**Risk:** Summaries may be technically correct but semantically useless.

**Recommendation:** Add research section analyzing 5-10 real queries against real Graphiti data to validate entity extraction quality.

---

### 3. **Missing: Empty/Sparse Data Handling**

**Description:** The research lists conditional display criteria but doesn't address sparse data scenarios:

| Scenario | Current Handling | Problem |
|----------|-----------------|---------|
| 1 entity, 0 relationships | ? | Summary feels empty |
| 0 entities, 3 relationships | Show relationships only | Stated but no design |
| 1 entity, 1 doc | ? | "Summary" for single doc is useless |
| Entities but no source_docs | ? | Algorithm crashes (`max()` on empty) |

**Evidence:** Research line 371-381 lists conditions but lacks designs for edge cases.

**Risk:** Crashes or confusing UI states in production.

**Recommendation:** Define minimum thresholds (e.g., ≥2 entities OR ≥2 relationships with ≥2 source_docs) and design fallback UX.

---

### 4. **Missing: Relationship Quality Assessment**

**Description:** Research assumes all relationships are useful for summary, but Graphiti extracts many low-value relationships.

**Why it matters:**
- Relationships like "Document → mentions → Term" are noise
- Relationship types are not filtered or ranked
- "Key relationships" selection is just `[:5]` slice, no quality filter

**Evidence:** Research line 245-246:
```python
key_relationships = [r for r in relationships
                    if primary_entity['name'] in (r['source_entity'], r['target_entity'])]
```
No filtering by relationship quality or type.

**Risk:** Summaries show meaningless relationships like "Invoice → contains → Number".

**Recommendation:** Research which relationship types are high-value (e.g., "works_for", "located_in", "payment_to") vs. low-value (e.g., "mentions", "contains", "related_to").

---

### 5. **Underspecified: Document Snippet Generation**

**Description:** Research mentions showing document titles with context but doesn't specify where context comes from.

**Evidence:** Proposed UI shows:
```
• Contract Agreement - "establishes payment terms"
```

But the research doesn't explain:
- Where does "establishes payment terms" come from?
- Is it from document summary? Relationship fact? Entity context?
- What if document has no summary?

**Risk:** Implementation will make arbitrary choices, inconsistent UX.

**Recommendation:** Specify the exact source for document context snippets (priority order: relationship fact → document summary → document text snippet → none).

---

### 6. **Missing: Duplicate Entity Analysis**

**Description:** Research doesn't address how Graphiti handles entity variations.

**Why it matters:**
- "The Other Party" vs "Other Party" vs "The other party" - same or different?
- "Company X Inc." vs "Company X" - merged or separate?
- Summaries may list near-duplicates as separate entities.

**Evidence:** No mention of entity deduplication in summary generation (SPEC-030's dedup is per-document, not global).

**Risk:** Summaries show cluttered entity lists with duplicates.

**Recommendation:** Research Graphiti's entity resolution behavior and add global deduplication before summary generation if needed.

---

## Questionable Assumptions

### 1. **"<50ms additional processing" is not validated**

**Assumption:** Summary generation adds <50ms overhead.

**Why questionable:** The O(n) analysis is correct, but:
- Python `max()` with key function over 50 entities
- String matching for relationships (~20 × 50 = 1000 comparisons)
- Creating new dicts for UI display

**Alternative:** May be 50-200ms for complex queries. Benchmark before claiming.

---

### 2. **"Entities: 10-50, Relationships: 5-20" is unverified**

**Assumption:** These are "expected typical values" for entity/relationship counts.

**Why questionable:** No production data analysis. Complex documents (legal contracts, technical specs) may have 100+ entities.

**Risk:** Performance guardrails may be needed that weren't planned.

---

### 3. **"Data is already collected" ignores timing**

**Assumption:** Since `st.session_state.graphiti_results` exists, summary generation adds no latency.

**Why questionable:** The data IS collected, but:
- Is it available synchronously when summary code runs?
- Session state writes may be deferred in Streamlit
- Race conditions possible if summary renders before enrichment completes

**Recommendation:** Verify timing of session state population vs. summary rendering.

---

## Missing Perspectives

### User Perspective (Not Researched)

- What do users actually want from a "Knowledge Summary"?
- Is this solving a real problem or assumed need?
- Would users prefer a different summary format (e.g., narrative, bullet list, graph)?

### Data Quality Perspective

- How accurate are Graphiti's entity extractions?
- How often are entities wrong or missing?
- What's the false positive rate for relationships?

### Accessibility Perspective

- Entity type emojis may not render for all users
- Relationship arrows (→) may not be screen-reader friendly
- No alt text or ARIA considerations mentioned

---

## Research Disconnects

| Research Finding | Gap |
|------------------|-----|
| "Builds on SPEC-030 enrichment" | SPEC-030 is per-document; summary is cross-document aggregation. Different problem. |
| "Reuse `escape_for_markdown()`" | ✓ Valid |
| "Use Option A (pure aggregation)" | No comparative analysis with real data |
| "Entity type emoji mapping" | Only covers 7 types, research shows "unknown" is common |

---

## Recommended Actions Before Specification

### Priority 1 (Must Do)

1. **Fix primary entity selection algorithm**
   - Add query-matching logic
   - Handle ties explicitly
   - Handle empty source_docs

2. **Define minimum thresholds for displaying summary**
   - What's the minimum data needed for a useful summary?
   - Design the "no summary" state

3. **Test algorithm against 5 real queries**
   - Run actual searches
   - Inspect Graphiti results
   - Validate summary would be useful

### Priority 2 (Should Do)

4. **Research relationship quality**
   - Identify high-value vs. low-value relationship types
   - Add filtering to key relationship selection

5. **Specify document snippet sources**
   - Define priority order for context text
   - Handle missing context gracefully

### Priority 3 (Nice to Have)

6. **Benchmark performance**
   - Measure actual summary generation time
   - Validate <50ms claim

7. **Entity deduplication analysis**
   - Understand Graphiti's entity resolution
   - Plan for fuzzy duplicates

---

## Proceed/Hold Decision

**PROCEED WITH CAUTION**

The research provides a solid foundation but has critical gaps in the core algorithm. Before creating the specification:

1. ✅ Data sources are correctly identified
2. ✅ Security considerations inherited from SPEC-030
3. ⚠️ Primary entity algorithm needs redesign
4. ⚠️ Edge cases need explicit handling
5. ⚠️ Relationship quality filtering needed

**Recommendation:** Address Priority 1 items in the specification document. Don't require additional research phase, but spec must include fixes for the identified gaps.
