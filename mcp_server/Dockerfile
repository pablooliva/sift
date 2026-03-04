# txtai RAG MCP Server
# SPEC-015: Claude Code + txtai MCP Integration
#
# Provides stdio-based MCP server for Claude Code integration
# with txtai semantic search and RAG capabilities

FROM python:3.11-slim

LABEL maintainer="Pablo"
LABEL description="txtai RAG MCP Server for Claude Code integration"

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy dependency files first for better caching
# Include README.md as it's referenced in pyproject.toml
COPY pyproject.toml uv.lock README.md ./

# Install dependencies using UV
# --no-dev excludes development dependencies
# --frozen ensures lock file is used exactly as-is
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 mcpuser && \
    chown -R mcpuser:mcpuser /app

USER mcpuser

# Environment variables (defaults, override via docker-compose)
ENV TXTAI_API_URL=http://txtai:8300
ENV PYTHONUNBUFFERED=1

# Run MCP server (stdio transport)
# Note: This runs in foreground, waiting for MCP client connection
ENTRYPOINT ["uv", "run", "txtai_rag_mcp.py"]
