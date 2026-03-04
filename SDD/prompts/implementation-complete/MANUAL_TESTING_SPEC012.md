# Manual Testing Checklist - SPEC-012: Zero-Shot Classification Labels

**Feature**: Auto-Classification with Zero-Shot Learning
**Specification**: `SDD/requirements/SPEC-012-zero-shot-classification.md`
**Test Date**: _____________
**Tester**: _____________

---

## Prerequisites

- [ ] txtai backend is running (`http://localhost:8300`)
- [ ] Frontend is running (`streamlit run frontend/Home.py`)
- [ ] Backend config has labels pipeline enabled (`config.yml:102-116`)
- [ ] At least one test document available for upload (>50 chars)

---

## Test Suite 1: Upload & Classification

### MAN-001: Upload Document with Auto-Classification

**Steps:**
1. Navigate to Upload page (`📤 Upload`)
2. Upload a text document with clear category (e.g., financial document)
3. Wait for upload to complete

**Expected Results:**
- [ ] Upload completes successfully
- [ ] No errors or crashes during classification
- [ ] Progress indicator shown during classification
- [ ] Document appears in Search results

**Notes:** _______________________________________________________________

---

### MAN-002: Verify Auto-Labels in Search Results

**Steps:**
1. Navigate to Search page (`🔍 Search`)
2. Search for the uploaded document
3. View search results card

**Expected Results:**
- [ ] Document appears in search results
- [ ] Auto-labels visible with ✨ sparkle icon (AI indicator)
- [ ] Confidence percentage displayed
- [ ] Labels have appropriate confidence indicators (🟢 🟡 🟠)
- [ ] Status icon shown (✓ for auto-applied, ? for suggested)

**Notes:** _______________________________________________________________

---

### MAN-003: Verify Auto-Labels in Full Document View

**Steps:**
1. From Search results, click "View Details" on the document
2. Scroll to auto-labels section

**Expected Results:**
- [ ] Auto-labels section visible in full document view
- [ ] ✨ AI indicator present
- [ ] Each label shows:
  - Label name
  - Confidence percentage
  - Progress bar (visual indicator)
  - Status (auto-applied ✓ or suggested ?)
- [ ] Labels sorted by confidence (highest first)

**Notes:** _______________________________________________________________

---

## Test Suite 2: Browse Page Display

### MAN-004: Verify Auto-Labels in Browse Page Cards

**Steps:**
1. Navigate to Browse page (`📚 Browse`)
2. Locate the uploaded document in the grid view

**Expected Results:**
- [ ] Document card displays auto-labels
- [ ] ✨ AI indicator present
- [ ] Top 2-3 labels visible (if multiple labels assigned)
- [ ] Confidence indicators visible (🟢 🟡 🟠)

**Notes:** _______________________________________________________________

---

### MAN-005: Verify Auto-Labels in Browse Details View

**Steps:**
1. From Browse page, click on a document to view details
2. Check auto-labels display

**Expected Results:**
- [ ] Auto-labels section visible in details view
- [ ] All labels above 60% threshold shown
- [ ] Progress bars and percentages displayed
- [ ] Status icons (✓ or ?) shown correctly

**Notes:** _______________________________________________________________

---

## Test Suite 3: Search Filtering

### MAN-006: Test Auto-Label Filter

**Steps:**
1. Navigate to Search page
2. Expand "✨ AI Label Filters" in sidebar
3. Select an auto-label from filter options
4. Apply filter

**Expected Results:**
- [ ] Filter expander shows available auto-labels
- [ ] Selecting a filter updates results
- [ ] Only documents with selected auto-label shown
- [ ] Filter indicator visible above results ("Filtered by AI Label: ...")
- [ ] Clear filter option works

**Notes:** _______________________________________________________________

---

## Test Suite 4: Settings UI Configuration

### MAN-007: Label Management

**Steps:**
1. Navigate to Settings page (`⚙️ Settings`)
2. View current label list
3. Add a new label (e.g., "testing")
4. Delete a label
5. Click "Reset to Defaults"

**Expected Results:**
- [ ] Current labels displayed in list
- [ ] Can add new label via text input + button
- [ ] Added label appears in list immediately
- [ ] Can delete labels with delete button
- [ ] Reset restores default labels from config.yml
- [ ] Success message shown for changes

