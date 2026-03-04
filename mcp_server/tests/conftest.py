"""
Pytest configuration and fixtures for MCP server tests.
SPEC-015: Claude Code + txtai MCP Integration
"""

import os
import pytest
from unittest.mock import Mock, patch


@pytest.fixture
def mock_env():
    """Set up test environment variables."""
    env_vars = {
        "TXTAI_API_URL": "http://localhost:8300",
        "TOGETHERAI_API_KEY": "test-api-key",
        "RAG_LLM_MODEL": "Qwen/Qwen2.5-72B-Instruct-Turbo",
        "RAG_SEARCH_WEIGHTS": "0.5",
        "RAG_SIMILARITY_THRESHOLD": "0.5",
        "RAG_MAX_DOCUMENT_CHARS": "10000",
        "RAG_MAX_TOKENS": "500",
        "RAG_TEMPERATURE": "0.3"
    }
    with patch.dict(os.environ, env_vars):
        yield env_vars


@pytest.fixture
def sample_search_results():
    """Sample search results from txtai API."""
    return [
        {
            "id": "doc-001",
            "text": "This is a sample document about Python programming.",
            "score": 0.85,
            "data": '{"filename": "python_guide.md", "category": "technical"}'
        },
        {
            "id": "doc-002",
            "text": "Another document discussing machine learning concepts.",
            "score": 0.72,
            "data": '{"filename": "ml_intro.md", "category": "technical"}'
        }
    ]


@pytest.fixture
def sample_llm_response():
    """Sample Together AI LLM response."""
    return {
        "choices": [
            {
                "text": "Based on the documents, Python is a programming language commonly used for machine learning and data science applications."
            }
        ]
    }


@pytest.fixture
def mock_requests_success(sample_search_results, sample_llm_response):
    """Mock successful HTTP requests."""
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        # Mock search response
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = sample_search_results
        search_response.raise_for_status = Mock()
        mock_get.return_value = search_response

        # Mock LLM response
        llm_response = Mock()
        llm_response.status_code = 200
        llm_response.json.return_value = sample_llm_response
        llm_response.raise_for_status = Mock()
        mock_post.return_value = llm_response

        yield {"get": mock_get, "post": mock_post}


@pytest.fixture
def mock_requests_empty_results():
    """Mock empty search results."""
    with patch('requests.get') as mock_get:
        response = Mock()
        response.status_code = 200
        response.json.return_value = []
        response.raise_for_status = Mock()
        mock_get.return_value = response
        yield mock_get


@pytest.fixture
def mock_requests_connection_error():
    """Mock connection error."""
    import requests
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        yield mock_get


@pytest.fixture
def mock_requests_timeout():
    """Mock timeout error."""
    import requests
    with patch('requests.get') as mock_get:
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")
        yield mock_get


@pytest.fixture
def mock_requests_rate_limit():
    """Mock rate limit error (429)."""
    import requests
    with patch('requests.get') as mock_get, patch('requests.post') as mock_post:
        # Search succeeds
        search_response = Mock()
        search_response.status_code = 200
        search_response.json.return_value = [{"id": "doc-001", "text": "Test", "score": 0.8, "data": "{}"}]
        search_response.raise_for_status = Mock()
        mock_get.return_value = search_response

        # LLM call fails with rate limit
        rate_limit_response = Mock()
        rate_limit_response.status_code = 429
        rate_limit_error = requests.exceptions.HTTPError(response=rate_limit_response)
        mock_post.side_effect = rate_limit_error

        yield {"get": mock_get, "post": mock_post}


# SPEC-037: Graphiti knowledge graph fixtures
@pytest.fixture
def mock_graphiti_env():
    """Set up Graphiti-specific environment variables."""
    env_vars = {
        "NEO4J_URI": "bolt://localhost:7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "test-password",
        "GRAPHITI_SEARCH_TIMEOUT_SECONDS": "10",
        "OLLAMA_API_URL": "http://localhost:11434"
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars
