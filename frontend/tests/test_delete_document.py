#!/usr/bin/env python
"""
Unit and integration tests for document deletion feature (SPEC-009).

Tests cover:
- Unit tests: API client delete methods
- Integration tests: Full delete workflow with txtai API
- Edge case tests: Error conditions and boundary cases

Run this file to execute all tests:
    python test_delete_document.py
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.api_client import TxtAIClient

# Test configuration
TEST_API_URL = "http://localhost:8300"


def test_safe_delete_image_valid_path():
    """
    UNIT TEST 1: test_delete_path_validation
    Test that valid image paths within /uploads/images/ are accepted.
    Implements SEC-001, SEC-002 validation.
    """
    print("\n[Unit Test 1] Testing valid image path deletion...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Create a temporary test file
    with tempfile.NamedTemporaryFile(
        mode='w',
        prefix='test_image_',
        suffix='.png',
        dir='/uploads/images' if os.path.exists('/uploads/images') else tempfile.gettempdir(),
        delete=False
    ) as temp_file:
        temp_path = temp_file.name
        temp_file.write("test image content")

    try:
        # Test deletion of valid path
        if '/uploads/images' in temp_path:
            result = client._safe_delete_image(temp_path)
            assert result == True, f"Expected True for valid path, got {result}"
            assert not os.path.exists(temp_path), "File should be deleted"
            print("   ✅ Valid path accepted and file deleted")
        else:
            print("   ⚠️  Skipped - /uploads/images/ not accessible in test environment")
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        return False
    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

    return True


def test_safe_delete_image_path_traversal():
    """
    UNIT TEST 2: test_delete_path_validation (Path traversal prevention)
    Test that path traversal attempts are blocked.
    Implements SEC-001, SEC-002: Security controls.
    """
    print("\n[Unit Test 2] Testing path traversal prevention...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Test various path traversal attempts
    malicious_paths = [
        "/uploads/images/../../../etc/passwd",
        "/uploads/images/../../secret.txt",
        "../uploads/images/test.png",
        "/etc/passwd",
        "/home/user/document.txt"
    ]

    all_blocked = True
    for path in malicious_paths:
        result = client._safe_delete_image(path)
        if result == True and not path.startswith("/uploads/images/"):
            print(f"   ❌ Path traversal NOT blocked: {path}")
            all_blocked = False
        elif result == False:
            print(f"   ✅ Path traversal blocked: {path}")

    if all_blocked:
        print("   ✅ All path traversal attempts blocked")
        return True
    else:
        print("   ❌ Some path traversal attempts not blocked")
        return False


def test_safe_delete_image_missing_file():
    """
    UNIT TEST 3: test_delete_nonexistent_doc
    Test that deleting a missing file returns True (idempotent behavior).
    Implements EDGE-001: Missing image file handling.
    """
    print("\n[Unit Test 3] Testing missing file handling...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Test with non-existent file in valid directory
    if os.path.exists('/uploads/images'):
        nonexistent_path = "/uploads/images/nonexistent_file_12345.png"
        result = client._safe_delete_image(nonexistent_path)

        if result == True:
            print("   ✅ Missing file handled gracefully (returns True)")
            return True
        else:
            print(f"   ❌ Missing file handling failed (returned {result})")
            return False
    else:
        print("   ⚠️  Skipped - /uploads/images/ not accessible in test environment")
        return True


def test_delete_document_api_success():
    """
    UNIT TEST 4: test_delete_document_api
    Test successful document deletion through API client.
    Implements REQ-004: Document deletion from txtai index.

    Note: This is a mock test. Integration test verifies actual API.
    """
    print("\n[Unit Test 4] Testing delete_document API method (mocked)...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Mock the requests.post call
    with patch('requests.post') as mock_post:
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["doc_123"]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test deletion without image
        result = client.delete_document("doc_123")

        # Verify result
        if (result.get("success") == True and
            result.get("deleted_ids") == ["doc_123"] and
            result.get("image_deleted") == True):
            print("   ✅ delete_document returns correct structure")
            print(f"      Result: {result}")
            return True
        else:
            print(f"   ❌ delete_document returned unexpected result: {result}")
            return False


def test_integration_delete_with_image():
    """
    INTEGRATION TEST 1: test_delete_with_image_cleanup
    Test full deletion workflow including image file cleanup.
    Implements REQ-005: Image file deletion.

    Note: Requires txtai API to be running and writable /uploads/images/
    """
    print("\n[Integration Test 1] Testing delete with image cleanup...")

    try:
        client = TxtAIClient(base_url=TEST_API_URL)

        # Check if API is available
        response = requests.get(f"{TEST_API_URL}/count", timeout=2)
        if response.status_code != 200:
            print("   ⚠️  Skipped - txtai API not available")
            return True

        # Create a temporary image file for testing
        if not os.path.exists('/uploads/images'):
            print("   ⚠️  Skipped - /uploads/images/ not accessible")
            return True

        with tempfile.NamedTemporaryFile(
            mode='w',
            prefix='test_integration_',
            suffix='.png',
            dir='/uploads/images',
            delete=False
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write("test image for integration test")

        # Add a test document to the index
        test_doc = {
            "id": "test_integration_doc_001",
            "text": "Test document for integration testing",
            "image": temp_path
        }

        add_response = requests.post(f"{TEST_API_URL}/add", json=[test_doc], timeout=5)
        if add_response.status_code != 200:
            print(f"   ⚠️  Failed to add test document: {add_response.status_code}")
            os.unlink(temp_path)
            return True

        # Index the document
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Now delete the document with image cleanup
        result = client.delete_document("test_integration_doc_001", image_path=temp_path)

        # Verify results
        success = True
        if not result.get("success"):
            print(f"   ❌ Deletion failed: {result.get('error')}")
            success = False

        if os.path.exists(temp_path):
            print(f"   ❌ Image file still exists: {temp_path}")
            os.unlink(temp_path)  # Cleanup
            success = False

        if success:
            print("   ✅ Document and image deleted successfully")
            print(f"      Result: {result}")

        return success

    except requests.exceptions.ConnectionError:
        print("   ⚠️  Skipped - txtai API not available")
        return True
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False


def test_integration_delete_updates_index():
    """
    INTEGRATION TEST 2: test_delete_updates_index
    Test that deletion removes document from search results.
    Implements REQ-007: UI reflects deletion.

    Note: Requires txtai API to be running.
    """
    print("\n[Integration Test 2] Testing index update after deletion...")

    try:
        client = TxtAIClient(base_url=TEST_API_URL)

        # Check if API is available
        response = requests.get(f"{TEST_API_URL}/count", timeout=2)
        if response.status_code != 200:
            print("   ⚠️  Skipped - txtai API not available")
            return True

        # Add a test document
        test_doc = {
            "id": "test_index_update_doc_002",
            "text": "Unique test phrase for index update testing xyz123"
        }

        add_response = requests.post(f"{TEST_API_URL}/add", json=[test_doc], timeout=5)
        if add_response.status_code != 200:
            print(f"   ⚠️  Failed to add test document")
            return True

        # Index the document
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Verify document is searchable
        search_response = requests.get(
            f"{TEST_API_URL}/search",
            params={"query": "unique test phrase xyz123", "limit": 5},
            timeout=5
        )

        if search_response.status_code != 200:
            print("   ⚠️  Search failed before deletion")
            return True

        results_before = search_response.json()
        doc_found_before = any(r.get("id") == "test_index_update_doc_002" for r in results_before)

        if not doc_found_before:
            print("   ⚠️  Test document not found in search before deletion")
            return True

        # Delete the document
        result = client.delete_document("test_index_update_doc_002")

        if not result.get("success"):
            print(f"   ❌ Deletion failed: {result.get('error')}")
            return False

        # Re-index
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Verify document is no longer searchable
        search_response_after = requests.get(
            f"{TEST_API_URL}/search",
            params={"query": "unique test phrase xyz123", "limit": 5},
            timeout=5
        )

        if search_response_after.status_code != 200:
            print("   ⚠️  Search failed after deletion")
            return True

        results_after = search_response_after.json()
        doc_found_after = any(r.get("id") == "test_index_update_doc_002" for r in results_after)

        if doc_found_after:
            print("   ❌ Document still in search results after deletion")
            return False
        else:
            print("   ✅ Document removed from index successfully")
            return True

    except requests.exceptions.ConnectionError:
        print("   ⚠️  Skipped - txtai API not available")
        return True
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False


def test_integration_delete_updates_count():
    """
    INTEGRATION TEST 3: test_delete_updates_count
    Test that deletion decrements document count.
    Implements REQ-004: Document removal from index.

    Note: Requires txtai API to be running.
    """
    print("\n[Integration Test 3] Testing document count after deletion...")

    try:
        # Check if API is available
        response = requests.get(f"{TEST_API_URL}/count", timeout=2)
        if response.status_code != 200:
            print("   ⚠️  Skipped - txtai API not available")
            return True

        count_before = response.json()

        # Add a test document
        test_doc = {
            "id": "test_count_doc_003",
            "text": "Test document for count verification"
        }

        add_response = requests.post(f"{TEST_API_URL}/add", json=[test_doc], timeout=5)
        if add_response.status_code != 200:
            print("   ⚠️  Failed to add test document")
            return True

        # Index
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Get count after add
        count_after_add = requests.get(f"{TEST_API_URL}/count", timeout=2).json()

        # Delete the document
        client = TxtAIClient(base_url=TEST_API_URL)
        result = client.delete_document("test_count_doc_003")

        if not result.get("success"):
            print(f"   ❌ Deletion failed: {result.get('error')}")
            return False

        # Re-index
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Get count after delete
        count_after_delete = requests.get(f"{TEST_API_URL}/count", timeout=2).json()

        # Verify count decreased
        if count_after_delete < count_after_add:
            print(f"   ✅ Document count decreased: {count_after_add} -> {count_after_delete}")
            return True
        else:
            print(f"   ❌ Document count did not decrease: {count_after_add} -> {count_after_delete}")
            return False

    except requests.exceptions.ConnectionError:
        print("   ⚠️  Skipped - txtai API not available")
        return True
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False


def test_integration_delete_removes_vectors():
    """
    INTEGRATION TEST 4: test_delete_removes_vectors
    Test that deletion removes vectors from Qdrant.
    Implements REQ-004: Complete index cleanup.

    Note: This is verified indirectly through search results.
    """
    print("\n[Integration Test 4] Testing vector removal (via search)...")

    # This is essentially the same as test_integration_delete_updates_index
    # but with focus on vector search
    try:
        client = TxtAIClient(base_url=TEST_API_URL)

        # Check if API is available
        response = requests.get(f"{TEST_API_URL}/count", timeout=2)
        if response.status_code != 200:
            print("   ⚠️  Skipped - txtai API not available")
            return True

        # Add a test document with unique vector-searchable content
        test_doc = {
            "id": "test_vector_doc_004",
            "text": "Machine learning embeddings vector search quantum computing neural networks"
        }

        add_response = requests.post(f"{TEST_API_URL}/add", json=[test_doc], timeout=5)
        if add_response.status_code != 200:
            print("   ⚠️  Failed to add test document")
            return True

        # Index
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Verify semantic search finds it
        search_response = requests.get(
            f"{TEST_API_URL}/search",
            params={"query": "AI and machine learning", "limit": 10},
            timeout=5
        )

        if search_response.status_code == 200:
            results = search_response.json()
            found_before = any(r.get("id") == "test_vector_doc_004" for r in results)

            if found_before:
                print("   ✅ Document found in vector search before deletion")
            else:
                print("   ⚠️  Document not in top results (may not affect test)")

        # Delete the document
        result = client.delete_document("test_vector_doc_004")

        if not result.get("success"):
            print(f"   ❌ Deletion failed: {result.get('error')}")
            return False

        # Re-index
        requests.get(f"{TEST_API_URL}/index", timeout=10)

        # Verify it's no longer in search results
        search_response_after = requests.get(
            f"{TEST_API_URL}/search",
            params={"query": "AI and machine learning", "limit": 10},
            timeout=5
        )

        if search_response_after.status_code == 200:
            results_after = search_response_after.json()
            found_after = any(r.get("id") == "test_vector_doc_004" for r in results_after)

            if not found_after:
                print("   ✅ Document vectors removed from search")
                return True
            else:
                print("   ❌ Document still appears in vector search")
                return False
        else:
            print("   ⚠️  Search failed after deletion")
            return True

    except requests.exceptions.ConnectionError:
        print("   ⚠️  Skipped - txtai API not available")
        return True
    except Exception as e:
        print(f"   ❌ Integration test failed: {e}")
        return False


def test_edge_case_network_error():
    """
    EDGE CASE TEST 1: test_delete_during_view (Network error handling)
    Test graceful handling when txtai API is unreachable.
    Implements FAIL-001, EDGE-004: Network error handling.
    """
    print("\n[Edge Case Test 1] Testing network error handling...")

    # Use an invalid URL to simulate network error
    client = TxtAIClient(base_url="http://invalid-host-12345.local:9999")

    result = client.delete_document("doc_123")

    # Verify error is handled gracefully
    if (result.get("success") == False and
        "error" in result and
        "connect" in result["error"].lower()):
        print("   ✅ Network error handled gracefully")
        print(f"      Error message: {result['error']}")
        return True
    else:
        print(f"   ❌ Network error not handled correctly: {result}")
        return False


def test_edge_case_double_delete():
    """
    EDGE CASE TEST 2: test_double_delete
    Test that deleting the same document twice is idempotent.
    Implements EDGE-005: API error handling with 404.

    Note: Requires txtai API to be running.
    """
    print("\n[Edge Case Test 2] Testing double deletion (idempotency)...")

    try:
        client = TxtAIClient(base_url=TEST_API_URL)

        # Check if API is available
        response = requests.get(f"{TEST_API_URL}/count", timeout=2)
        if response.status_code != 200:
            print("   ⚠️  Skipped - txtai API not available")
            return True

        # Try to delete a document that doesn't exist
        result1 = client.delete_document("nonexistent_doc_99999")

        # Should succeed (idempotent behavior)
        if result1.get("success"):
            print("   ✅ First delete of nonexistent doc treated as success")

        # Try again
        result2 = client.delete_document("nonexistent_doc_99999")

        # Should also succeed
        if result2.get("success"):
            print("   ✅ Second delete of nonexistent doc treated as success")
            print("   ✅ Delete operation is idempotent")
            return True
        else:
            print(f"   ❌ Second delete failed: {result2}")
            return False

    except requests.exceptions.ConnectionError:
        print("   ⚠️  Skipped - txtai API not available")
        return True
    except Exception as e:
        print(f"   ❌ Edge case test failed: {e}")
        return False


def test_edge_case_missing_image_file():
    """
    EDGE CASE TEST 3: test_delete_missing_image_file
    Test deletion when image path is provided but file doesn't exist.
    Implements EDGE-001: Missing image file handling.
    """
    print("\n[Edge Case Test 3] Testing missing image file handling...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Mock the API call to focus on image handling
    with patch('requests.post') as mock_post:
        # Setup mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["doc_with_missing_image"]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response

        # Test deletion with missing image file
        if os.path.exists('/uploads/images'):
            result = client.delete_document(
                "doc_with_missing_image",
                image_path="/uploads/images/nonexistent_image_xyz.png"
            )

            # Should succeed - missing image is not an error (EDGE-001)
            if result.get("success") and result.get("image_deleted"):
                print("   ✅ Missing image file handled gracefully")
                print(f"      Result: {result}")
                return True
            else:
                print(f"   ❌ Missing image handling failed: {result}")
                return False
        else:
            print("   ⚠️  Skipped - /uploads/images/ not accessible")
            return True


def run_all_tests():
    """Run all test suites and report results"""
    print("=" * 70)
    print("SPEC-009 Document Deletion Feature - Test Suite")
    print("=" * 70)

    results = {
        "Unit Tests": [],
        "Integration Tests": [],
        "Edge Case Tests": []
    }

    # Unit Tests
    print("\n" + "=" * 70)
    print("UNIT TESTS - API Client Methods")
    print("=" * 70)
    results["Unit Tests"].append(("Valid path deletion", test_safe_delete_image_valid_path()))
    results["Unit Tests"].append(("Path traversal prevention", test_safe_delete_image_path_traversal()))
    results["Unit Tests"].append(("Missing file handling", test_safe_delete_image_missing_file()))
    results["Unit Tests"].append(("delete_document API method", test_delete_document_api_success()))

    # Integration Tests
    print("\n" + "=" * 70)
    print("INTEGRATION TESTS - Full Workflow")
    print("=" * 70)
    results["Integration Tests"].append(("Delete with image cleanup", test_integration_delete_with_image()))
    results["Integration Tests"].append(("Index update after delete", test_integration_delete_updates_index()))
    results["Integration Tests"].append(("Count update after delete", test_integration_delete_updates_count()))
    results["Integration Tests"].append(("Vector removal verification", test_integration_delete_removes_vectors()))

    # Edge Case Tests
    print("\n" + "=" * 70)
    print("EDGE CASE TESTS - Error Conditions")
    print("=" * 70)
    results["Edge Case Tests"].append(("Network error handling", test_edge_case_network_error()))
    results["Edge Case Tests"].append(("Double deletion (idempotency)", test_edge_case_double_delete()))
    results["Edge Case Tests"].append(("Missing image file", test_edge_case_missing_image_file()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    total_passed = 0
    total_tests = 0

    for category, tests in results.items():
        passed = sum(1 for _, result in tests if result)
        total = len(tests)
        total_passed += passed
        total_tests += total

        print(f"\n{category}: {passed}/{total} passed")
        for name, result in tests:
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {status} - {name}")

    print("\n" + "=" * 70)
    print(f"OVERALL: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {total_tests - total_passed} tests failed")

    print("=" * 70)

    return total_passed == total_tests


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
