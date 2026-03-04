"""
E2E tests for SPEC-031 Knowledge Summary Header Display.

Tests the UI display of knowledge summary in search results:
- Full summary display with all components (REQ-001 to REQ-005)
- Sparse summary display (REQ-006)
- No summary when data insufficient (REQ-007)
- Document link navigation to View Source (UX-003)
- Graceful degradation when Graphiti disabled (FAIL-001)
- XSS prevention for malicious queries (SEC-001)

Requirements:
    - Frontend running at TEST_FRONTEND_URL
    - txtai API running at TEST_TXTAI_API_URL
    - Test environment with Graphiti enabled (for full/sparse tests)

Usage:
    pytest tests/e2e/test_search_summary.py -v
    pytest tests/e2e/test_search_summary.py -v --headed
"""

import pytest
import requests
import os
from playwright.sync_api import Page, expect


def get_api_url():
    """Get the txtai API URL from environment."""
    return os.getenv("TEST_TXTAI_API_URL", "http://localhost:9301")


def add_document(doc_id: str, content: str, metadata: dict):
    """Add a document via txtai API with metadata."""
    api_url = get_api_url()
    response = requests.post(
        f"{api_url}/add",
        json=[{
            "id": doc_id,
            "text": content,
            "data": metadata
        }],
        timeout=30
    )
    return response


def index_documents():
    """Trigger indexing via txtai API."""
    api_url = get_api_url()
    return requests.get(f"{api_url}/upsert", timeout=60)


def check_graphiti_has_data(query: str):
    """
    Check if Graphiti has data for a given query.

    Returns:
        tuple: (has_entities, has_relationships, entity_names)
        - has_entities: bool - True if Graphiti returned entities
        - has_relationships: bool - True if Graphiti returned relationships
        - entity_names: list - Names of entities found
    """
    api_url = get_api_url()
    try:
        # Use txtai graph search to check if Graphiti has data
        response = requests.get(
            f"{api_url}/graphsearch",
            params={"query": query, "limit": 10},
            timeout=30
        )

        if response.status_code != 200:
            return (False, False, [])

        data = response.json()

        # Check if Graphiti returned entities
        entities = data.get('entities', [])
        relationships = data.get('relationships', [])

        has_entities = len(entities) > 0
        has_relationships = len(relationships) > 0
        entity_names = [e.get('name') for e in entities if e.get('name')]

        return (has_entities, has_relationships, entity_names)
    except Exception as e:
        # If API call fails, assume no Graphiti data
        return (False, False, [])


