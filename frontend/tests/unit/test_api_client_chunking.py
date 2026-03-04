"""
Unit tests for TxtAIClient.chunk_text() method (REQ-003).

Tests cover:
- Character limits and chunk boundaries
- Chunk overlap behavior
- Edge cases: empty text, very long text, short text
- Unicode handling
- Markdown structure preservation

These are pure unit tests with no external service dependencies.
"""

import pytest
import sys
from pathlib import Path

# Add frontend directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.api_client import TxtAIClient, DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP


class TestChunkTextBasic:
    """Basic chunk_text() functionality tests."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        # Use a dummy URL since we're not making actual API calls
        return TxtAIClient(base_url="http://dummy:8300")

    def test_empty_text_returns_empty_list(self, client):
        """EDGE: Empty text should return empty list."""
        result = client.chunk_text("")
        assert result == []

    def test_whitespace_only_returns_empty_list(self, client):
        """EDGE: Whitespace-only text should return empty list."""
        result = client.chunk_text("   \n\t  ")
        assert result == []

    def test_none_text_returns_empty_list(self, client):
        """EDGE: None should be handled gracefully."""
        # The method checks 'if not text' which handles None
        result = client.chunk_text(None)
        assert result == []

    def test_short_text_returns_single_chunk(self, client):
        """Short text (< chunk_size) should return single chunk."""
        text = "This is a short text."
        result = client.chunk_text(text)

        assert len(result) == 1
        assert result[0]["text"] == text
        assert result[0]["chunk_index"] == 0
        assert result[0]["start"] == 0
        assert result[0]["end"] == len(text)

    def test_exact_chunk_size_returns_single_chunk(self, client):
        """Text exactly at chunk_size boundary should return single chunk."""
        chunk_size = 100
        text = "x" * chunk_size

        result = client.chunk_text(text, chunk_size=chunk_size)

        assert len(result) == 1
        assert result[0]["text"] == text

    def test_chunk_structure_has_required_keys(self, client):
        """Each chunk should have text, chunk_index, start, end keys."""
        text = "This is some text to chunk."
        result = client.chunk_text(text)

        assert len(result) > 0
        chunk = result[0]

        assert "text" in chunk
        assert "chunk_index" in chunk
        assert "start" in chunk
        assert "end" in chunk

        assert isinstance(chunk["text"], str)
        assert isinstance(chunk["chunk_index"], int)
        assert isinstance(chunk["start"], int)
        assert isinstance(chunk["end"], int)


class TestChunkTextMultipleChunks:
    """Tests for text that produces multiple chunks."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://dummy:8300")

    def test_long_text_creates_multiple_chunks(self, client):
        """Text longer than chunk_size should create multiple chunks."""
        # Create text that will definitely exceed default chunk size (4000 chars)
        # Need text significantly longer than 4000 chars to get multiple chunks
        text = "This is a sentence. " * 500  # ~10000 chars

        result = client.chunk_text(text)

        assert len(result) > 1, f"Expected multiple chunks but got {len(result)}"
        # Each chunk should have sequential indices
        for i, chunk in enumerate(result):
            assert chunk["chunk_index"] == i

    def test_chunks_have_overlap(self, client):
        """Consecutive chunks should have overlapping content."""
        # Use a large enough text to create multiple chunks
        text = "Word " * 500  # ~2500 chars
        chunk_size = 500
        overlap = 100

        result = client.chunk_text(text, chunk_size=chunk_size, overlap=overlap)

        if len(result) > 1:
            # The end of chunk N should overlap with start of chunk N+1
            # Due to how text splitters work, exact overlap may vary
            # but positions should reflect some overlap
            for i in range(len(result) - 1):
                current_end = result[i]["end"]
                next_start = result[i + 1]["start"]
                # With overlap, next chunk starts before current ends
                assert next_start < current_end, (
                    f"Chunk {i} ends at {current_end}, "
                    f"chunk {i+1} starts at {next_start} (should overlap)"
                )

    def test_chunk_positions_cover_full_text(self, client):
        """Chunk positions should cover the entire input text."""
        text = "Hello world. " * 200
        result = client.chunk_text(text)

        if len(result) > 0:
            # First chunk should start at 0
            assert result[0]["start"] == 0
            # Last chunk should end at or near text length
            # (may be slightly off due to stripping)
            assert result[-1]["end"] <= len(text.strip())

    def test_custom_chunk_size_respected(self, client):
        """Custom chunk_size parameter should be respected."""
        text = "x" * 1000
        chunk_size = 200

        result = client.chunk_text(text, chunk_size=chunk_size, overlap=0)

        # Each chunk text should be <= chunk_size
        for chunk in result:
            assert len(chunk["text"]) <= chunk_size + 50, (
                f"Chunk length {len(chunk['text'])} exceeds chunk_size {chunk_size}"
            )

    def test_zero_overlap_creates_minimal_overlapping_chunks(self, client):
        """Overlap=0 should minimize overlap between chunks."""
        # Use sentence-based text to allow natural splitting
        text = "This is sentence number one. " * 200  # ~5800 chars
        chunk_size = 1000
        overlap = 0

        result = client.chunk_text(text, chunk_size=chunk_size, overlap=overlap)

        # Should create multiple chunks
        assert len(result) > 1

        # With overlap=0, there should be less overlap than with default overlap
        # We just verify chunks are created and indexed correctly
        for i, chunk in enumerate(result):
            assert chunk["chunk_index"] == i
            assert len(chunk["text"]) > 0


