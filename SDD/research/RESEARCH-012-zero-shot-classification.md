# RESEARCH-012-zero-shot-classification

**Feature:** Zero-Shot Classification Labels Component
**Started:** 2025-12-02
**Status:** Research Complete - Ready for Specification
**Config Reference:** `config.yml:99-102` (currently commented out)

## Overview

Enable zero-shot text classification using the BART-large-MNLI model. This allows documents to be automatically categorized without training data - users provide category labels and the model predicts which category each text belongs to.

**Key Distinction from Existing Categories:**
- Current system: Manual categories (personal, professional, activism, memodo) selected during upload
- Zero-shot labels: AI-generated classifications based on document content

---

## System Data Flow

### Key Entry Points
| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| API Client | `frontend/utils/api_client.py` | ~770+ | New `classify_text()` method |
| Upload Integration | `frontend/pages/1_📤_Upload.py` | 749-773 | Call classification during upload |
| Search Display | `frontend/pages/2_🔍_Search.py` | 305-321 | Display labels in results |
| Browse Display | `frontend/pages/4_📚_Browse.py` | 354-360 | Display labels in document cards |

### Data Transformation Flow
```
Document Text → API Client → txtai /workflow endpoint → BART-MNLI Model
                                                              ↓
Metadata Storage ← label + confidence ← Response [[label_idx, score], ...]
```

### External Dependencies
- **txtai API**: `/workflow` endpoint with `name: "labels"`
- **Model**: `facebook/bart-large-mnli` (405M parameters)
- **Alternative**: `valhalla/distilbart-mnli-12-3` (faster, smaller)

### Integration Points
1. **Config**: Add `labels:` section and workflow definition
2. **API Client**: New `classify_text()` method following summary pattern
3. **Upload.py**: Classification call after content extraction (~line 773)
4. **Search.py**: Display labels with filter capability
5. **Browse.py**: Display labels in document cards

---

## Stakeholder Mental Models

### Product Team Perspective
- **Value**: Automatic document organization without manual tagging
- **Concern**: Label quality and user trust in AI classifications
- **Need**: Clear UI showing this is "AI-suggested" vs manual categories
- **Expectation**: Users can filter/search by auto-labels

### Engineering Team Perspective
- **Pattern**: Follows existing caption/summary workflow integration
- **Complexity**: Medium - requires user-defined label sets (not just config)
- **Risk**: Model size (405M params) may impact memory/performance
- **Preference**: Use distilled model for production speed

### Support Team Perspective
- **FAQ Expected**: "Why did it classify my document as X?"
- **Training Need**: Explain zero-shot classification concept
- **Concern**: Users may expect 100% accuracy
- **Need**: Clear documentation on limitations and label set design

### User Perspective
- **Want**: Less manual work categorizing documents
- **Expectation**: Classifications make sense
- **Confusion Risk**: Difference between manual categories and auto-labels
- **Need**: Ability to correct/override AI labels

---

## Critical Design Decision: Label Set Management

### Problem
Zero-shot classification requires a predefined set of labels to classify against. Unlike summary/caption (which need no user input), labels need user configuration.

### Options Analyzed

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **1. Config-defined** | Labels defined in config.yml | Simple, no UI needed | Requires restart to change |
| **2. Session-based** | User enters labels during upload | Flexible | Inconsistent across uploads |
| **3. Settings page** | Dedicated UI to manage label sets | User control, persistent | More complex UI |
| **4. Replace categories** | Use labels instead of manual categories | Unified system | Breaking change, loss of control |

### Recommended Approach: Option 3 (Settings Page)
Create a simple settings/configuration page where users can:
1. Define a list of classification labels (e.g., "technical", "financial", "legal", "personal")
2. Enable/disable auto-classification during upload
3. Set confidence threshold for classification

**Storage**: Labels stored in a config file or database, loaded at upload time.

**Alternative (MVP)**: Option 1 (config-defined) for faster implementation, with Option 3 as enhancement.

---

## Files That Matter

### Core Logic (To Modify)
| File | Lines | Significance | Priority |
|------|-------|--------------|----------|
| `config.yml` | 99-102 | Enable labels pipeline | P0 |
| `frontend/utils/api_client.py` | 667-769 | Reference: summarize_text pattern | P0 |
| `frontend/pages/1_📤_Upload.py` | 749-773 | Integration point for classification | P0 |
| `frontend/pages/2_🔍_Search.py` | 305-321 | Display labels in results | P1 |
| `frontend/pages/4_📚_Browse.py` | 354-360 | Display labels in cards | P1 |

