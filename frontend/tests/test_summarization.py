#!/usr/bin/env python
"""
Unit and integration tests for document summarization feature (RESEARCH-018).

Tests cover:
- Unit tests: API client summarize_text_llm method (6 tests)
- SPEC-017 tests: Universal summarization methods (8 tests)
- Edge case tests: Boundary conditions and special scenarios (6 tests)

Run this file to execute all tests:
    python test_summarization.py
"""

import sys
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import requests

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.api_client import TxtAIClient

# Test configuration
TEST_API_URL = "http://localhost:8300"


# =============================================================================
# UNIT TESTS (6 tests for summarize_text_llm method)
# =============================================================================

def test_summarize_text_llm_success():
    """
    TEST-001: test_summarize_text_llm_success()
    Verify successful API call with valid text.
    Tests: RESEARCH-018 LLM summarization
    """
    print("\n[Unit Test 1] Testing successful LLM summarization...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Mock successful API response
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["This is a test summary of the provided text."]
        mock_post.return_value = mock_response

        test_text = "This is a document about machine learning. " * 20
        result = client.summarize_text_llm(test_text)

        # Assertions
        assert result['success'] == True, "Expected success=True"
        assert 'summary' in result, "Expected 'summary' in result"
        assert result['summary'] == "This is a test summary of the provided text."
        assert 'error' not in result or result.get('error') is None

        # Verify API was called correctly with llm-summary workflow
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]['json']['name'] == 'llm-summary'
        assert call_args[1]['timeout'] == 30

    print("✅ TEST-001 PASSED: Successful LLM summarization")