**Notes:** _______________________________________________________________

---

### MAN-008: Threshold Configuration

**Steps:**
1. In Settings page, locate threshold sliders
2. Adjust "Auto-Apply Threshold" slider
3. Adjust "Suggestion Threshold" slider
4. Observe threshold preview metrics

**Expected Results:**
- [ ] Two sliders visible:
  - Auto-Apply Threshold (default 85%)
  - Suggestion Threshold (default 60%)
- [ ] Preview shows three ranges:
  - Auto-applied (≥ auto threshold) - green
  - Suggested (between suggestion and auto) - orange
  - Hidden (< suggestion threshold) - gray
- [ ] Can't set suggestion threshold above auto-apply threshold
- [ ] Changes take effect immediately

**Notes:** _______________________________________________________________

---

### MAN-009: Enable/Disable Toggle

**Steps:**
1. In Settings page, locate "Enable Auto-Classification" toggle
2. Turn toggle OFF
3. Upload a new document
4. Turn toggle back ON
5. Upload another document

**Expected Results:**
- [ ] Toggle visible at top of Settings page
- [ ] When disabled: uploads don't classify documents
- [ ] When enabled: uploads include classification
- [ ] Toggle state persists during session
- [ ] Status message shown when toggled

**Notes:** _______________________________________________________________

---

### MAN-010: Settings Integration with Upload

**Steps:**
1. In Settings, add a custom label (e.g., "urgent")
2. Set auto-apply threshold to 70%
3. Navigate to Upload page
4. Upload a document

**Expected Results:**
- [ ] Classification uses updated label list (including "urgent")
- [ ] Auto-apply threshold of 70% is applied
- [ ] Labels ≥70% marked as "auto-applied"
- [ ] Labels 60-69% marked as "suggested"
- [ ] Settings changes reflected in classification results

**Notes:** _______________________________________________________________

---

## Test Suite 5: Edge Cases

### EDGE-MAN-001: Short Document (<50 chars)

**Steps:**
1. Upload a very short document (e.g., "Hello world")

**Expected Results:**
- [ ] Upload succeeds (not blocked)
- [ ] No auto-labels assigned
- [ ] No error message shown to user
- [ ] Document still searchable and browseable

**Notes:** _______________________________________________________________

---

### EDGE-MAN-002: Empty or Whitespace Document

**Steps:**
1. Create a text file with only spaces/newlines
2. Upload the file

**Expected Results:**
- [ ] Upload succeeds
- [ ] No auto-labels assigned
- [ ] No error shown
- [ ] Document appears in system (with no content)

**Notes:** _______________________________________________________________

---

### EDGE-MAN-003: Document with Special Characters

