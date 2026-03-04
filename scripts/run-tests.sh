#!/bin/bash
#
# Test runner script for txtai project
# Runs tests in order: backend -> unit -> integration -> e2e
#
# Usage:
#   ./scripts/run-tests.sh              # Run all tests
#   ./scripts/run-tests.sh --backend    # Backend API tests only (requires services)
#   ./scripts/run-tests.sh --unit       # Frontend unit tests only (fast, no services needed)
#   ./scripts/run-tests.sh --no-e2e     # Skip E2E tests (backend + unit + integration)
#   ./scripts/run-tests.sh --e2e-only   # E2E tests only
#   ./scripts/run-tests.sh --quick      # Unit tests, skip slow markers
#   ./scripts/run-tests.sh --headed     # Run E2E tests with visible browser
#   ./scripts/run-tests.sh --frontend   # Frontend tests only (unit + integration + e2e)
#
# Exit codes:
#   0 - All tests passed
#   1 - Some tests failed
#   2 - Service check failed (for tests requiring services)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# Test ports (from SPEC-024)
TEST_API_PORT="${TEST_TXTAI_API_PORT:-9301}"
TEST_POSTGRES_PORT="${TEST_POSTGRES_PORT:-9433}"
TEST_QDRANT_PORT="${TEST_QDRANT_PORT:-9333}"
TEST_FRONTEND_PORT="${TEST_FRONTEND_PORT:-9502}"

# Default options
RUN_BACKEND=true
RUN_UNIT=true
RUN_INTEGRATION=true
RUN_E2E=true
SKIP_SLOW=false
HEADED=false
VERBOSE="-v"
EXTRA_ARGS=""

# Track results
BACKEND_RESULT=0
UNIT_RESULT=0
INTEGRATION_RESULT=0
E2E_RESULT=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --backend|--backend-only)
            RUN_BACKEND=true
            RUN_UNIT=false
            RUN_INTEGRATION=false
            RUN_E2E=false
            shift
            ;;
        --frontend|--frontend-only)
            RUN_BACKEND=false
            RUN_UNIT=true
            RUN_INTEGRATION=true
            RUN_E2E=true
            shift
            ;;
        --unit|--unit-only)
            RUN_BACKEND=false
            RUN_UNIT=true
            RUN_INTEGRATION=false
            RUN_E2E=false
            shift
            ;;
        --no-e2e)
            RUN_E2E=false
            shift
            ;;
        --e2e-only)
            RUN_BACKEND=false
            RUN_UNIT=false
            RUN_INTEGRATION=false
            RUN_E2E=true
            shift
            ;;
        --integration|--integration-only)
            RUN_BACKEND=false
            RUN_UNIT=false
            RUN_INTEGRATION=true
            RUN_E2E=false
            shift
            ;;
        --quick)
            SKIP_SLOW=true
            RUN_BACKEND=false
            RUN_E2E=false
            shift
            ;;
        --headed)
            HEADED=true
            shift
            ;;
        --quiet|-q)
            VERBOSE=""
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --backend              Run only backend API tests (requires services)"
            echo "  --frontend             Run only frontend tests (unit + integration + e2e)"
            echo "  --unit, --unit-only    Run only frontend unit tests (fast, no services needed)"
            echo "  --no-e2e               Skip E2E tests (run backend + unit + integration)"
            echo "  --e2e-only             Run only E2E tests"
            echo "  --integration          Run only frontend integration tests"
            echo "  --quick                Run frontend unit tests only, skip slow markers"
            echo "  --headed               Run E2E tests with visible browser"
            echo "  --quiet, -q            Less verbose output"
            echo "  --help, -h             Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  TXTAI_API_URL          txtai API URL for backend tests (default: http://localhost:9301)"
            echo "  TEST_TXTAI_API_PORT    txtai API port (default: 9301)"
            echo "  TEST_POSTGRES_PORT     PostgreSQL port (default: 9433)"
            echo "  TEST_QDRANT_PORT       Qdrant port (default: 9333)"
            echo "  TEST_FRONTEND_PORT     Frontend port (default: 9502)"
            exit 0
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_service() {
    local name=$1
    local host=$2
    local port=$3

    if nc -z "$host" "$port" 2>/dev/null; then
        print_success "$name is available on port $port"
        return 0
    else
        print_warning "$name is not available on port $port"
        return 1
    fi
}

