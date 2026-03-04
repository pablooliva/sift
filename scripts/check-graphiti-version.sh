#!/bin/bash
#
# Check Graphiti Version Synchronization (SPEC-037 P1-002)
#
# Validates that frontend and MCP server use the same graphiti-core version.
# This is critical because different versions produce different knowledge graph
# results, causing inconsistencies between frontend uploads and MCP queries.
#
# Usage:
#   ./scripts/check-graphiti-version.sh
#
# Exit codes:
#   0 - Versions match (success)
#   1 - Versions mismatch (error)
#   2 - Could not parse versions (error)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# File paths
FRONTEND_REQ="frontend/requirements.txt"
MCP_PYPROJECT="mcp_server/pyproject.toml"

# Check files exist
if [[ ! -f "$FRONTEND_REQ" ]]; then
    echo -e "${RED}ERROR: $FRONTEND_REQ not found${NC}"
    echo "Run this script from the project root directory."
    exit 2
fi

if [[ ! -f "$MCP_PYPROJECT" ]]; then
    echo -e "${RED}ERROR: $MCP_PYPROJECT not found${NC}"
    echo "Run this script from the project root directory."
    exit 2
fi

# Extract versions
# Frontend: Look for "graphiti-core==X.Y.Z" or "graphiti-core>=X.Y.Z"
FRONTEND_LINE=$(grep -E '^graphiti-core[>=]' "$FRONTEND_REQ" || true)
if [[ -z "$FRONTEND_LINE" ]]; then
    echo -e "${YELLOW}WARNING: Could not find graphiti-core in $FRONTEND_REQ${NC}"
    echo "Expected format: graphiti-core==X.Y.Z"
    exit 2
fi

# Extract version number (supports == or >= syntax)
FRONTEND_VERSION=$(echo "$FRONTEND_LINE" | grep -oP '(==|>=)\K[0-9.]+')
if [[ -z "$FRONTEND_VERSION" ]]; then
    echo -e "${RED}ERROR: Could not parse version from: $FRONTEND_LINE${NC}"
    exit 2
fi

# MCP: Look for 'graphiti-core = "==X.Y.Z"' or 'graphiti-core = ">=X.Y.Z"'
MCP_LINE=$(grep -E 'graphiti-core\s*=' "$MCP_PYPROJECT" || true)
if [[ -z "$MCP_LINE" ]]; then
    echo -e "${YELLOW}WARNING: Could not find graphiti-core in $MCP_PYPROJECT${NC}"
    echo "Expected format: graphiti-core = \"==X.Y.Z\""
    exit 2
fi

# Extract version number (supports == or >= syntax within quotes)
MCP_VERSION=$(echo "$MCP_LINE" | grep -oP '(==|>=)\K[0-9.]+')
if [[ -z "$MCP_VERSION" ]]; then
    echo -e "${RED}ERROR: Could not parse version from: $MCP_LINE${NC}"
    exit 2
fi

# Compare versions
if [[ "$FRONTEND_VERSION" == "$MCP_VERSION" ]]; then
    echo -e "${GREEN}✓ Graphiti versions match: $FRONTEND_VERSION${NC}"
    exit 0
else
    echo -e "${RED}ERROR: Graphiti version mismatch detected!${NC}"
    echo ""
    echo "  Frontend: graphiti-core==$FRONTEND_VERSION  ($FRONTEND_REQ)"
    echo "  MCP:      graphiti-core==$MCP_VERSION  ($MCP_PYPROJECT)"
    echo ""
    echo "This will cause inconsistent knowledge graph behavior between frontend"
    echo "and MCP server. Please update both to the same version."
    echo ""
    echo -e "${YELLOW}Action required:${NC}"
    echo "  1. Decide on target version (usually the newer one)"

    # Suggest which one to update
    if [[ "$FRONTEND_VERSION" > "$MCP_VERSION" ]]; then
        echo "  2. Update MCP to match frontend:"
        echo "     - Edit $MCP_PYPROJECT"
        echo "     - Change graphiti-core = \"==$MCP_VERSION\" to \"==$FRONTEND_VERSION\""
    else
        echo "  2. Update frontend to match MCP:"
        echo "     - Edit $FRONTEND_REQ"
        echo "     - Change graphiti-core==$FRONTEND_VERSION to ==$MCP_VERSION"
    fi

    echo "  3. Rebuild containers: docker compose build"
    echo "  4. Run this check again to verify: ./scripts/check-graphiti-version.sh"
    echo ""
    exit 1
fi