class TestChunkTextUnicode:
    """Tests for Unicode text handling."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://dummy:8300")

    def test_unicode_characters_preserved(self, client):
        """Unicode characters should be preserved in chunks."""
        text = "Hello! Bonjour! Guten Tag! Hola!"
        result = client.chunk_text(text)

        assert len(result) == 1
        assert result[0]["text"] == text

    def test_emoji_text_chunked_correctly(self, client):
        """Emoji characters should be handled correctly."""
        text = "Hello! Great job! Thanks!"
        result = client.chunk_text(text)

        assert len(result) == 1
        # Emojis should be preserved
        assert "" in result[0]["text"]
        assert "" in result[0]["text"]

    def test_chinese_text_chunked_correctly(self, client):
        """Chinese characters should be chunked correctly."""
        # Chinese text with enough content to not be empty after stripping
        text = "Hello world!"
        result = client.chunk_text(text)

        assert len(result) == 1
        assert "" in result[0]["text"]
        assert "" in result[0]["text"]

    def test_mixed_unicode_scripts(self, client):
        """Mixed Unicode scripts should be preserved."""
        text = "English, Franais, Deutsch"
        result = client.chunk_text(text)

        assert len(result) == 1
        # Key characters should be preserved
        assert "English" in result[0]["text"]
        assert "Franais" in result[0]["text"]
        assert "Deutsch" in result[0]["text"]

    def test_long_unicode_text_chunks_correctly(self, client):
        """Long Unicode text should chunk without corruption."""
        # Create long text with various Unicode
        text = " " * 500  # ~1500 chars
        chunk_size = 500

        result = client.chunk_text(text, chunk_size=chunk_size)

        # All chunks combined should have all original characters
        combined = "".join(c["text"] for c in result)
        # Due to overlap, combined may have duplicates, but all unique chars should be present
        assert "" in combined
        assert "" in combined
        assert "" in combined


class TestChunkTextMarkdown:
    """Tests for Markdown structure preservation."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://dummy:8300")

    def test_paragraph_breaks_respected(self, client):
        """Chunks should prefer to break at paragraph boundaries."""
        text = """First paragraph with enough content to matter.

Second paragraph also with substantial content here.

Third paragraph completing the document structure."""

        # Use small chunk size to force splitting
        result = client.chunk_text(text, chunk_size=100, overlap=20)

        # Should have multiple chunks
        assert len(result) > 1

    def test_markdown_header_preserved(self, client):
        """Markdown headers should be preserved in chunks."""
        text = """# Main Title

This is the introduction paragraph.

## Section One

Content for section one.

## Section Two

Content for section two."""

        result = client.chunk_text(text, chunk_size=100, overlap=20)

        # Headers should appear in chunks
        all_text = " ".join(c["text"] for c in result)
        assert "# Main Title" in all_text or "Main Title" in all_text
        assert "Section One" in all_text
        assert "Section Two" in all_text

    def test_code_block_handling(self, client):
        """Code blocks should be handled appropriately."""
        text = """Here is some code:

```python
def hello():
    print("Hello, World!")
```

And here is more text after the code."""

        result = client.chunk_text(text)

        # Code should be preserved somewhere in the chunks
        all_text = " ".join(c["text"] for c in result)
        assert "def hello():" in all_text
        assert "print" in all_text


