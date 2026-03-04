#!/bin/bash
#
# Setup script for txtai git hooks
# SPEC-029 REQ-002: Installs git hooks after repository clone
# SPEC-037 P1-002: Optional Graphiti version check hook
#
# Usage:
#   ./scripts/setup-hooks.sh                    # Install post-merge hook only
#   ./scripts/setup-hooks.sh --graphiti-check   # Also install pre-commit version check
#
# This script is idempotent - safe to run multiple times.
#

set -e

# Parse arguments
INSTALL_GRAPHITI_CHECK=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --graphiti-check)
            INSTALL_GRAPHITI_CHECK=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--graphiti-check]"
            exit 1
            ;;
    esac
done

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo -e "${BLUE}  txtai Git Hooks Setup${NC}"
echo -e "${BLUE}════════════════════════════════════════${NC}"
echo ""

# Check if we're in a git repository
if [ ! -d "$PROJECT_ROOT/.git" ]; then
    echo -e "${RED}✗ Error: Not a git repository${NC}"
    echo "Run this script from the project root or scripts directory"
    exit 1
fi

# Check if hooks template directory exists
if [ ! -d "$PROJECT_ROOT/hooks" ]; then
    echo -e "${RED}✗ Error: hooks/ directory not found${NC}"
    echo "Expected location: $PROJECT_ROOT/hooks"
    exit 1
fi

# Install post-merge hook
HOOK_SOURCE="$PROJECT_ROOT/hooks/post-merge"
HOOK_DEST="$PROJECT_ROOT/.git/hooks/post-merge"

if [ ! -f "$HOOK_SOURCE" ]; then
    echo -e "${RED}✗ Error: Hook template not found${NC}"
    echo "Expected: $HOOK_SOURCE"
    exit 1
fi

echo "Installing post-merge hook..."

# Copy hook to .git/hooks/
cp "$HOOK_SOURCE" "$HOOK_DEST"

# Make executable
chmod +x "$HOOK_DEST"

echo -e "${GREEN}✓ Installed: .git/hooks/post-merge${NC}"
echo ""
echo "Hook details:"
echo "  Source:   hooks/post-merge"
echo "  Purpose:  Auto-backup on merge to master"
echo "  Triggers: After successful git merge to master branch"
echo ""

# Install optional pre-commit hook for Graphiti version check
if [ "$INSTALL_GRAPHITI_CHECK" = true ]; then
    echo "Installing pre-commit hook (Graphiti version check)..."

    PRECOMMIT_SOURCE="$PROJECT_ROOT/hooks/pre-commit-graphiti-check"
    PRECOMMIT_DEST="$PROJECT_ROOT/.git/hooks/pre-commit"

    if [ ! -f "$PRECOMMIT_SOURCE" ]; then
        echo -e "${RED}✗ Error: Hook template not found${NC}"
        echo "Expected: $PRECOMMIT_SOURCE"
        exit 1
    fi

    # Copy hook to .git/hooks/
    cp "$PRECOMMIT_SOURCE" "$PRECOMMIT_DEST"

    # Make executable
    chmod +x "$PRECOMMIT_DEST"

    echo -e "${GREEN}✓ Installed: .git/hooks/pre-commit${NC}"
    echo ""
    echo "Hook details:"
    echo "  Source:   hooks/pre-commit-graphiti-check"
    echo "  Purpose:  Prevent commits when graphiti-core versions mismatch"
    echo "  Triggers: Before every git commit"
    echo "  Skip:     Use 'git commit --no-verify' to bypass"
    echo ""
fi

echo -e "${GREEN}✓ Setup complete!${NC}"
echo ""

if [ "$INSTALL_GRAPHITI_CHECK" = true ]; then
    echo "Installed hooks:"
    echo "  • post-merge: Auto-backup on merge to master"
    echo "  • pre-commit: Graphiti version synchronization check"
    echo ""
    echo "The pre-commit hook will validate that frontend and MCP use"
    echo "the same graphiti-core version before allowing commits."
    echo ""
    echo "To test the version check:"
    echo "  ./scripts/check-graphiti-version.sh"
    echo ""
else
    echo "Installed hooks:"
    echo "  • post-merge: Auto-backup on merge to master"
    echo ""
    echo "To also install Graphiti version check (pre-commit hook):"
    echo "  ./scripts/setup-hooks.sh --graphiti-check"
    echo ""
fi

echo "The post-merge hook will now automatically create backups"
echo "when you merge feature branches to master, protecting your"
echo "data before any documents are uploaded with new code."
echo ""
