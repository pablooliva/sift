# Phase 2 UI Integration - Manual Testing Guide

**SPEC:** SPEC-021-graphiti-parallel-integration.md
**Implementation Date:** 2025-12-20
**Requirements:** REQ-007 (dual result display), UX-002 (expandable sections)

## Prerequisites

Before testing, ensure:

1. **Docker Services Running:**
   ```bash
   docker compose --profile graphiti up -d
   ```

2. **Verify Services:**
   ```bash
   # Check txtai API
   curl http://YOUR_SERVER_IP:8300/count

   # Check Neo4j (Graphiti backend)
   curl http://YOUR_SERVER_IP:7474

   # Check Qdrant
   curl http://YOUR_SERVER_IP:7333/collections
   ```

3. **Environment Variables Set:**
   - `GRAPHITI_ENABLED=true` in `.env`
   - `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` configured
   - `TOGETHERAI_API_KEY` set

4. **Frontend Image Built with Dependencies:**
   ```bash
   # Rebuild frontend image to ensure graphiti-core is installed
   # (graphiti-core>=0.17.0 is in frontend/requirements.txt)
   docker compose build frontend
   docker compose up -d frontend
   ```

## Test Scenarios

### Test 1: Dual Search Display (REQ-007)

**Objective:** Verify dual search results are displayed correctly

**Steps:**
1. Navigate to Search page: `http://YOUR_SERVER_IP:8501/Search`
2. Enter query: "machine learning"
3. Click "Search"
4. Observe results

**Expected Behavior:**
- ✅ txtai results section appears with header "📚 txtai Semantic Search Results"
- ✅ Results display normally (title, score, metadata, preview)
- ✅ After txtai results, timing metrics appear showing:
  - txtai Search Time (ms)
  - Graphiti Search Time (ms)
  - Total Time (Parallel) (ms)
- ✅ Expandable section "🕸️ Knowledge Graph Results (Graphiti)" appears
- ✅ Caption "⚡ Searches executed in parallel for maximum performance" displayed

**Pass Criteria:**
- All elements visible
- No errors in UI
- Timing shows parallel execution (Total Time < txtai + Graphiti)

---

### Test 2: Graphiti Results Expansion (UX-002)

**Objective:** Verify Graphiti results expandable section works correctly

**Steps:**
1. Complete Test 1
2. Click on "🕸️ Knowledge Graph Results (Graphiti)" expander
3. Observe content

**Expected Behavior:**
- ✅ Expander opens to show Graphiti content
- ✅ If successful, displays:
  - "📊 Entities Discovered" section with entity list
  - Entity format: `emoji **name** _type_` (e.g., `💡 **Machine Learning** _concept_`)
  - "🔗 Relationships Discovered" section
  - Relationship format: `**source** → _type_ → **target**`
  - "About Graphiti Results" caption at bottom
- ✅ Entities limited to 10 with "... and X more entities" if >10
- ✅ Relationships limited to 10 with "... and X more relationships" if >10

**Pass Criteria:**
- Expander toggles correctly
- Content formatted properly
- Entity type emojis display correctly (👤 person, 🏢 organization, etc.)

---

### Test 3: Error Handling - Graphiti Unavailable (RELIABILITY-001)

**Objective:** Verify graceful degradation when Graphiti fails

**Steps:**
1. Stop Neo4j: `docker stop txtai-neo4j`
2. Navigate to Search page
3. Enter query and search

**Expected Behavior:**
- ✅ txtai results display normally (unaffected)
- ✅ Timing section shows txtai time only
- ✅ Graphiti expander appears but shows warning:
  - "⚠️ Graphiti Search Issue: [error message]"
  - Caption: "txtai results are still available above. Graphiti is experimental."

**Pass Criteria:**
- No UI crash or blank page
- txtai results fully functional
- Clear error message for Graphiti
- User can continue working

**Cleanup:**
```bash
docker start txtai-neo4j
```

---

### Test 4: Error Handling - Graphiti Disabled (Feature Flag)

**Objective:** Verify behavior when `GRAPHITI_ENABLED=false`

**Steps:**
1. Set `GRAPHITI_ENABLED=false` in `.env`
2. Restart frontend: `docker restart txtai-frontend`
3. Navigate to Search page
4. Enter query and search

**Expected Behavior:**
- ✅ Only txtai results displayed
- ✅ No "📚 txtai Semantic Search Results" header (no dual mode)
- ✅ No timing metrics section
- ✅ No Graphiti expander section
- ✅ Backward compatible with original search UI

**Pass Criteria:**
- UI identical to pre-Phase-2 behavior
- No errors or blank sections
- Search works normally

**Cleanup:**
```bash
# Restore GRAPHITI_ENABLED=true if testing continues
docker restart txtai-frontend
```

---

### Test 5: Empty Graphiti Results

**Objective:** Verify handling when Graphiti returns no entities/relationships

**Steps:**
1. Ensure Graphiti enabled and running
2. Search for a term not in any indexed documents (e.g., "xyzabc123")
3. Observe results

**Expected Behavior:**
- ✅ txtai shows "No results found" (standard behavior)
- ✅ Graphiti expander appears
- ✅ When expanded, shows:
  - "ℹ️ Graphiti search did not return results or encountered an issue."
  - Caption: "This is normal for new deployments or when Graphiti is unavailable."