### Reference Files (Pattern Templates)
| File | Lines | Pattern |
|------|-------|---------|
| `api_client.py` | 580-665 | `caption_image()` - workflow API call |
| `api_client.py` | 667-769 | `summarize_text()` - input validation, error handling |
| `Upload.py` | 749-773 | Summary integration during upload |
| `document_processor.py` | 1039-1078 | `create_category_selector()` - UI pattern |

### Tests (Gaps)
- No existing tests for labels/classification
- Need unit tests for `classify_text()` method
- Need integration tests for upload workflow
- Test patterns in `frontend/tests/test_*.py`

---

## Security Considerations

### Authentication/Authorization
- Same as existing API calls - no additional auth needed
- Labels are per-document, not user-specific

### Data Privacy
- Document text sent to txtai API (local container)
- No external API calls - all processing is local
- Label results stored in document metadata

### Input Validation (4 Requirements)
1. **Text sanitization**: Strip control characters before classification
2. **Label validation**: Ensure labels are non-empty strings
3. **Confidence threshold**: Reject low-confidence classifications
4. **Length limits**: Cap text length for model input (similar to summary 100K limit)

### Injection Prevention
- No SQL injection risk (labels stored in JSON metadata)
- No command injection (no shell execution)
- No XSS risk (labels are strings, properly escaped in UI)

---

## Production Edge Cases

### Historical Issues (Based on Similar Pipelines)
| ID | Issue | Mitigation |
|----|-------|------------|
| EDGE-001 | Model timeout on long documents | Truncate to 100K chars |
| EDGE-002 | Empty or whitespace-only text | Skip classification, no error |
| EDGE-003 | Non-English text | Document limitation, may misclassify |
| EDGE-004 | Very short text (<50 chars) | Skip classification (insufficient context) |
| EDGE-005 | Ambiguous content (multiple labels apply) | Return top label with confidence |
| EDGE-006 | No labels configured | Skip classification with warning |
| EDGE-007 | Model unavailable (loading/OOM) | Retry once, then skip |
| EDGE-008 | Low confidence score (<50%) | Optionally skip or flag as "uncertain" |

### Failure Patterns
| ID | Pattern | Recovery |
|----|---------|----------|
| FAIL-001 | Timeout (>60s) | Log error, skip classification, continue upload |
| FAIL-002 | Model not loaded | Return 500, retry with 5s delay once |
| FAIL-003 | Invalid response format | Log, skip classification, continue |
| FAIL-004 | OOM error | Log, skip classification, container may restart |

---

## Testing Strategy

### Unit Tests (6 tests for `classify_text()`)
1. TEST-001: Valid text returns label and confidence
2. TEST-002: Empty text returns appropriate error
3. TEST-003: Short text (<50 chars) skips classification
4. TEST-004: Timeout handling returns error dict
5. TEST-005: Invalid label list handling
6. TEST-006: Response parsing with different formats

### Integration Tests (5 tests)
1. INT-001: Full workflow from /workflow endpoint
2. INT-002: Upload with classification enabled
3. INT-003: Upload with classification disabled
4. INT-004: Search filtering by auto-labels
5. INT-005: Browse display of auto-labels

### Edge Case Tests (8 tests - matching EDGE cases)
1. EDGE-TEST-001 through EDGE-TEST-008

### Manual Testing Checklist
1. [ ] Upload text document, verify classification appears
2. [ ] Upload short document, verify graceful skip
3. [ ] Search and filter by auto-label
4. [ ] View document details showing label with confidence
5. [ ] Test with different label sets
6. [ ] Verify model timeout handling

### Performance Testing
- Measure classification time vs document length
- Memory usage with BART-large-MNLI loaded
- Compare with distilled model alternative

---

## Documentation Needs

### User-Facing Documentation
1. **Feature overview**: What zero-shot classification does
2. **Label set guide**: How to choose effective labels
3. **Limitations**: Non-English text, confidence thresholds, accuracy expectations

### Developer Documentation
1. **API reference**: `classify_text()` method signature and usage
2. **Configuration guide**: How to enable/configure labels
3. **Troubleshooting**: Common errors and solutions

