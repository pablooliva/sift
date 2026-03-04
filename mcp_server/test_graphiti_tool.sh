#!/bin/bash
# Test knowledge_graph_search tool with empty graph
set -e

echo "Testing knowledge_graph_search tool..."
echo

{
    echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test-client","version":"1.0"}},"id":1}'
    sleep 0.5
    echo '{"jsonrpc":"2.0","method":"notifications/initialized"}'
    sleep 0.5
    # Call knowledge_graph_search tool
    echo '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"knowledge_graph_search","arguments":{"query":"machine learning","limit":10}},"id":3}'
    sleep 2
} | docker exec -i txtai-mcp uv run txtai_rag_mcp.py 2>&1 | \
    grep -E '(knowledge_graph_search|"result"|"entities"|"relationships")' | head -50

echo
echo "✅ knowledge_graph_search tool test complete"
