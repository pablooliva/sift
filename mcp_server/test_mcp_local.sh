#!/bin/bash
# Test MCP server local deployment
# Sends proper MCP initialization sequence and tests tools

set -e

echo "Testing txtai-mcp local deployment (Docker exec)..."
echo

# Test MCP protocol handshake and tools list
{
    # 1. Initialize
    echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0"}},"id":1}'
    sleep 0.5

    # 2. Initialized notification
    echo '{"jsonrpc":"2.0","method":"notifications/initialized"}'
    sleep 0.5

    # 3. List tools
    echo '{"jsonrpc":"2.0","method":"tools/list","id":2}'
    sleep 1

} | docker exec -i txtai-mcp uv run txtai_rag_mcp.py 2>&1 | \
    grep -A 1000 '"result"' | head -200

echo
echo "✅ MCP local deployment test complete"