check_services() {
    print_header "Checking Test Services"

    local all_ok=true

    check_service "txtai API" "localhost" "$TEST_API_PORT" || all_ok=false
    check_service "PostgreSQL" "localhost" "$TEST_POSTGRES_PORT" || all_ok=false
    check_service "Qdrant" "localhost" "$TEST_QDRANT_PORT" || all_ok=false

    if [ "$all_ok" = false ]; then
        echo ""
        print_warning "Some services are not running."
        print_warning "Integration and E2E tests require test services."
        print_warning "Start test services or use --unit for unit tests only."
        echo ""
        return 1
    fi

    return 0
}

run_tests() {
    local test_type=$1
    local test_path=$2
    local extra_opts=$3

    print_header "Running $test_type Tests"

    cd "$FRONTEND_DIR"

    local cmd="pytest $test_path $VERBOSE $extra_opts $EXTRA_ARGS"

    if [ "$SKIP_SLOW" = true ]; then
        cmd="$cmd -m 'not slow'"
    fi

    echo "Command: $cmd"
    echo ""

    set +e
    eval $cmd
    local result=$?
    set -e

    return $result
}

# Main execution
print_header "txtai Test Runner"

echo "Configuration:"
echo "  Backend tests:     $([ "$RUN_BACKEND" = true ] && echo "Yes" || echo "No")"
echo "  Unit tests:        $([ "$RUN_UNIT" = true ] && echo "Yes" || echo "No")"
echo "  Integration tests: $([ "$RUN_INTEGRATION" = true ] && echo "Yes" || echo "No")"
echo "  E2E tests:         $([ "$RUN_E2E" = true ] && echo "Yes" || echo "No")"
echo "  Skip slow:         $([ "$SKIP_SLOW" = true ] && echo "Yes" || echo "No")"
echo "  Headed browser:    $([ "$HEADED" = true ] && echo "Yes" || echo "No")"

# Check if we need services
NEEDS_SERVICES=false
if [ "$RUN_BACKEND" = true ] || [ "$RUN_INTEGRATION" = true ] || [ "$RUN_E2E" = true ]; then
    NEEDS_SERVICES=true
fi

if [ "$NEEDS_SERVICES" = true ]; then
    if ! check_services; then
        if [ "$RUN_UNIT" = true ]; then
            print_warning "Continuing with unit tests only..."
            RUN_BACKEND=false
            RUN_INTEGRATION=false
            RUN_E2E=false
        else
            print_error "Cannot run requested tests without services"
            exit 2
        fi
    fi
fi

# Run backend tests
if [ "$RUN_BACKEND" = true ]; then
    print_header "Running Backend Tests"

    cd "$PROJECT_ROOT"

    # Set API URL for backend tests (defaults to test port)
    export TXTAI_API_URL="${TXTAI_API_URL:-http://localhost:$TEST_API_PORT}"

    BACKEND_CMD="pytest tests/ $VERBOSE $EXTRA_ARGS"

    echo "Command: $BACKEND_CMD"
    echo "TXTAI_API_URL: $TXTAI_API_URL"
    echo ""

    set +e
    eval $BACKEND_CMD
    BACKEND_RESULT=$?
    set -e

    if [ $BACKEND_RESULT -eq 0 ]; then
        print_success "Backend tests passed"
    else
        print_error "Backend tests failed"
    fi
fi

# Run unit tests
if [ "$RUN_UNIT" = true ]; then
    if run_tests "Unit" "tests/unit/"; then
        UNIT_RESULT=0
        print_success "Unit tests passed"
    else
        UNIT_RESULT=1
        print_error "Unit tests failed"
    fi
fi

# Run integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    if run_tests "Integration" "tests/integration/"; then
        INTEGRATION_RESULT=0
        print_success "Integration tests passed"
    else
        INTEGRATION_RESULT=1
        print_error "Integration tests failed"
    fi
fi

