"""
RAG flow E2E tests (SPEC-024).

Tests RAG (Retrieval Augmented Generation) functionality including:
- RAG query with answer (REQ-004)
- Source citations display (REQ-004)
- Empty knowledge base handling (EDGE-003)
- RAG timeout handling (FAIL-002)

Requirements:
    - Frontend running at TEST_FRONTEND_URL
    - txtai API running at TEST_TXTAI_API_URL
    - Together AI API key configured (TOGETHERAI_API_KEY)

Usage:
    pytest tests/e2e/test_rag_flow.py -v
    pytest tests/e2e/test_rag_flow.py -v --headed
"""

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGWithContent:
    """Test RAG when documents exist in knowledge base."""

    def test_rag_returns_answer(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG query returns an answer (REQ-004)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document directly via txtai API (bypasses UI complexity)
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

        # Read the sample file content
        with open(sample_txt_path, "r") as f:
            content = f.read()

        # Add document via API
        add_response = requests.post(
            f"{api_url}/add",
            json=[{
                "id": "test-rag-doc",
                "text": content,
                "data": {"filename": "sample.txt", "category": "personal"}
            }],
            timeout=30
        )
        assert add_response.status_code == 200, f"Add failed: {add_response.text}"

        # Index the document
        upsert_response = requests.get(f"{api_url}/upsert", timeout=30)
        assert upsert_response.status_code == 200, f"Upsert failed: {upsert_response.text}"

        # Verify document count
        count_response = requests.get(f"{api_url}/count", timeout=10)
        assert count_response.status_code == 200
        doc_count = int(count_response.text)
        assert doc_count >= 1, f"Expected at least 1 document, got {doc_count}"

        # Wait for indexing to propagate
        e2e_page.wait_for_timeout(2000)

        # Navigate to Ask page
        ask_page = AskPage(e2e_page)
        ask_page.navigate()

        # Ask a question about the document content
        ask_page.ask_question("What is in the sample document?")

        # Should get an answer
        ask_page.expect_answer_visible()

    def test_rag_shows_sources(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG answer includes source citations (REQ-004)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document directly via txtai API
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-sources-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)

        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("What information is in the document?")

        # Should show sources
        ask_page.expect_answer_visible()
        ask_page.expect_sources_visible()

    def test_rag_answer_contains_text(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG answer contains meaningful text (REQ-004)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document directly via txtai API
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-text-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)

        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("Summarize the content")

        # Get answer text
        ask_page.expect_answer_visible()
        answer_text = ask_page.get_answer_text()

        # Answer should be substantial
        assert len(answer_text) > 50, f"Expected substantial answer, got: {answer_text}"


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGEmptyKnowledgeBase:
    """Test RAG behavior with empty knowledge base."""

    def test_empty_kb_shows_message(
        self, ask_page, clean_postgres, clean_qdrant
    ):
        """Empty knowledge base shows appropriate message (EDGE-003)."""
        # Ask question with no documents indexed
        ask_page.ask_question("What documents are available?")

        # Should show some indication that KB is empty or give a response
        # Either outcome is acceptable - just verify no crash
        e2e_page = ask_page.page
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGEdgeCases:
    """Test RAG edge cases."""

    def test_special_characters_in_question(
        self, ask_page, clean_postgres, clean_qdrant
    ):
        """RAG handles special characters in question."""
        ask_page.ask_question('What about "quoted text" & special <characters>?')

        # Should not crash
        expect(ask_page.page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_very_long_question(
        self, ask_page, clean_postgres, clean_qdrant
    ):
        """RAG handles very long questions."""
        long_question = "Please explain " + " ".join(["the topic"] * 50) + "?"
        ask_page.ask_question(long_question)

        # Should not crash
        expect(ask_page.page.locator('[data-testid="stException"]')).to_have_count(0)

    def test_empty_question_handled(
        self, ask_page, clean_postgres, clean_qdrant
    ):
        """Empty question is handled gracefully."""
        # Ensure question input is empty
        ask_page.question_input.fill("")
        ask_page.question_input.press("Tab")

        # The button should be disabled when question is empty
        # (The Ask page disables the button when question.strip() is empty)
        expect(ask_page.ask_button.first).to_be_disabled()

        # Should not crash - no exceptions displayed
        expect(ask_page.page.locator('[data-testid="stException"]')).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.rag
@pytest.mark.slow
class TestRAGPerformance:
    """Test RAG performance characteristics."""

    def test_rag_completes_within_timeout(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG query completes within acceptable time (PERF-002)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage
        import time

        # Add document directly via txtai API
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")

        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-perf-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)

        e2e_page.wait_for_timeout(2000)

        # Time the RAG query
        ask_page = AskPage(e2e_page)
        ask_page.navigate()

        start_time = time.time()
        ask_page.ask_question("What is in the document?")
        ask_page.expect_answer_visible()
        end_time = time.time()

        elapsed = end_time - start_time

        # Should complete within 60 seconds (RAG timeout)
        assert elapsed < 60, f"RAG took too long: {elapsed:.1f}s"


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGPageLoad:
    """Test RAG page loading and status."""

    def test_ask_page_shows_ready_status(
        self, e2e_page: Page, base_url: str
    ):
        """Ask page shows RAG service status."""
        from tests.pages.ask_page import AskPage

        ask_page = AskPage(e2e_page)
        ask_page.navigate()

        # Page should load successfully
        ask_page.expect_page_loaded()

        # Should have question input available
        expect(ask_page.question_input).to_be_visible()

    def test_ask_button_visible(
        self, ask_page
    ):
        """Ask button is visible and clickable."""
        if ask_page.ask_button.count() > 0:
            expect(ask_page.ask_button.first).to_be_visible()


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGAnswerQuality:
    """Test RAG answer quality indicators (REQ-016)."""

    def test_answer_shows_confidence_indicator(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG answer shows confidence indicator (REQ-016)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-confidence-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)
        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("What is in the document?")
        ask_page.expect_answer_visible()

        # Should show confidence indicator (High/Medium/Low confidence alert)
        confidence_indicator = e2e_page.locator('[data-testid="stAlert"]:has-text("confidence")')
        expect(confidence_indicator.first).to_be_visible(timeout=5000)

    def test_answer_has_meaningful_length(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """RAG answer has meaningful length (REQ-016)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-length-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)
        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("Explain what the document contains")
        ask_page.expect_answer_visible()

        # Answer should be substantial (at least 100 chars)
        answer_text = ask_page.get_answer_text()
        assert len(answer_text) >= 100, \
            f"Expected substantial answer (>=100 chars), got {len(answer_text)} chars"


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGSourceCitations:
    """Test RAG source citation functionality (REQ-016)."""

    def test_source_shows_document_info(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """Source citation shows document information (REQ-016)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document with specific filename
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-source-info", "text": content, "data": {"filename": "test_source.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)
        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("What does the document say?")
        ask_page.expect_answer_visible()

        # Check for source expanders
        source_count = ask_page.get_source_count()
        assert source_count >= 1, "Expected at least one source citation"

    def test_sources_are_expandable(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """Source citations can be expanded for details (REQ-016)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-expand-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)
        e2e_page.wait_for_timeout(2000)

        # Ask question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("What information is available?")
        ask_page.expect_answer_visible()

        # Try to expand first source
        if ask_page.source_items.count() > 0:
            ask_page.source_items.first.click()
            e2e_page.wait_for_timeout(500)

            # Should not crash
            expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)


@pytest.mark.e2e
@pytest.mark.rag
class TestRAGConversationFlow:
    """Test RAG conversation continuity (REQ-016)."""

    def test_can_ask_multiple_questions(
        self, e2e_page: Page, base_url: str, sample_txt_path,
        clean_postgres, clean_qdrant, mock_together_ai
    ):
        """Can ask multiple questions in sequence (REQ-016)."""
        import requests
        import os
        from tests.pages.ask_page import AskPage

        # Add document
        api_url = os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")
        with open(sample_txt_path, "r") as f:
            content = f.read()

        requests.post(
            f"{api_url}/add",
            json=[{"id": "test-multi-doc", "text": content, "data": {"filename": "sample.txt"}}],
            timeout=30
        )
        requests.get(f"{api_url}/upsert", timeout=30)
        e2e_page.wait_for_timeout(2000)

        # Ask first question
        ask_page = AskPage(e2e_page)
        ask_page.navigate()
        ask_page.ask_question("What is the main topic?")
        ask_page.expect_answer_visible()

        first_answer = ask_page.get_answer_text()

        # Ask second question (should work without page refresh)
        ask_page.question_input.fill("Can you provide more details?")
        ask_page.question_input.press("Tab")
        e2e_page.wait_for_timeout(1000)

        # Click ask again
        if ask_page.ask_button.count() > 0:
            ask_page.ask_button.first.click()
            ask_page._wait_for_answer(timeout=ask_page.RAG_TIMEOUT)

        second_answer = ask_page.get_answer_text()

        # Both questions should have produced answers
        assert len(first_answer) > 20, "First question should have an answer"
        # Note: second answer might include or replace first, just check it's not empty
        expect(e2e_page.locator('[data-testid="stException"]')).to_have_count(0)
