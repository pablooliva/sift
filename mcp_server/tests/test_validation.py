"""
Input validation tests for MCP server.
SPEC-015: Claude Code + txtai MCP Integration

Tests SEC-002 requirements:
- Question length validation (max 1000 chars)
- Character sanitization (non-printable chars)
- Empty input handling
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from txtai_rag_mcp import validate_question, remove_nonprintable


class TestRemoveNonprintable:
    """Tests for remove_nonprintable function."""

    def test_normal_text_unchanged(self):
        """Normal text should pass through unchanged."""
        text = "What is Python programming?"
        assert remove_nonprintable(text) == text

    def test_preserves_newlines(self):
        """Newlines should be preserved."""
        text = "Line 1\nLine 2\nLine 3"
        assert remove_nonprintable(text) == text

    def test_preserves_tabs(self):
        """Tabs should be preserved."""
        text = "Column1\tColumn2\tColumn3"
        assert remove_nonprintable(text) == text

    def test_removes_null_bytes(self):
        """Null bytes should be removed."""
        text = "Hello\x00World"
        assert remove_nonprintable(text) == "HelloWorld"

    def test_removes_control_characters(self):
        """Control characters (except newline/tab) should be removed."""
        text = "Hello\x01\x02\x03World"
        assert remove_nonprintable(text) == "HelloWorld"

    def test_empty_string(self):
        """Empty string should return empty."""
        assert remove_nonprintable("") == ""

    def test_unicode_preserved(self):
        """Unicode characters should be preserved."""
        text = "Hello, mundo! Bonjour, 世界!"
        assert remove_nonprintable(text) == text


class TestValidateQuestion:
    """Tests for validate_question function."""

    def test_valid_question(self):
        """Valid question should pass validation."""
        question = "What are the main features of txtai?"
        assert validate_question(question) == question

    def test_strips_whitespace(self):
        """Leading/trailing whitespace should be stripped."""
        question = "  What is txtai?  "
        assert validate_question(question) == "What is txtai?"

    def test_empty_question_raises_error(self):
        """Empty question should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_question("")

    def test_whitespace_only_raises_error(self):
        """Whitespace-only question should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_question("   \n\t   ")

    def test_truncates_long_question(self):
        """Questions over 1000 chars should be truncated."""
        long_question = "x" * 1500
        result = validate_question(long_question)
        assert len(result) == 1000
        assert result == "x" * 1000

    def test_exactly_1000_chars_not_truncated(self):
        """Questions exactly 1000 chars should not be truncated."""
        question = "x" * 1000
        assert validate_question(question) == question

    def test_sanitizes_non_printable(self):
        """Non-printable characters should be removed."""
        question = "What\x00is\x01txtai?"
        assert validate_question(question) == "Whatistxtai?"

    def test_preserves_valid_formatting(self):
        """Valid formatting (newlines, tabs) should be preserved."""
        question = "Question:\n- Part 1\n- Part 2"
        result = validate_question(question)
        assert "\n" in result
        assert "- Part 1" in result