**Steps:**
1. Upload a document with:
   - Non-English characters (accents, umlauts, CJK)
   - Symbols (@#$%^&*)
   - HTML/code snippets

**Expected Results:**
- [ ] Upload succeeds
- [ ] Classification completes (may or may not assign labels)
- [ ] No crashes or errors
- [ ] Special characters preserved in document

**Notes:** _______________________________________________________________

---

### EDGE-MAN-004: Ambiguous Document

**Steps:**
1. Upload a document that could fit multiple categories
2. Example: "I need legal advice about my personal financial project"

**Expected Results:**
- [ ] Multiple labels assigned (if above 60%)
- [ ] All relevant labels shown
- [ ] Confidence scores vary across labels
- [ ] Top 2-3 most relevant labels emphasized

**Notes:** _______________________________________________________________

---

### EDGE-MAN-005: Classification with Disabled Setting

**Steps:**
1. Go to Settings, disable auto-classification
2. Upload a document
3. Check Search/Browse for auto-labels

**Expected Results:**
- [ ] Upload succeeds normally
- [ ] No auto-labels assigned
- [ ] No classification API call made
- [ ] No errors or delays

**Notes:** _______________________________________________________________

---

## Test Suite 6: Performance & UX

### PERF-MAN-001: Classification Speed

**Steps:**
1. Upload a typical document (1-10KB text)
2. Time the classification process

**Expected Results:**
- [ ] Classification completes in <10 seconds
- [ ] Upload workflow feels responsive
- [ ] Progress spinner/indicator shown during wait
- [ ] No UI freezing

**Actual Time:** _________ seconds

**Notes:** _______________________________________________________________

---

### PERF-MAN-002: Large Document Handling

**Steps:**
1. Upload a large document (>100KB text)
2. Observe classification behavior

**Expected Results:**
- [ ] Upload succeeds
- [ ] Classification either succeeds or fails gracefully
- [ ] No crashes or timeouts blocking upload
- [ ] Large document truncated if necessary
- [ ] Classification completes within 15 seconds

**Notes:** _______________________________________________________________

---

### UX-MAN-001: Visual Distinction

**Steps:**
1. Upload document, view in Search
2. Compare auto-labels with manual categories

**Expected Results:**
- [ ] Auto-labels clearly distinct from manual categories
- [ ] ✨ sparkle icon makes AI-generated labels obvious
- [ ] Color/style differences visible
- [ ] User can easily tell which labels are automatic

**Notes:** _______________________________________________________________

---

### UX-MAN-002: Error Handling

**Steps:**
1. Stop txtai backend (docker stop txtai)
2. Try to upload a document
3. Restart backend

**Expected Results:**
- [ ] Upload completes without blocking
- [ ] Graceful error message (if shown)
- [ ] Document still uploaded and accessible
- [ ] No crashes or confusing errors
- [ ] After backend restart, classification works again

**Notes:** _______________________________________________________________

---

## Test Suite 7: Help & Documentation

### DOC-MAN-001: Settings Help Text

**Steps:**
1. Navigate to Settings page
2. Expand help sections

**Expected Results:**
- [ ] "About Auto-Classification" section present
- [ ] Help text explains feature clearly
- [ ] Technical details available (model, approach)
- [ ] Examples provided for label management

**Notes:** _______________________________________________________________

---

## Summary & Sign-Off

### Overall Results

**Total Tests Executed:** _____ / 27
**Tests Passed:** _____
**Tests Failed:** _____
**Blockers Found:** _____

### Issues Discovered

1. ________________________________________________________________
2. ________________________________________________________________
3. ________________________________________________________________

### Recommendations

________________________________________________________________
________________________________________________________________
________________________________________________________________

### Sign-Off

**Feature Status:** [ ] Ready for Production  [ ] Needs Fixes  [ ] Needs More Testing

**Tester Signature:** ________________________  **Date:** __________

**Reviewer Signature:** ______________________  **Date:** __________

---

## Appendix: Test Data

### Sample Financial Document

```
Invoice #2024-1234
Date: December 2, 2024

Services Rendered:
- Consulting Services: $5,000
- Development Work: $8,000
- Support & Maintenance: $2,000

Total: $15,000

Payment Terms: Net 30
Tax ID: 12-3456789

Please remit payment to:
Account #: 9876543210
Routing #: 123456789
```

### Sample Professional Document

```
Project Status Report - Q4 2024

Team: Engineering
Project: Zero-Shot Classification Feature
Status: In Progress (90% complete)

Completed This Quarter:
- Backend API integration
- Upload workflow integration
- Display components (Search & Browse)
- Settings UI implementation

Remaining Work:
- Comprehensive testing
- Performance validation
- Documentation finalization

Next Steps:
1. Execute full test suite
2. Address any issues found
3. Prepare for production release
```

### Sample Personal Document

```
Personal Journal Entry - December 2024

Today was a productive day. I finally finished organizing my
home office and setting up my new filing system. I've been meaning
to do this for months, but work kept getting in the way.

Tomorrow I need to:
- Schedule dentist appointment
- Buy groceries
- Call Mom
- Finish reading that book Sarah recommended

Feeling grateful for good health and family.
```

### Sample Legal Document

```
Non-Disclosure Agreement

This Confidentiality Agreement ("Agreement") is entered into as of
December 2, 2024, by and between Company A and Company B.

WHEREAS, the parties wish to explore a business opportunity requiring
disclosure of confidential information;

NOW, THEREFORE, in consideration of the mutual covenants contained herein:

1. Definition of Confidential Information
2. Obligations of Receiving Party
3. Term and Termination
4. Miscellaneous

This Agreement shall be governed by the laws of the State of California.

Signatures:
_____________________  _____________________
Party A                Party B
```

---

**End of Manual Testing Checklist**