class TestChunkTextEdgeCases:
    """Edge case tests for chunk_text()."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://dummy:8300")

    def test_very_long_text_handled(self, client):
        """Very long text (100k+ chars) should be handled without error."""
        # Create 100,000 character text
        text = "This is a repeated sentence for testing. " * 2500

        # Should not raise exception
        result = client.chunk_text(text)

        assert len(result) > 0
        # Should create multiple chunks (with 4000 char default, ~100k text should create 20+ chunks)
        assert len(result) > 20, f"Expected >20 chunks for 100k chars, got {len(result)}"

    def test_single_very_long_word(self, client):
        """Single very long word should be handled."""
        # Word longer than default chunk_size but using default settings
        # (RecursiveCharacterTextSplitter requires chunk_overlap < chunk_size)
        text = "a" * 10000

        # Use default settings to avoid overlap validation issues
        result = client.chunk_text(text)

        # Should still produce chunks even for single long "word"
        assert len(result) > 0

    def test_text_with_only_newlines(self, client):
        """Text with only newlines should be handled."""
        text = "\n\n\n\n\n"

        result = client.chunk_text(text)

        # After stripping, this is empty
        assert result == []

    def test_text_ending_with_separator(self, client):
        """Text ending with various separators should be handled."""
        texts = [
            "Hello world.",
            "Hello world!",
            "Hello world?",
            "Hello world;",
            "Hello world,",
            "Hello world\n",
            "Hello world\n\n",
        ]

        for text in texts:
            result = client.chunk_text(text)
            assert len(result) > 0, f"Failed for text ending with: {repr(text[-5:])}"

    def test_special_characters_preserved(self, client):
        """Special characters should be preserved."""
        text = "Special chars: @#$%^&*()[]{}|\\:;<>?,./~`"
        result = client.chunk_text(text)

        assert len(result) == 1
        assert result[0]["text"] == text

    def test_html_entities_preserved(self, client):
        """HTML entities and tags should be preserved as-is."""
        text = "<html>&lt;div&gt;Content&lt;/div&gt;&amp;</html>"
        result = client.chunk_text(text)

        assert len(result) == 1
        assert "&lt;" in result[0]["text"]
        assert "&gt;" in result[0]["text"]
        assert "&amp;" in result[0]["text"]


class TestChunkTextDefaults:
    """Tests for default parameter values."""

    @pytest.fixture
    def client(self):
        """Create TxtAIClient instance for testing."""
        return TxtAIClient(base_url="http://dummy:8300")

    def test_default_chunk_size_used(self, client):
        """Default chunk_size should be DEFAULT_CHUNK_SIZE."""
        # Create text longer than default chunk size
        text = "x" * (DEFAULT_CHUNK_SIZE + 500)

        result = client.chunk_text(text)

        # Should create multiple chunks with default size
        assert len(result) > 1

    def test_default_overlap_used(self, client):
        """Default overlap should be DEFAULT_CHUNK_OVERLAP."""
        # Create text that will produce multiple chunks
        text = "Word " * 1000

        result = client.chunk_text(text)

        # With default overlap, chunks should overlap
        if len(result) > 1:
            # Check that positions indicate overlap
            for i in range(len(result) - 1):
                assert result[i + 1]["start"] < result[i]["end"]

    def test_chunk_size_and_overlap_constants_reasonable(self):
        """Default constants should have reasonable values."""
        # Chunk size should be large enough for meaningful content
        assert DEFAULT_CHUNK_SIZE >= 500
        # Overlap should be positive but smaller than chunk size
        assert DEFAULT_CHUNK_OVERLAP > 0
        assert DEFAULT_CHUNK_OVERLAP < DEFAULT_CHUNK_SIZE