# Run E2E tests
# Run each test file separately to avoid session state isolation issues
# between test files (Streamlit session state persists in browser context)
if [ "$RUN_E2E" = true ]; then
    E2E_OPTS=""
    if [ "$HEADED" = true ]; then
        E2E_OPTS="--headed"
    fi

    print_header "Running E2E Tests (per-file isolation)"

    E2E_RESULT=0
    E2E_FILES_PASSED=0
    E2E_FILES_FAILED=0

    # Get all E2E test files
    cd "$FRONTEND_DIR"

    # Files with within-file isolation issues - run by test class
    #
    # Why: Streamlit session state persists in browser between tests.
    # When tests in the same file share browser context, state from
    # earlier tests (e.g., selected_doc, editing_mode) can leak into
    # later tests, causing failures.
    #
    # Add filenames here if tests pass individually but fail in suite.
    # See: frontend/tests/e2e/conftest.py for full explanation.
    ISOLATED_FILES="test_edit_flow.py"

    for test_file in tests/e2e/test_*.py; do
        if [ -f "$test_file" ]; then
            filename=$(basename "$test_file")

            # Check if this file needs per-class isolation
            if echo "$ISOLATED_FILES" | grep -q "$filename"; then
                echo ""
                echo -e "${BLUE}Running: $filename (per-class isolation)${NC}"
                echo "────────────────────────────────────────"

                # Extract test class names and run each separately
                classes=$(grep -E "^class Test" "$test_file" | sed 's/class \(Test[^(:]*\).*/\1/')
                file_failed=0

                for class in $classes; do
                    echo ""
                    echo "  Running $class..."

                    set +e
                    pytest "$test_file::$class" $VERBOSE $E2E_OPTS $EXTRA_ARGS 2>&1 | tail -20
                    result=$?
                    set -e

                    if [ $result -ne 0 ]; then
                        file_failed=1
                    fi
                done

                if [ $file_failed -eq 0 ]; then
                    print_success "$filename passed"
                    E2E_FILES_PASSED=$((E2E_FILES_PASSED + 1))
                else
                    print_error "$filename had failures"
                    E2E_FILES_FAILED=$((E2E_FILES_FAILED + 1))
                    E2E_RESULT=1
                fi
            else
                # Run entire file as normal
                echo ""
                echo -e "${BLUE}Running: $filename${NC}"
                echo "────────────────────────────────────────"

                set +e
                pytest "$test_file" $VERBOSE $E2E_OPTS $EXTRA_ARGS
                result=$?
                set -e

                if [ $result -eq 0 ]; then
                    print_success "$filename passed"
                    E2E_FILES_PASSED=$((E2E_FILES_PASSED + 1))
                else
                    print_error "$filename failed"
                    E2E_FILES_FAILED=$((E2E_FILES_FAILED + 1))
                    E2E_RESULT=1
                fi
            fi
        fi
    done

    echo ""
    echo "E2E Summary: $E2E_FILES_PASSED file(s) passed, $E2E_FILES_FAILED file(s) failed"

    if [ $E2E_RESULT -eq 0 ]; then
        print_success "All E2E tests passed"
    else
        print_error "Some E2E tests failed"
    fi
fi

# Summary
print_header "Test Summary"

TOTAL_FAILED=0

if [ "$RUN_BACKEND" = true ]; then
    if [ $BACKEND_RESULT -eq 0 ]; then
        print_success "Backend tests:     PASSED"
    else
        print_error "Backend tests:     FAILED"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

if [ "$RUN_UNIT" = true ]; then
    if [ $UNIT_RESULT -eq 0 ]; then
        print_success "Unit tests:        PASSED"
    else
        print_error "Unit tests:        FAILED"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

if [ "$RUN_INTEGRATION" = true ]; then
    if [ $INTEGRATION_RESULT -eq 0 ]; then
        print_success "Integration tests: PASSED"
    else
        print_error "Integration tests: FAILED"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

if [ "$RUN_E2E" = true ]; then
    if [ $E2E_RESULT -eq 0 ]; then
        print_success "E2E tests:         PASSED"
    else
        print_error "E2E tests:         FAILED"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
    fi
fi

echo ""

if [ $TOTAL_FAILED -eq 0 ]; then
    print_success "All tests passed!"
    exit 0
else
    print_error "$TOTAL_FAILED test suite(s) failed"
    exit 1
fi
