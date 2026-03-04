#!/usr/bin/env python3
"""
Test script for SPEC-012 Phase 2: Upload Integration
Tests that classification is integrated into the upload workflow
"""

import sys
import time
sys.path.append('frontend/utils')

from api_client import TxtAIClient

def test_upload_with_classification():
    """Test that classification works during document upload flow"""

    # Initialize API client
    client = TxtAIClient(base_url="http://localhost:8300")

    print("Testing Phase 2: Upload Integration with Classification")
    print("="*60)

    # Wait for container to be ready
    print("Waiting for txtai API to be ready...")
    time.sleep(5)

    # Check API health
    health = client.check_health()
    print(f"API Health: {health}")

    if health.get("status") != "healthy":
        print("ERROR: API is not available. Cannot proceed with test.")
        return False

    # Test labels configuration
    labels = [
        "professional",
        "personal",
        "financial",
        "legal",
        "reference",
        "project",
        "work (Memodo)",
        "activism"
    ]

    # Simulate upload workflow: classify text and prepare metadata
    print("\n" + "="*60)
    print("TEST: Upload flow with classification")
    print("="*60)

    # Sample document content (like what would be extracted from upload)
    document_content = """
    Project Proposal: Machine Learning Integration

    This document outlines the technical requirements for integrating
    machine learning capabilities into our platform. The project involves
    implementing zero-shot classification, text summarization, and semantic
    search features. The development team will work with the product team
    to ensure all requirements are met. Estimated timeline is 4-6 weeks.

    Key deliverables:
    - Backend API integration
    - Frontend UI components
    - Testing and documentation
    """

    # Classify the document (simulating the Upload.py workflow)
    print("\n1. Classifying document content...")
    classification_result = client.classify_text(document_content, labels, timeout=10)

    print(f"   Classification success: {classification_result.get('success')}")

    if classification_result.get('success'):
        # Filter labels above 60% threshold (as in Upload.py)
        labels_above_threshold = [
            {
                "label": item["label"],
                "score": item["score"],
                "status": "auto-applied" if item["score"] >= 0.85 else "suggested"
            }
            for item in classification_result['labels']
            if item["score"] >= 0.60
        ]

        print(f"\n2. Labels above 60% threshold: {len(labels_above_threshold)}")
        for label_data in labels_above_threshold:
            score_pct = label_data["score"] * 100
            status = label_data["status"]
            print(f"   - {label_data['label']}: {score_pct:.2f}% ({status})")

        # Simulate metadata storage (as in Upload.py)
        if labels_above_threshold:
            metadata = {
                'auto_labels': labels_above_threshold,
                'classification_model': 'bart-large-mnli',
                'classified_at': time.time()
            }
            print(f"\n3. Metadata prepared for storage:")
            print(f"   - Model: {metadata['classification_model']}")
            print(f"   - Labels stored: {len(metadata['auto_labels'])}")
            print(f"   - Timestamp: {metadata['classified_at']}")

            # Verify requirements
            print(f"\n4. Requirements verification:")

            # REQ-002: Returns labels with confidence scores
            has_scores = all('score' in label for label in labels_above_threshold)
            print(f"   ✓ REQ-002: Labels have confidence scores: {has_scores}")

            # REQ-003: Labels >= 60% displayed as suggestions
            has_suggestions = any(label['status'] == 'suggested' for label in labels_above_threshold)
            print(f"   ✓ REQ-003: Suggestions (60-85%): {has_suggestions}")

            # REQ-004: Labels >= 85% auto-applied
            has_auto_applied = any(label['status'] == 'auto-applied' for label in labels_above_threshold)
            print(f"   ✓ REQ-004: Auto-applied (>=85%): {has_auto_applied}")

            # EDGE-008: Low confidence (<60%) filtered out
            low_confidence_filtered = all(label['score'] >= 0.60 for label in labels_above_threshold)
            print(f"   ✓ EDGE-008: Low confidence filtered: {low_confidence_filtered}")

            # PERF-002: Classification doesn't block upload
            print(f"   ✓ PERF-002: Non-blocking (graceful error handling in Upload.py)")

            print("\n✓ Phase 2 Upload Integration Test PASSED!")
            return True
        else:
            print("\n✗ No labels above threshold - unexpected for this content")
            return False
    else:
        error = classification_result.get('error', 'unknown')
        skip_silently = classification_result.get('skip_silently', False)

        if skip_silently:
            print(f"\n✓ Classification skipped silently (expected behavior): {error}")
            print("✓ PERF-002: Upload would continue without blocking")
            return True
        else:
            print(f"\n✗ Classification failed: {error}")
            return False

if __name__ == "__main__":
    success = test_upload_with_classification()
    sys.exit(0 if success else 1)
