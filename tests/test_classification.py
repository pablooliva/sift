#!/usr/bin/env python3
"""
Test script for SPEC-012 classify_text() API method
Tests Phase 1: Backend Configuration + API Method
"""

import sys
import time
sys.path.append('frontend/utils')

from api_client import TxtAIClient

def test_classify_text():
    """Test the classify_text() method with sample text"""

    # Initialize API client
    client = TxtAIClient(base_url="http://localhost:8300")

    # Wait for container to be ready
    print("Waiting for txtai API to be ready...")
    time.sleep(10)

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

    # Test Case 1: Financial document
    print("\n" + "="*60)
    print("TEST 1: Financial document")
    print("="*60)

    text1 = """
    Invoice #12345

    Payment for services rendered in Q4 2024.
    Total amount: $5,000.00

    Please process payment by the end of the month.
    Tax ID: 12-3456789
    """

    result1 = client.classify_text(text1, labels, timeout=10)
    print(f"Success: {result1.get('success')}")
    print(f"Raw result: {result1}")  # DEBUG

    if result1.get("success"):
        print("Classifications:")
        results_list = result1.get("labels", [])
        print(f"  Found {len(results_list)} classifications")
        for item in results_list[:3]:  # Show top 3
            score_pct = item["score"] * 100
            print(f"  - {item['label']}: {score_pct:.2f}%")
    else:
        print(f"Error: {result1.get('error')}")

    # Test Case 2: Professional/work document
    print("\n" + "="*60)
    print("TEST 2: Professional/work document")
    print("="*60)

    text2 = """
    Project Status Report - Q4 2024

    The development team has completed all major milestones for the
    new feature release. Testing is underway and deployment is
    scheduled for next week. The client is pleased with progress.
    """

    result2 = client.classify_text(text2, labels, timeout=10)
    print(f"Success: {result2.get('success')}")

    if result2.get("success"):
        print("Classifications:")
        for item in result2.get("labels", [])[:3]:
            score_pct = item["score"] * 100
            print(f"  - {item['label']}: {score_pct:.2f}%")
    else:
        print(f"Error: {result2.get('error')}")

    # Test Case 3: Edge case - short text (should skip)
    print("\n" + "="*60)
    print("TEST 3: Edge case - text too short (EDGE-004)")
    print("="*60)

    text3 = "Hello world"

    result3 = client.classify_text(text3, labels, timeout=10)
    print(f"Success: {result3.get('success')}")
    print(f"Error: {result3.get('error')}")
    print(f"Skip silently: {result3.get('skip_silently', False)}")

    # Test Case 4: Edge case - empty text (should skip)
    print("\n" + "="*60)
    print("TEST 4: Edge case - empty text (EDGE-002)")
    print("="*60)

    text4 = "   "

    result4 = client.classify_text(text4, labels, timeout=10)
    print(f"Success: {result4.get('success')}")
    print(f"Error: {result4.get('error')}")
    print(f"Skip silently: {result4.get('skip_silently', False)}")

    # Test Case 5: Edge case - no labels (EDGE-006)
    print("\n" + "="*60)
    print("TEST 5: Edge case - no labels configured (EDGE-006)")
    print("="*60)

    result5 = client.classify_text("Some text", [], timeout=10)
    print(f"Success: {result5.get('success')}")
    print(f"Error: {result5.get('error')}")

    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    tests = [
        ("Financial document", result1.get("success")),
        ("Professional document", result2.get("success")),
        ("Short text (skip)", not result3.get("success") and result3.get("skip_silently")),
        ("Empty text (skip)", not result4.get("success") and result4.get("skip_silently")),
        ("No labels (error)", not result5.get("success"))
    ]

    for test_name, passed in tests:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(passed for _, passed in tests)

    if all_passed:
        print("\n✓ All tests passed!")
    else:
        print("\n✗ Some tests failed")

    return all_passed

if __name__ == "__main__":
    success = test_classify_text()
    sys.exit(0 if success else 1)
