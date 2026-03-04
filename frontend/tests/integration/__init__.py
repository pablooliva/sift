"""
Integration tests for txtai frontend (SPEC-025, REQ-021-023).

These tests verify cross-component workflows:
- Upload-to-search (REQ-021)
- RAG-to-source navigation (REQ-022)
- Graph visualization with documents (REQ-023)

Unlike E2E tests that use browser automation, these tests verify
the integration between components using direct API calls and
Streamlit AppTest where appropriate.
"""