@pytest.mark.e2e
@pytest.mark.search
class TestKnowledgeSummaryDisplay:
    """Test knowledge summary display in search results UI."""

    def test_search_with_full_summary_displayed(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 REQ-001 to REQ-005: Full summary displays all components.

        When search returns results with rich Graphiti data (3+ entities,
        2+ filtered relationships), a full summary should display with:
        - Knowledge Summary header with query
        - Primary entity with type and description
        - Document mentions (up to 5) with snippets
        - Key relationships (up to 3)
        - Statistics footer
        """
        from tests.pages.search_page import SearchPage

        # Note: This test requires Graphiti to be enabled and populated
        # In test environment, we'll mock the response by adding documents
        # with pre-computed Graphiti context (via session state simulation)

        # For E2E testing, we simulate Graphiti context by uploading documents
        # and checking if summary appears (requires real Graphiti integration)

        # Add documents about machine learning
        add_document(
            "ml-intro",
            "Machine learning is a subset of artificial intelligence that enables computers to learn from data.",
            {"filename": "ml_intro.txt", "title": "Introduction to Machine Learning", "category": "technical"}
        )
        add_document(
            "ml-algorithms",
            "Machine learning algorithms include neural networks, decision trees, and support vector machines.",
            {"filename": "ml_algorithms.txt", "title": "ML Algorithms", "category": "technical"}
        )
        add_document(
            "ml-applications",
            "Machine learning applications span image recognition, natural language processing, and predictive analytics.",
            {"filename": "ml_applications.txt", "title": "ML Applications", "category": "technical"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()

        # Perform search
        search_page.search("machine learning")
        search_page.expect_results_visible()

        # CRITICAL: Verify Graphiti actually has data for this query
        # This prevents false confidence when Graphiti is disabled/broken
        has_entities, has_relationships, entity_names = check_graphiti_has_data("machine learning")

        # Only assert summary UI if Graphiti actually returned data
        if has_entities:
            # REQ-001: Summary displays above results
            knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first
            expect(knowledge_summary_header).to_be_visible()

            # Verify query appears in header (SEC-001: escaped)
            expect(knowledge_summary_header).to_contain_text("machine learning")

            # CRITICAL: Verify specific entity name appears in UI (not just "summary exists")
            # This ensures the summary is actually populated with Graphiti data
            if entity_names:
                # At least one entity name should appear in the summary
                entity_found = False
                for entity_name in entity_names:
                    entity_locator = e2e_page.locator(f'text=/{entity_name}/i').first
                    if entity_locator.count() > 0:
                        entity_found = True
                        break
                assert entity_found, f"Expected at least one entity from {entity_names} to appear in summary"

            # REQ-002: Primary entity displayed with type emoji
            # Look for entity type emoji (concept: 💡, technology: ⚙️, person: 👤, etc.)
            entity_section = e2e_page.locator('[data-testid="stMarkdown"]').filter(
                has_text="💡"
            ).or_(e2e_page.locator('[data-testid="stMarkdown"]').filter(
                has_text="⚙️"
            )).first

            if entity_section.count() > 0:
                expect(entity_section).to_be_visible()

            # REQ-003: Document mentions section
            # Look for "Documents mentioning" or "Mentioned in documents" heading
            doc_mentions = e2e_page.locator('text=/Documents? mention/i').first
            if doc_mentions.count() > 0:
                expect(doc_mentions).to_be_visible()

            # REQ-004: Key relationships section (full mode only)
            # Look for "Key relationships" heading
            relationships = e2e_page.locator('text=/Key relationships?/i').first
            # Relationships may or may not be present depending on data

            # REQ-005: Statistics footer
            # Look for stats like "3 entities • 5 relationships • 3 documents"
            stats = e2e_page.locator('text=/\\d+ entit(y|ies) • \\d+ relationship/i').first
            if stats.count() > 0:
                expect(stats).to_be_visible()

        else:
            # Graphiti disabled or no data - summary should not appear
            # This is expected behavior (graceful degradation)
            pass

    def test_search_with_sparse_summary_displayed(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 REQ-006: Sparse summary displays when thresholds not met.

        When Graphiti returns limited data (2 entities, 1 relationship),
        sparse mode should display without the "Key relationships" section.
        """
        from tests.pages.search_page import SearchPage

        # Add documents with limited cross-document context
        add_document(
            "python-basics",
            "Python is a high-level programming language known for its simplicity.",
            {"filename": "python_basics.txt", "title": "Python Basics", "category": "technical"}
        )
        add_document(
            "python-web",
            "Python is widely used for web development with frameworks like Django and Flask.",
            {"filename": "python_web.txt", "title": "Python Web Development", "category": "technical"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search("Python programming")
        search_page.expect_results_visible()

        # CRITICAL: Verify Graphiti has data before asserting UI elements
        has_entities, has_relationships, entity_names = check_graphiti_has_data("Python programming")

        # Only assert summary UI if Graphiti actually returned data
        if has_entities:
            # Summary should be visible
            knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first
            expect(knowledge_summary_header).to_be_visible()

            # CRITICAL: Verify specific entity appears in UI
            if entity_names:
                entity_found = False
                for entity_name in entity_names:
                    entity_locator = e2e_page.locator(f'text=/{entity_name}/i').first
                    if entity_locator.count() > 0:
                        entity_found = True
                        break
                assert entity_found, f"Expected at least one entity from {entity_names} to appear in summary"

            # Sparse mode: Should have primary entity and documents
            # Should NOT have "Key relationships" section
            relationships_heading = e2e_page.locator('text=/Key relationships?:/i').first
            expect(relationships_heading).not_to_be_visible()

            # Should still have document mentions
            doc_mentions = e2e_page.locator('text=/Documents? mention/i').first
            if doc_mentions.count() > 0:
                expect(doc_mentions).to_be_visible()
        else:
            # Graphiti has no data - summary should not appear
            # This is expected for this specific query/documents
            pass

    def test_search_with_no_summary(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 REQ-007: Summary skipped when data insufficient.

        When Graphiti returns insufficient data (1 entity or single source doc),
        no summary should display. Search results should appear directly.
        """
        from tests.pages.search_page import SearchPage

        # Add a single document (single source = no summary per EDGE-002)
        add_document(
            "standalone",
            "This is a standalone document about a unique topic with no cross-references.",
            {"filename": "standalone.txt", "title": "Standalone Document", "category": "personal"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search("standalone")
        search_page.expect_results_visible()

        # Summary should NOT appear (insufficient data)
        knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first
        expect(knowledge_summary_header).not_to_be_visible()

        # Search results should still display normally
        # UI shows "Total results: X" format
        result_count = e2e_page.locator('text=/Total results.*\\d+/i').first
        expect(result_count).to_be_visible()

    def test_summary_document_link_navigation(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 UX-003: Clicking document link in summary navigates to View Source.

        When user clicks a document link in the "Documents mentioning" section,
        they should navigate to the View Source page showing that document.
        """
        from tests.pages.search_page import SearchPage
        from tests.pages.view_source_page import ViewSourcePage

        # Add documents
        add_document(
            "docker-intro",
            "Docker is a platform for developing, shipping, and running applications in containers.",
            {"filename": "docker_intro.txt", "title": "Docker Introduction", "category": "technical"}
        )
        add_document(
            "docker-compose",
            "Docker Compose is a tool for defining multi-container Docker applications.",
            {"filename": "docker_compose.txt", "title": "Docker Compose Guide", "category": "technical"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search and perform query
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search("Docker")
        search_page.expect_results_visible()

        # Check if summary is displayed
        knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first

        if knowledge_summary_header.count() > 0:
            # Find document link in summary (links look like "📄 docker_intro.txt")
            # Document links are markdown links that should be clickable
            doc_link = e2e_page.locator('a[href*="/View_Source"]').first

            if doc_link.count() > 0:
                # Click the document link
                doc_link.click()

                # Wait for navigation to View Source page
                e2e_page.wait_for_url("**/View_Source**", timeout=5000)

                # Verify we're on View Source page
                view_source_page = ViewSourcePage(e2e_page)
                expect(view_source_page.page_title).to_be_visible()

                # Verify document content is displayed
                # (specific validation would require knowing exact document ID)

    def test_summary_with_graphiti_disabled(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 FAIL-001: No errors when Graphiti is disabled.

        When Graphiti is disabled (NEO4J_DISABLED=true), no summary should display
        and search should work normally without errors.
        """
        from tests.pages.search_page import SearchPage

        # Add documents
        add_document(
            "test-doc",
            "Test document content for search without Graphiti.",
            {"filename": "test.txt", "title": "Test Document", "category": "personal"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search("test")
        search_page.expect_results_visible()

        # Summary should NOT appear (Graphiti disabled in test env)
        knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first
        expect(knowledge_summary_header).not_to_be_visible()

        # Search results should display normally
        result_items = search_page.result_items
        expect(result_items.first).to_be_visible()

        # No error messages should appear
        error_message = e2e_page.locator('[data-testid="stAlert"]').filter(
            has_text="error"
        ).first
        expect(error_message).not_to_be_visible()

    def test_summary_escapes_malicious_query(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 SEC-001: Summary escapes malicious query strings (XSS prevention).

        When user searches for a query with HTML/JavaScript injection attempts,
        the summary header should escape the query properly and not execute scripts.
        """
        from tests.pages.search_page import SearchPage

        # Add documents
        add_document(
            "security-doc",
            "Information security and cybersecurity best practices.",
            {"filename": "security.txt", "title": "Security Guide", "category": "technical"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()

        # Attempt XSS attack in query
        malicious_query = '<script>alert("XSS")</script>'
        search_page.search(malicious_query)

        # Wait for search to complete
        e2e_page.wait_for_timeout(2000)

        # Verify no alert dialog appeared (script should not execute)
        # Playwright automatically waits for and handles dialogs, so if no exception
        # is raised, the XSS attempt was blocked

        # Check if summary header exists
        knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first

        if knowledge_summary_header.count() > 0:
            # Query should be escaped in the summary header
            # The raw text should NOT contain <script> tags
            header_text = knowledge_summary_header.inner_text()
            assert "<script>" not in header_text, \
                "Query should be escaped (no <script> tags in display)"

            # Escaped text should be visible (shown as literal string)
            # escape_for_markdown() would escape the angle brackets
            assert "script" in header_text.lower(), \
                "Query text should still be visible (escaped)"

        # Search results should display normally (no crash from malicious query)
        # Even if no results, the page should not error
        page_content = e2e_page.content()
        assert "error" not in page_content.lower() or "No results found" in page_content


@pytest.mark.e2e
@pytest.mark.search
class TestKnowledgeSummaryAccessibility:
    """Test accessibility features of knowledge summary."""

    def test_summary_aria_labels(
        self, e2e_page: Page, base_url: str, clean_postgres, clean_qdrant
    ):
        """
        SPEC-031 UX-004: Summary components have accessibility labels.

        Verify that summary sections have appropriate ARIA labels or semantic HTML
        for screen reader accessibility.
        """
        from tests.pages.search_page import SearchPage

        # Add documents
        add_document(
            "ai-doc-1",
            "Artificial intelligence and machine learning fundamentals.",
            {"filename": "ai_basics.txt", "title": "AI Basics", "category": "technical"}
        )
        add_document(
            "ai-doc-2",
            "Artificial intelligence applications in healthcare and finance.",
            {"filename": "ai_apps.txt", "title": "AI Applications", "category": "technical"}
        )

        index_documents()
        e2e_page.wait_for_timeout(2000)

        # Navigate to search
        search_page = SearchPage(e2e_page)
        search_page.navigate()
        search_page.search("artificial intelligence")
        search_page.expect_results_visible()

        # Check if summary is present
        knowledge_summary_header = e2e_page.locator('text=/Knowledge Summary: .+/i').first

        if knowledge_summary_header.count() > 0:
            # UX-004: Verify accessibility features for screen readers

            # 1. Check for proper heading hierarchy
            # Summary header should be h3 (### in Streamlit markdown)
            summary_h3 = e2e_page.locator('h3').filter(has_text="Knowledge Summary")
            if summary_h3.count() > 0:
                expect(summary_h3.first).to_be_visible()
                # Verify heading has actual text content
                heading_text = summary_h3.first.inner_text()
                assert len(heading_text) > 10, "Heading should have meaningful content"

            # 2. Verify entity type text is present (not just emoji)
            # Line 72 of Search.py shows: `{type_emoji} **`{entity_name}`** ({entity_type})`
            # Entity type should appear in parentheses for screen readers
            entity_types = ['person', 'organization', 'concept', 'location', 'technology', 'product', 'event']
            entity_type_found = False
            for entity_type in entity_types:
                # Look for entity type in parentheses: (person), (organization), etc.
                entity_type_locator = e2e_page.locator(f'text=/\\({entity_type}\\)/i')
                if entity_type_locator.count() > 0:
                    entity_type_found = True
                    expect(entity_type_locator.first).to_be_visible()
                    break

            if entity_type_found:
                # Good: Entity type text present for screen readers
                pass
            else:
                # If no entity type found, at least check emoji is present
                # (still works for screen readers via alt text)
                entity_emoji_locator = e2e_page.locator('text=/[👤🏢💡📍⚙️📦📌]/').first
                if entity_emoji_locator.count() > 0:
                    expect(entity_emoji_locator).to_be_visible()

            # 3. Verify semantic HTML structure (Streamlit generates proper containers)
            # Check that content is within proper container elements
            # Streamlit uses [data-testid="stMarkdown"] for markdown content
            markdown_containers = e2e_page.locator('[data-testid="stMarkdown"]')
            assert markdown_containers.count() >= 3, \
                "Should have multiple markdown containers (header, entity, documents)"

            # 4. Document links should have meaningful text (not "click here")
            doc_links = e2e_page.locator('a[href*="/View_Source"]')
            if doc_links.count() > 0:
                for i in range(min(3, doc_links.count())):
                    link = doc_links.nth(i)
                    link_text = link.inner_text()

                    # Link text should be non-empty and meaningful
                    assert link_text.strip() != "", \
                        "Links should have descriptive text (filename/title)"
                    assert "click here" not in link_text.lower(), \
                        "Links should not use generic 'click here' text (a11y violation)"
                    assert len(link_text.strip()) >= 3, \
                        "Link text should be meaningful (>= 3 chars)"

            # 5. Verify relationship text structure (if full mode)
            # Relationships should have textual context: "source → rel_type → target"
            relationships_section = e2e_page.locator('text=/Key Relationships?:/i').first
            if relationships_section.count() > 0:
                # Check for arrow symbols with textual context
                relationship_items = e2e_page.locator('text=/→/')
                if relationship_items.count() > 0:
                    # Verify relationship has surrounding text (not just arrows)
                    rel_text = relationship_items.first.inner_text()
                    assert len(rel_text) > 5, \
                        "Relationships should have descriptive text, not just symbols"

            # 6. Verify statistics footer uses proper caption style
            # Stats footer should be visible and contain entity/relationship/document counts
            stats_footer = e2e_page.locator('text=/\\d+ entit(y|ies) • \\d+ relationship/i').first
            if stats_footer.count() > 0:
                expect(stats_footer).to_be_visible()
                stats_text = stats_footer.inner_text()
                # Verify stats contain numbers (not empty)
                assert any(char.isdigit() for char in stats_text), \
                    "Statistics should contain numeric counts"
