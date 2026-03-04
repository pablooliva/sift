"""
Graphiti integration package for MCP server.

SPEC-037: MCP Graphiti Knowledge Graph Integration
Provides async interface to Graphiti SDK adapted for FastMCP native asyncio.
"""

from .graphiti_client_async import GraphitiClientAsync, get_graphiti_client

__all__ = ['GraphitiClientAsync', 'get_graphiti_client']
