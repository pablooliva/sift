#!/bin/bash
# Master test runner for backup automation (SPEC-042)
#
# Runs all test suites:
#   - Unit tests (validation functions)
#   - Edge case tests (EDGE-001 through EDGE-021)
#   - Integration tests (full backup cycle)
#
# Usage:
#   ./test-backup-automation.sh           # Run all tests
#   ./test-backup-automation.sh --unit    # Run unit tests only
#   ./test-backup-automation.sh --edge    # Run edge case tests only
#   ./test-backup-automation.sh --quick   # Run unit + edge (skip integration)
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more test suites failed

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Test scripts
UNIT_TESTS="$PROJECT_ROOT/tests/unit/backup/test-cron-backup.sh"
EDGE_TESTS="$PROJECT_ROOT/tests/integration/backup/test-edge-cases.sh"

# Parse arguments
RUN_UNIT=true
RUN_EDGE=true
RUN_INTEGRATION=false

if [ $# -gt 0 ]; then
    RUN_UNIT=false
    RUN_EDGE=false
    RUN_INTEGRATION=false

    for arg in "$@"; do
        case $arg in
            --unit)
                RUN_UNIT=true
                ;;
            --edge)
                RUN_EDGE=true
                ;;
            --integration)
                RUN_INTEGRATION=true
                ;;
            --quick)
                RUN_UNIT=true
                RUN_EDGE=true
                ;;
            --all)
                RUN_UNIT=true
                RUN_EDGE=true
                RUN_INTEGRATION=true
                ;;
            --help)
                echo "Usage: $0 [--unit] [--edge] [--integration] [--quick] [--all]"
                echo ""
                echo "Options:"
                echo "  --unit          Run unit tests only"
                echo "  --edge          Run edge case tests only"
                echo "  --integration   Run integration tests only"
                echo "  --quick         Run unit + edge tests (no integration)"
                echo "  --all           Run all tests (default)"
                echo "  --help          Show this help message"
                exit 0
                ;;
            *)
                echo "Unknown argument: $arg"
                echo "Run with --help for usage information"
                exit 1
                ;;
        esac
    done
fi

# If no specific tests selected, run all
if [ "$RUN_UNIT" = false ] && [ "$RUN_EDGE" = false ] && [ "$RUN_INTEGRATION" = false ]; then
    RUN_UNIT=true
    RUN_EDGE=true
    # Note: Integration tests are opt-in
fi

# Test suite results
SUITES_RUN=0
SUITES_PASSED=0
SUITES_FAILED=0

# Header
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Backup Automation Test Suite (SPEC-042)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ============================================================================
# Run Unit Tests
# ============================================================================

if [ "$RUN_UNIT" = true ]; then
    echo -e "${BLUE}▶${NC} Running unit tests..."
    SUITES_RUN=$((SUITES_RUN + 1))

    if [ -f "$UNIT_TESTS" ]; then
        if "$UNIT_TESTS"; then
            echo -e "${GREEN}✓${NC} Unit tests passed"
            SUITES_PASSED=$((SUITES_PASSED + 1))
        else
            echo -e "${RED}✗${NC} Unit tests failed"
            SUITES_FAILED=$((SUITES_FAILED + 1))
        fi
    else
        echo -e "${RED}✗${NC} Unit test script not found: $UNIT_TESTS"
        SUITES_FAILED=$((SUITES_FAILED + 1))
    fi
    echo ""
fi

# ============================================================================
# Run Edge Case Tests
# ============================================================================

if [ "$RUN_EDGE" = true ]; then
    echo -e "${BLUE}▶${NC} Running edge case tests..."
    SUITES_RUN=$((SUITES_RUN + 1))

    if [ -f "$EDGE_TESTS" ]; then
        if "$EDGE_TESTS"; then
            echo -e "${GREEN}✓${NC} Edge case tests passed"
            SUITES_PASSED=$((SUITES_PASSED + 1))
        else
            echo -e "${RED}✗${NC} Edge case tests failed"
            SUITES_FAILED=$((SUITES_FAILED + 1))
        fi
    else
        echo -e "${RED}✗${NC} Edge case test script not found: $EDGE_TESTS"
        SUITES_FAILED=$((SUITES_FAILED + 1))
    fi
    echo ""
fi

# ============================================================================
# Run Integration Tests
# ============================================================================

if [ "$RUN_INTEGRATION" = true ]; then
    echo -e "${BLUE}▶${NC} Running integration tests..."
    echo -e "${YELLOW}Note:${NC} Integration tests require Docker services and may modify test data"
    SUITES_RUN=$((SUITES_RUN + 1))

    # Integration tests would go here (manual testing for now)
    echo -e "${YELLOW}⊘${NC} Integration tests not yet implemented (manual testing required)"
    echo ""
fi

# ============================================================================
# Summary
# ============================================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Test Suite Summary:"
echo "  Total suites:  $SUITES_RUN"
echo -e "  ${GREEN}Passed:${NC}        $SUITES_PASSED"

if [ "$SUITES_FAILED" -gt 0 ]; then
    echo -e "  ${RED}Failed:${NC}        $SUITES_FAILED"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    exit 1
else
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "${GREEN}All test suites passed!${NC}"
    exit 0
fi