def test_summarize_text_llm_timeout():
    """
    TEST-002: test_summarize_text_llm_timeout()
    Mock timeout exception, verify error handling.
    Tests: RESEARCH-018 error handling
    """
    print("\n[Unit Test 2] Testing timeout handling...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Mock timeout exception
    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.Timeout()

        test_text = "A" * 100
        result = client.summarize_text_llm(test_text, timeout=30)

        # Assertions
        assert result['success'] == False, "Expected success=False on timeout"
        assert result['error'] == 'timeout', "Expected error='timeout'"
        assert 'summary' not in result

    print("✅ TEST-002 PASSED: Timeout handled gracefully")


def test_summarize_text_llm_empty_input():
    """
    TEST-003: test_summarize_text_llm_empty_input()
    Verify empty string returns error.
    Tests: RESEARCH-018 input validation
    """
    print("\n[Unit Test 3] Testing empty input handling...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Test with empty string
    result = client.summarize_text_llm("")

    # Assertions
    assert result['success'] == False, "Expected success=False for empty input"
    assert 'Empty text' in result['error'], "Expected 'Empty text' error"

    print("✅ TEST-003 PASSED: Empty input rejected")


def test_summarize_text_llm_short_input_works():
    """
    TEST-004: test_summarize_text_llm_short_input_works()
    Verify short text works (unlike BART, LLM has no minimum).
    Tests: RESEARCH-018 - no minimum length requirement
    """
    print("\n[Unit Test 4] Testing short text handling (should work)...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["Summary of short text."]
        mock_post.return_value = mock_response

        # Test with short text - LLM should handle it fine
        test_text = "Short text about Python."
        result = client.summarize_text_llm(test_text)

        # Assertions - should succeed (no minimum length for LLM)
        assert result['success'] == True, "Expected success=True for short text"
        assert 'summary' in result

    print("✅ TEST-004 PASSED: Short text handled (no minimum length)")


def test_summarize_text_llm_connection_error():
    """
    TEST-005: test_summarize_text_llm_connection_error()
    Mock connection error, verify graceful handling.
    Tests: RESEARCH-018 error handling
    """
    print("\n[Unit Test 5] Testing connection error...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_post.side_effect = requests.exceptions.ConnectionError()

        test_text = "A" * 100
        result = client.summarize_text_llm(test_text)

        # Assertions
        assert result['success'] == False, "Expected success=False on connection error"
        assert 'unavailable' in result['error'].lower()

    print("✅ TEST-005 PASSED: Connection error handled")


def test_summarize_text_llm_invalid_response():
    """
    TEST-006: test_summarize_text_llm_invalid_response()
    Mock empty response, verify handling.
    Tests: RESEARCH-018 error handling
    """
    print("\n[Unit Test 6] Testing invalid/empty response...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Mock empty response from API
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty list
        mock_post.return_value = mock_response

        test_text = "A" * 100
        result = client.summarize_text_llm(test_text)

        # Assertions
        assert result['success'] == False, "Expected success=False for empty response"
        assert 'empty summary' in result['error'].lower(), "Expected 'empty summary' error"

    print("✅ TEST-006 PASSED: Invalid response handled")


# =============================================================================
# EDGE CASE TESTS (6 edge case scenarios)
# =============================================================================

def test_edge_very_long_document():
    """
    EDGE-TEST-001: Very long document (20,000 chars)
    Should truncate to 10,000 characters.
    Tests: RESEARCH-018 truncation
    """
    print("\n[Edge Test 1] Testing very long document truncation...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["Summary of truncated text."]
        mock_post.return_value = mock_response

        # Create 20,000 character text
        test_text = "A" * 20000
        result = client.summarize_text_llm(test_text)

        # Verify truncation happened
        call_args = mock_post.call_args
        sent_text = call_args[1]['json']['elements'][0]
        assert len(sent_text) == 10000, f"Expected truncation to 10K, got {len(sent_text)}"
        assert result['success'] == True

    print("✅ EDGE-TEST-001 PASSED: Long document truncated to 10K")


def test_edge_code_file():
    """
    EDGE-TEST-002: Code file content (Python source)
    Should attempt summarization.
    Tests: RESEARCH-018 code handling
    """
    print("\n[Edge Test 2] Testing code file summarization...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["This code defines a function that processes data."]
        mock_post.return_value = mock_response

        test_code = """
def process_data(input_list):
    \"\"\"Process input data and return results.\"\"\"
    results = []
    for item in input_list:
        if item > 0:
            results.append(item * 2)
    return results
        """

        result = client.summarize_text_llm(test_code)
        assert result['success'] == True

    print("✅ EDGE-TEST-002 PASSED: Code file summarized")


def test_edge_structured_data():
    """
    EDGE-TEST-003: Structured data (JSON file)
    Should skip summarization.
    Tests: RESEARCH-018 structured data detection
    """
    print("\n[Edge Test 3] Testing structured data detection...")

    client = TxtAIClient(base_url=TEST_API_URL)

    test_json = '{"key": "value", "data": [1, 2, 3]}' * 50
    result = client.summarize_text_llm(test_json)

    assert result['success'] == False
    assert 'Structured data detected' in result['error']

    print("✅ EDGE-TEST-003 PASSED: Structured data skipped")


def test_edge_whitespace_only():
    """
    EDGE-TEST-004: Whitespace-only text
    Should return error.
    Tests: RESEARCH-018 input validation
    """
    print("\n[Edge Test 4] Testing whitespace-only text...")

    client = TxtAIClient(base_url=TEST_API_URL)

    test_whitespace = "   \n\n\t\t   " * 100
    result = client.summarize_text_llm(test_whitespace)

    assert result['success'] == False
    assert 'Empty text' in result['error']

    print("✅ EDGE-TEST-004 PASSED: Whitespace-only text rejected")


def test_edge_special_characters():
    """
    EDGE-TEST-005: Text with special characters/emojis
    Should handle gracefully.
    Tests: RESEARCH-018 input sanitization
    """
    print("\n[Edge Test 5] Testing special characters...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["Summary of text with special chars."]
        mock_post.return_value = mock_response

        test_text = "Hello 🌟 World! Special chars: @#$%^&*() " * 10
        result = client.summarize_text_llm(test_text)

        assert result['success'] == True

    print("✅ EDGE-TEST-005 PASSED: Special characters handled")


def test_edge_http_error():
    """
    EDGE-TEST-006: HTTP error from API
    Should handle gracefully.
    Tests: RESEARCH-018 error handling
    """
    print("\n[Edge Test 6] Testing HTTP error...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        test_text = "A" * 100
        result = client.summarize_text_llm(test_text)

        assert result['success'] == False
        assert 'HTTP error' in result['error']

    print("✅ EDGE-TEST-006 PASSED: HTTP error handled")


# =============================================================================
# SPEC-017 / RESEARCH-018 TESTS: Universal Summarization
# =============================================================================

def test_generate_brief_explanation_success():
    """
    SPEC-017-TEST-001: Brief explanation for short content
    Verify Together AI is called for fallback.
    Tests: SPEC-017 REQ-005
    """
    print("\n[SPEC-017 Test 1] Testing brief explanation generation...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch.dict(os.environ, {'TOGETHERAI_API_KEY': 'test-key', 'RAG_LLM_MODEL': 'test-model'}):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{"text": "This is a brief explanation of the short content."}]
            }
            mock_post.return_value = mock_response

            test_text = "A short note about something important."
            result = client.generate_brief_explanation(test_text)

            assert result['success'] == True, "Expected success=True"
            assert 'summary' in result, "Expected 'summary' in result"
            assert 'brief explanation' in result['summary'].lower()

            # Verify Together AI API was called
            call_args = mock_post.call_args
            assert 'together.xyz' in call_args[0][0]

    print("✅ SPEC-017-TEST-001 PASSED: Brief explanation generated")


def test_generate_brief_explanation_missing_api_key():
    """
    SPEC-017-TEST-002: Missing Together AI API key
    Tests: SPEC-017 FAIL-002
    """
    print("\n[SPEC-017 Test 2] Testing missing API key...")

    client = TxtAIClient(base_url=TEST_API_URL)

    # Clear the API key
    with patch.dict(os.environ, {'TOGETHERAI_API_KEY': ''}, clear=True):
        result = client.generate_brief_explanation("Short text")

        assert result['success'] == False
        assert 'missing_api_key' in result['error']

    print("✅ SPEC-017-TEST-002 PASSED: Missing API key handled")


def test_generate_summary_uses_llm():
    """
    RESEARCH-018-TEST-001: generate_summary uses LLM as primary
    Tests: RESEARCH-018 - LLM is primary summarization method
    """
    print("\n[RESEARCH-018 Test 1] Testing summary uses LLM...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["LLM summary of the text."]
        mock_post.return_value = mock_response

        test_text = "A" * 600  # Any length should use LLM
        result = client.generate_summary(test_text)

        assert result['success'] == True
        assert result.get('model') == 'llm-qwen', f"Expected model='llm-qwen', got {result.get('model')}"

        # Verify llm-summary workflow was called
        call_args = mock_post.call_args
        assert call_args[1]['json']['name'] == 'llm-summary'

    print("✅ RESEARCH-018-TEST-001 PASSED: LLM used as primary")


def test_generate_summary_short_text_uses_llm():
    """
    RESEARCH-018-TEST-002: generate_summary uses LLM even for short text
    Tests: RESEARCH-018 - no minimum length requirement
    """
    print("\n[RESEARCH-018 Test 2] Testing short text uses LLM...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["LLM summary of short content."]
        mock_post.return_value = mock_response

        test_text = "Short text under 500 chars."  # < 500 chars
        result = client.generate_summary(test_text)

        assert result['success'] == True
        assert result.get('model') == 'llm-qwen', f"Expected model='llm-qwen', got {result.get('model')}"

    print("✅ RESEARCH-018-TEST-002 PASSED: Short text uses LLM")


def test_generate_summary_fallback_to_direct_api():
    """
    RESEARCH-018-TEST-003: generate_summary falls back to direct Together AI
    Tests: RESEARCH-018 - fallback when txtai unavailable
    """
    print("\n[RESEARCH-018 Test 3] Testing fallback to direct API...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch.dict(os.environ, {'TOGETHERAI_API_KEY': 'test-key'}):
        with patch('requests.post') as mock_post:
            # First call (LLM) fails, second call (direct API) succeeds
            mock_post.side_effect = [
                requests.exceptions.ConnectionError(),  # LLM fails
                Mock(status_code=200, json=lambda: {"choices": [{"text": "Fallback summary."}]})  # Direct API succeeds
            ]

            test_text = "Some text to summarize."
            result = client.generate_summary(test_text)

            assert result['success'] == True
            assert result.get('model') == 'together-ai-direct'

    print("✅ RESEARCH-018-TEST-003 PASSED: Fallback to direct API works")


def test_generate_image_summary_with_ocr():
    """
    SPEC-017-TEST-005: Image summary with significant OCR
    Tests: SPEC-017 REQ-006
    """
    print("\n[SPEC-017 Test 5] Testing image summary with OCR...")

    client = TxtAIClient(base_url=TEST_API_URL)

    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = ["Summary of the OCR text content."]
        mock_post.return_value = mock_response

        # OCR text > 50 chars
        caption = "A screenshot of a document"
        ocr_text = "This is extracted OCR text from a screenshot with more than fifty characters."

        result = client.generate_image_summary(caption, ocr_text)

        assert result['success'] == True
        # Should summarize OCR using LLM
        assert result.get('model') == 'llm-qwen'

    print("✅ SPEC-017-TEST-005 PASSED: Image OCR summarized with LLM")


def test_generate_image_summary_caption_only():
    """
    SPEC-017-TEST-006: Image summary with no significant OCR
    Tests: SPEC-017 REQ-007
    """
    print("\n[SPEC-017 Test 6] Testing image summary with caption only...")

    client = TxtAIClient(base_url=TEST_API_URL)

    caption = "A beautiful sunset over the ocean"
    ocr_text = ""  # No OCR

    result = client.generate_image_summary(caption, ocr_text)

    assert result['success'] == True
    assert result['summary'] == caption, "Caption should be used as summary"
    assert result.get('model') == 'caption'

    print("✅ SPEC-017-TEST-006 PASSED: Caption used as summary")


def test_generate_image_summary_short_ocr_uses_caption():
    """
    SPEC-017-TEST-007: Image with short OCR (<= 50 chars) uses caption
    Tests: SPEC-017 REQ-007
    """
    print("\n[SPEC-017 Test 7] Testing short OCR fallback to caption...")

    client = TxtAIClient(base_url=TEST_API_URL)

    caption = "A photo of a whiteboard"
    ocr_text = "Brief text"  # <= 50 chars

    result = client.generate_image_summary(caption, ocr_text)

    assert result['success'] == True
    assert result['summary'] == caption, "Caption should be used for short OCR"
    assert result.get('model') == 'caption'

    print("✅ SPEC-017-TEST-007 PASSED: Short OCR uses caption")


def test_generate_image_summary_no_content():
    """
    SPEC-017-TEST-008: Image with no caption or OCR
    Tests: SPEC-017 error handling
    """
    print("\n[SPEC-017 Test 8] Testing image with no content...")

    client = TxtAIClient(base_url=TEST_API_URL)

    result = client.generate_image_summary("", "")

    assert result['success'] == False
    assert 'No caption or OCR' in result.get('error', '')

    print("✅ SPEC-017-TEST-008 PASSED: No content handled")


# =============================================================================
# TEST RUNNER
# =============================================================================

def run_all_tests():
    """Run all tests and report results."""
    print("=" * 80)
    print("DOCUMENT SUMMARIZATION TEST SUITE (RESEARCH-018)")
    print("=" * 80)

    test_functions = [
        # Unit tests (LLM summarization)
        test_summarize_text_llm_success,
        test_summarize_text_llm_timeout,
        test_summarize_text_llm_empty_input,
        test_summarize_text_llm_short_input_works,
        test_summarize_text_llm_connection_error,
        test_summarize_text_llm_invalid_response,
        # Edge case tests
        test_edge_very_long_document,
        test_edge_code_file,
        test_edge_structured_data,
        test_edge_whitespace_only,
        test_edge_special_characters,
        test_edge_http_error,
        # SPEC-017 / RESEARCH-018 tests
        test_generate_brief_explanation_success,
        test_generate_brief_explanation_missing_api_key,
        test_generate_summary_uses_llm,
        test_generate_summary_short_text_uses_llm,
        test_generate_summary_fallback_to_direct_api,
        test_generate_image_summary_with_ocr,
        test_generate_image_summary_caption_only,
        test_generate_image_summary_short_ocr_uses_caption,
        test_generate_image_summary_no_content,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_func in test_functions:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test_func.__name__, str(e)))
            print(f"❌ {test_func.__name__} FAILED: {e}")
        except Exception as e:
            failed += 1
            errors.append((test_func.__name__, f"ERROR: {str(e)}"))
            print(f"💥 {test_func.__name__} ERROR: {e}")

    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(test_functions)}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if errors:
        print("\nFailed tests:")
        for test_name, error in errors:
            print(f"  - {test_name}: {error}")

    print("=" * 80)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