**Pass Criteria:**
- No errors
- Clear messaging about empty results
- UI stable

---

### Test 6: Large Result Sets

**Objective:** Verify performance with many entities/relationships

**Steps:**
1. Upload several related documents (5-10 docs on same topic)
2. Wait for indexing to complete
3. Search for the common topic
4. Expand Graphiti results

**Expected Behavior:**
- ✅ Entities list shows max 10 items
- ✅ If >10 entities, shows "... and X more entities"
- ✅ Relationships list shows max 10 items
- ✅ If >10 relationships, shows "... and X more relationships"
- ✅ Page renders smoothly (no lag)

**Pass Criteria:**
- No performance degradation
- Pagination/limiting works correctly
- All data structured properly

---

### Test 7: Entity Type Emoji Mapping

**Objective:** Verify entity type emojis display correctly

**Expected Emoji Mapping:**
- person → 👤
- organization → 🏢
- location → 📍
- event → 📅
- concept → 💡
- technology → ⚙️
- document → 📄
- unknown types → 🔹

**Steps:**
1. Upload diverse documents (people, places, concepts)
2. Search to trigger entity extraction
3. Expand Graphiti results
4. Check entity emoji display

**Pass Criteria:**
- Correct emojis for each entity type
- Unknown types use default 🔹
- Emojis render in all browsers

---

### Test 8: Relationship Display Format

**Objective:** Verify relationship arrows and formatting

**Steps:**
1. Search query that generates relationships
2. Expand Graphiti results
3. Check relationships section

**Expected Format:**
```
- **Entity A** → _relationship_type_ → **Entity B**
```

**Pass Criteria:**
- Arrow (→) renders correctly
- Relationship type in italics
- Entity names in bold
- Readable and clear

---

### Test 9: Timing Metrics Accuracy

**Objective:** Verify parallel execution timing is correct

**Steps:**
1. Perform several searches
2. Record timing metrics displayed
3. Verify: Total Time ≈ max(txtai Time, Graphiti Time) (not sum)

**Expected Behavior:**
- ✅ Parallel timing: Total ≤ (txtai + Graphiti) and ≥ max(txtai, Graphiti)
- ✅ Overhead < 200ms (PERF-003 requirement)
- ✅ Times displayed in milliseconds (ms)

**Pass Criteria:**
- Timing metrics make sense
- Parallel execution evident (not sequential sum)
- Matches test expectations from unit tests

---

### Test 10: Multiple Searches (Session State)

**Objective:** Verify session state properly updates between searches

**Steps:**
1. Search for "machine learning"
2. Observe results and Graphiti entities
3. Search for "database design"
4. Observe results update

**Expected Behavior:**
- ✅ Results update correctly for each query
- ✅ Graphiti section updates with new entities/relationships
- ✅ No stale data from previous search
- ✅ Timing metrics refresh

**Pass Criteria:**
- Each search shows current data only
- No mixing of results from different queries
- Session state clean

---

## Regression Testing

Verify existing functionality still works:

### Backward Compatibility (COMPAT-001)

**Test existing features with Graphiti disabled:**
- [ ] Category filtering works
- [ ] AI label filtering works
- [ ] Search modes (hybrid/semantic/keyword) work
- [ ] Pagination works
- [ ] Document deletion works
- [ ] Full document view works
- [ ] Image results display correctly
- [ ] Summary display works

**Test existing features with Graphiti enabled:**
- [ ] All above features still functional
- [ ] No interference from dual search

---

## Performance Benchmarks

**Target Metrics (from PERF requirements):**

| Metric | Target | Test |
|--------|--------|------|
| txtai search time (Graphiti disabled) | <300ms | Measure 10 searches, avg |
| txtai search time (Graphiti enabled) | <300ms | Unchanged (PERF-001) |
| Parallel overhead | <200ms | Total - max(txtai, Graphiti) |
| UI render time | <500ms | From search click to results visible |

**How to Measure:**
1. Use browser DevTools Network tab
2. Note timing metrics displayed in UI
3. Record for multiple queries
4. Calculate averages

---

## Bug Reporting

If issues found, document:

1. **Environment:**
   - GRAPHITI_ENABLED value
   - Docker service status
   - Browser and version

2. **Steps to Reproduce:**
   - Exact query used
   - Filters applied
   - Actions taken

3. **Expected vs Actual:**
   - What should happen
   - What actually happened
   - Screenshots if applicable

4. **Logs:**
   ```bash
   docker logs txtai-frontend --tail 100
   docker logs txtai-api --tail 100
   ```

---

## Success Criteria Summary

Phase 2 UI Integration is successful if:

- [x] REQ-007: Dual results displayed in separate sections
- [x] UX-002: Graphiti results in expandable section
- [x] Error handling: Graceful degradation when Graphiti fails
- [ ] Performance: txtai unaffected by Graphiti (PERF-001)
- [ ] Backward compatibility: Existing tests pass (COMPAT-001)
- [ ] Manual testing: All 10 test scenarios pass
- [ ] Regression testing: All existing features work

---

## Next Steps After Testing

1. Document any bugs found
2. Fix critical issues
3. Create integration tests (automated)
4. Update user documentation
5. Prepare for Phase 3 (advanced features)