### Configuration Documentation
1. **config.yml changes**: Enable labels pipeline
2. **Label set configuration**: How to define custom labels
3. **Performance tuning**: Model selection (full vs distilled)

---

## API Details (from txtai Documentation)

### Labels Pipeline Response Format
```python
# Input
labels(text, ["label1", "label2", "label3"])

# Response: List of (label_index, confidence_score) sorted by highest score
[[0, 0.9987], [1, 0.0013], [2, 0.0001]]

# Interpretation
# Label at index 0 ("label1") has 99.87% confidence
# Label at index 1 ("label2") has 0.13% confidence
```

### Configuration Required
```yaml
# config.yml additions
labels:
  path: facebook/bart-large-mnli  # or valhalla/distilbart-mnli-12-3

workflow:
  # ... existing workflows ...
  labels:
    tasks:
      - action: labels
```

### API Call Pattern
```python
# Via /workflow endpoint
response = requests.post(
    f"{base_url}/workflow",
    json={
        "name": "labels",
        "elements": [text],
        # Note: labels list may need to be passed differently
    },
    timeout=60
)
```

### Implementation Note
The txtai labels pipeline requires labels at inference time. Need to verify if:
1. Labels can be passed via workflow API, or
2. Labels must be configured statically, or
3. A custom wrapper is needed

**Action Required**: Test actual API behavior before implementation.

---

## Metadata Storage Structure

### Proposed Document Metadata
```json
{
  "id": "uuid",
  "text": "document content",
  "indexed_at": 1733140800,
  "categories": ["personal"],           // Manual categories (existing)
  "auto_labels": [                       // AI-generated labels (new)
    {"label": "technical", "score": 0.92},
    {"label": "tutorial", "score": 0.78}
  ],
  "classification_model": "bart-large-mnli",
  "classified_at": 1733140800,
  "classification_labels": ["technical", "tutorial", "reference", "personal"]
}
```

### Display Priority
Search/Browse should show:
1. Manual categories (user-selected)
2. Top auto-label with confidence (if available)
3. Full label list in document detail view

---

## Implementation Complexity Assessment

### Effort Estimate
| Phase | Task | Estimate |
|-------|------|----------|
| Phase 1 | Config + API method | 1 hour |
| Phase 2 | Upload integration | 1.5 hours |
| Phase 3 | Search/Browse display | 1.5 hours |
| Phase 4 | Label set management (MVP) | 2 hours |
| Phase 5 | Testing | 3 hours |
| **Total** | | **9 hours** |

### Risk Assessment
| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Model performance (slow) | Medium | High | Use distilled model |
| Memory usage | Medium | Medium | Monitor, consider lazy loading |
| Label API complexity | Low | Medium | Test before implementation |
| User confusion (labels vs categories) | Medium | Low | Clear UI labeling |

---

## Open Questions for Planning Phase

1. **MVP vs Full**: Should Phase 4 (label management UI) be deferred?
2. **Model choice**: Use full BART-large or distilled version?
3. **Confidence threshold**: What minimum confidence to display labels?
4. **Multi-label**: Show top 1, top 3, or all labels above threshold?
5. **Label source**: Config file, database, or session state?
6. **Filter integration**: Add auto-label filter to Search sidebar?

---

## Research Status: READY FOR SPECIFICATION

### Completed Research
- [x] System data flows mapped with file:line references
- [x] Stakeholder perspectives documented (4 perspectives)
- [x] Edge cases identified (8 cases)
- [x] Failure patterns documented (4 patterns)
- [x] Security analysis complete (4 validation requirements)
- [x] Testing strategy defined (6 unit + 5 integration + 8 edge case tests)
- [x] Documentation needs identified (3 user + 3 developer docs)
- [x] Files that matter documented with line references
- [x] API behavior researched from txtai documentation

### Key Findings Summary
1. **Backend Ready**: labels pipeline is pre-configured in config.yml (just uncommented)
2. **Pattern Exists**: Follow summary/caption integration pattern exactly
3. **4 Files to Modify**: config.yml, api_client.py, Upload.py, Search.py, Browse.py
4. **Key Decision**: Need label set management (config or UI)
5. **Low-Medium Complexity**: ~9 hours estimated development
6. **Medium Risk**: Model performance and user understanding

### Ready for `/sdd:planning-start` to create SPEC-012-zero-shot-classification.md
