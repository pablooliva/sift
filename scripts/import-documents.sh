#!/bin/bash
#
# Import documents to txtai database
# SPEC-029 REQ-005: Batch re-import documents from export
#
# Usage:
#   ./scripts/import-documents.sh documents.jsonl
#   ./scripts/import-documents.sh documents.jsonl --skip-duplicates
#   ./scripts/import-documents.sh documents.jsonl --new-ids
#   ./scripts/import-documents.sh documents.json
#
# Features:
#   - Preserves all metadata (no AI re-processing)
#   - Duplicate detection with --skip-duplicates
#   - ID preservation (default) or new UUID generation (--new-ids)
#   - Failure threshold: aborts if >50% documents fail
#
# Limitations:
#   - Does NOT populate the Graphiti knowledge graph (QA-002)
#     Only the frontend upload workflow triggers Graphiti ingestion.
#     Documents imported via this script will be searchable (vector + keyword)
#     but will not appear in the knowledge graph or have relationships extracted.
#     To add knowledge graph coverage, re-ingest documents through the frontend.
#

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

# Default options
SKIP_DUPLICATES=false
PRESERVE_IDS=true  # Default: preserve original IDs
DRY_RUN=false
INPUT_FILE=""
API_URL="${TXTAI_API_URL:-http://localhost:8300}"

# Helper functions
print_header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""
}

print_success() {
    local prefix=""
    [ "$DRY_RUN" = true ] && prefix="[DRY RUN] "
    echo -e "${GREEN}✓ ${prefix}$1${NC}"
}

print_warning() {
    local prefix=""
    [ "$DRY_RUN" = true ] && prefix="[DRY RUN] "
    echo -e "${YELLOW}⚠ ${prefix}$1${NC}"
}

print_error() {
    local prefix=""
    [ "$DRY_RUN" = true ] && prefix="[DRY RUN] "
    echo -e "${RED}✗ ${prefix}$1${NC}"
}

print_info() {
    local prefix=""
    [ "$DRY_RUN" = true ] && prefix="[DRY RUN] "
    echo -e "  ${prefix}$1"
}

# Calculate ETA and format as human-readable string
calculate_eta() {
    local current_doc=$1
    local total_docs=$2
    local start_time=$3

    if [ "$current_doc" -eq 0 ]; then
        echo "calculating..."
        return
    fi

    local elapsed=$(($(date +%s) - start_time))
    if [ "$elapsed" -eq 0 ]; then
        echo "calculating..."
        return
    fi

    local docs_per_sec=$(awk "BEGIN {printf \"%.4f\", $current_doc / $elapsed}")
    local remaining=$(($total_docs - $current_doc))
    local eta_seconds=$(awk "BEGIN {printf \"%.0f\", $remaining / $docs_per_sec}")

    # Format as Xm Ys or Xs
    if [ "$eta_seconds" -ge 60 ]; then
        local minutes=$((eta_seconds / 60))
        local seconds=$((eta_seconds % 60))
        echo "${minutes}m ${seconds}s"
    else
        echo "${eta_seconds}s"
    fi
}

# Show enhanced progress with percentage and ETA
show_progress() {
    local current=$1
    local total=$2
    local doc_title=$3
    local start_time=$4

    local percentage=$((current * 100 / total))
    local eta=$(calculate_eta "$current" "$total" "$start_time")

    # Truncate title if too long
    local display_title="$doc_title"
    if [ ${#display_title} -gt 50 ]; then
        display_title="${display_title:0:47}..."
    fi

    print_info "Processing document $current/$total ($percentage%) - \"$display_title\" - ETA: $eta"
}

show_usage() {
    cat <<EOF
Usage: $0 FILE [OPTIONS]

Import documents from export file (JSONL or JSON format).

Arguments:
  FILE                   Path to export file (documents.jsonl or documents.json)

Options:
  --skip-duplicates      Skip documents with duplicate content_hash
  --new-ids              Generate new UUIDs instead of preserving original IDs
  --preserve-ids         Preserve original IDs (default)
  --dry-run              Preview import without modifying data
  --help, -h             Show this help message

Environment Variables:
  TXTAI_API_URL          txtai API endpoint (default: http://localhost:8300)

Examples:
  # Import with default settings (preserve IDs, allow duplicates)
  $0 exports/export_*/documents.jsonl

  # Skip documents that already exist (based on content_hash)
  $0 exports/export_*/documents.jsonl --skip-duplicates

  # Generate new IDs (avoid conflicts with existing documents)
  $0 exports/export_*/documents.jsonl --new-ids

Features:
  - Batch API calls for efficiency
  - Preserves all metadata (summary, captions, transcriptions)
  - Progress reporting
  - Aborts if >50% of documents fail (safety threshold)
EOF
}

# Parse arguments
if [ $# -eq 0 ]; then
    show_usage
    exit 1
fi

INPUT_FILE="$1"
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-duplicates)
            SKIP_DUPLICATES=true
            shift
            ;;
        --new-ids)
            PRESERVE_IDS=false
            shift
            ;;
        --preserve-ids)
            PRESERVE_IDS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --help|-h)
            show_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate input file
if [ ! -f "$INPUT_FILE" ]; then
    echo -e "${RED}Error: File not found: $INPUT_FILE${NC}"
    exit 1
fi

# Detect file format
if [[ "$INPUT_FILE" == *.jsonl ]]; then
    FORMAT="jsonl"
elif [[ "$INPUT_FILE" == *.json ]]; then
    FORMAT="json"
else
    echo -e "${RED}Error: Unsupported file format. Use .jsonl or .json${NC}"
    exit 1
fi

# Configuration summary
print_header "Import Configuration"

print_info "Input file:        $INPUT_FILE"
print_info "Format:            $FORMAT"
print_info "API endpoint:      $API_URL"
print_info "Preserve IDs:      $([ "$PRESERVE_IDS" = true ] && echo "Yes" || echo "No (generate new)")"
print_info "Skip duplicates:   $([ "$SKIP_DUPLICATES" = true ] && echo "Yes" || echo "No")"
print_info "Mode:              $([ "$DRY_RUN" = true ] && echo "DRY RUN (preview only)" || echo "Live import")"

# Check API connectivity
print_header "Checking API"

if ! curl -s "$API_URL" > /dev/null 2>&1; then
    echo -e "${RED}Error: Cannot connect to txtai API at $API_URL${NC}"
    echo ""
    echo "Make sure services are running:"
    echo "  docker compose up -d"
    echo ""
    echo "Or set TXTAI_API_URL environment variable:"
    echo "  export TXTAI_API_URL=http://your-server:8300"
    exit 1
fi

print_success "API is accessible"

# Load documents from file
print_header "Loading Documents"

if [ "$FORMAT" = "jsonl" ]; then
    # JSONL: Count lines
    TOTAL_DOCS=$(wc -l < "$INPUT_FILE")
    print_success "Loaded $TOTAL_DOCS document(s) from JSONL"
else
    # JSON: Parse array length
    TOTAL_DOCS=$(jq '. | length' "$INPUT_FILE")
    print_success "Loaded $TOTAL_DOCS document(s) from JSON"
fi

if [ "$TOTAL_DOCS" -eq 0 ]; then
    echo -e "${YELLOW}No documents to import${NC}"
    exit 0
fi

# Get existing content hashes if skip-duplicates is enabled
EXISTING_HASHES=""
if [ "$SKIP_DUPLICATES" = true ]; then
    print_header "Checking for Duplicates"

    # Query all existing content hashes from database
    # Note: This requires PostgreSQL access
    if docker ps --format '{{.Names}}' | grep -q "^txtai-postgres$"; then
        EXISTING_HASHES=$(docker exec txtai-postgres psql -U postgres -d txtai -t -c "
            SELECT DISTINCT data->>'content_hash'
            FROM txtai
            WHERE data->>'content_hash' IS NOT NULL;
        " 2>/dev/null | tr -d ' ')

        HASH_COUNT=$(echo "$EXISTING_HASHES" | grep -v '^$' | wc -l)
        print_success "Loaded $HASH_COUNT existing content hash(es)"
    else
        print_warning "PostgreSQL not running, cannot check for duplicates"
        SKIP_DUPLICATES=false
    fi
fi

# Import documents
print_header "Importing Documents"

SUCCESS_COUNT=0
FAILURE_COUNT=0
SKIPPED_COUNT=0
FAILED_DOCS=()
IMPORTED_IDS=()

# Temporary file for batch processing
TEMP_BATCH=$(mktemp)
trap "rm -f $TEMP_BATCH" EXIT

# Process each document
DOC_INDEX=0
START_TIME=$(date +%s)

# Calculate update frequency based on document count
if [ "$TOTAL_DOCS" -ge 100 ]; then
    # Update every 1% for large batches
    UPDATE_FREQUENCY=$((TOTAL_DOCS / 100))
    [ "$UPDATE_FREQUENCY" -lt 1 ] && UPDATE_FREQUENCY=1
else
    # Update every document for small batches
    UPDATE_FREQUENCY=1
fi

process_document() {
    local doc="$1"
    local index="$2"

    # Validate JSON structure
    if ! echo "$doc" | jq '.' > /dev/null 2>&1; then
        print_error "Invalid JSON at document $index"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_DOCS+=("Document $index: Invalid JSON")
        return 1
    fi

    # Extract fields
    DOC_ID=$(echo "$doc" | jq -r '.id')
    DOC_TEXT=$(echo "$doc" | jq -r '.text')
    DOC_DATA=$(echo "$doc" | jq -c '.data')
    DOC_TITLE=$(echo "$doc" | jq -r '.data.title // .id')

    # Validate required fields (REQ-004)
    if [ "$DOC_ID" = "null" ] || [ -z "$DOC_ID" ]; then
        print_error "Document missing required field 'id' at document $index"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_DOCS+=("Document $index: Missing 'id' field")
        return 1
    fi

    if [ "$DOC_TEXT" = "null" ] || [ -z "$DOC_TEXT" ]; then
        print_error "Document missing required field 'text' at document $index"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_DOCS+=("Document $index: Missing 'text' field")
        return 1
    fi

    # Validate field types
    if ! echo "$doc" | jq -e '.id | type == "string"' > /dev/null 2>&1; then
        print_error "Document field 'id' must be string at document $index (got $(echo "$doc" | jq -r '.id | type'))"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_DOCS+=("Document $index: 'id' must be string")
        return 1
    fi

    if ! echo "$doc" | jq -e '.text | type == "string"' > /dev/null 2>&1; then
        print_error "Document field 'text' must be string at document $index (got $(echo "$doc" | jq -r '.text | type'))"
        FAILURE_COUNT=$((FAILURE_COUNT + 1))
        FAILED_DOCS+=("Document $index: 'text' must be string")
        return 1
    fi

    # Check for duplicate
    if [ "$SKIP_DUPLICATES" = true ]; then
        CONTENT_HASH=$(echo "$doc" | jq -r '.data.content_hash // empty')

        if [ -n "$CONTENT_HASH" ]; then
            if echo "$EXISTING_HASHES" | grep -q "^$CONTENT_HASH$"; then
                print_warning "Skipping duplicate: $DOC_ID (hash: ${CONTENT_HASH:0:8}...)"
                SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
                return 0
            fi
        fi
    fi

    # Generate new ID if requested
    if [ "$PRESERVE_IDS" = false ]; then
        DOC_ID=$(uuidgen)
    fi

    # Build document for API
    # Merge 'data' fields into root level for txtai API
    DOC_PAYLOAD=$(echo "$DOC_DATA" | jq -c ". + {id: \"$DOC_ID\", text: $(echo "$DOC_TEXT" | jq -R .)}")

    if [ "$DRY_RUN" = true ]; then
        # Dry-run mode: Skip write operations, just report what would be done
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
        IMPORTED_IDS+=("$DOC_ID")

        # Enhanced progress reporting
        if [ $((SUCCESS_COUNT % UPDATE_FREQUENCY)) -eq 0 ] || [ "$SUCCESS_COUNT" -eq "$TOTAL_DOCS" ]; then
            show_progress "$SUCCESS_COUNT" "$TOTAL_DOCS" "$DOC_TITLE" "$START_TIME"
        fi
    else
        # Normal mode: Perform write operations
        # DELETE before ADD to prevent orphaned chunks (BUG-003 fix)
        # Uses POST with JSON array of IDs (txtai API format)
        DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/delete" \
            -H "Content-Type: application/json" \
            -d "[\"$DOC_ID\"]" 2>&1)
        DELETE_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)

        # Log DELETE failures as warnings only (best-effort cleanup)
        if [ "$DELETE_CODE" != "200" ]; then
            # Silently continue - delete is optional cleanup
            # Frontend treats deletion as best-effort, we do the same
            :
        fi

        # Send to API (individual calls for better error tracking)
        RESPONSE=$(curl -s -X POST "$API_URL/add" \
            -H "Content-Type: application/json" \
            -d "[$DOC_PAYLOAD]" 2>&1)

        # Check response
        if echo "$RESPONSE" | jq -e '. == true or . == null or type == "object"' > /dev/null 2>&1; then
            SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
            IMPORTED_IDS+=("$DOC_ID")

            # Enhanced progress reporting
            if [ $((SUCCESS_COUNT % UPDATE_FREQUENCY)) -eq 0 ] || [ "$SUCCESS_COUNT" -eq "$TOTAL_DOCS" ]; then
                show_progress "$SUCCESS_COUNT" "$TOTAL_DOCS" "$DOC_TITLE" "$START_TIME"
            fi
        else
            FAILURE_COUNT=$((FAILURE_COUNT + 1))
            FAILED_DOCS+=("$DOC_ID: $RESPONSE")
            print_error "Failed: $DOC_ID"
        fi
    fi
}

# Process documents based on format
if [ "$FORMAT" = "jsonl" ]; then
    # JSONL: Process line by line with size check
    LINE_NUM=0
    while IFS= read -r line; do
        LINE_NUM=$((LINE_NUM + 1))
        DOC_INDEX=$((DOC_INDEX + 1))

        # Check line length (REQ-004: 10MB limit)
        LINE_SIZE=${#line}
        MAX_LINE_SIZE=$((10 * 1024 * 1024))  # 10MB in bytes

        if [ "$LINE_SIZE" -gt "$MAX_LINE_SIZE" ]; then
            print_error "JSONL line exceeds 10MB limit at line $LINE_NUM (size: $((LINE_SIZE / 1024 / 1024))MB). Use JSON array format for large documents."
            FAILURE_COUNT=$((FAILURE_COUNT + 1))
            FAILED_DOCS+=("Line $LINE_NUM: Oversized ($((LINE_SIZE / 1024 / 1024))MB)")
            continue
        fi

        process_document "$line" "$DOC_INDEX" || true  # Don't exit on validation failure
    done < "$INPUT_FILE"
else
    # JSON: Process array elements
    # Use process substitution to avoid subshell (preserves variable scope)
    while IFS= read -r doc; do
        DOC_INDEX=$((DOC_INDEX + 1))
        process_document "$doc" "$DOC_INDEX" || true  # Don't exit on validation failure
    done < <(jq -c '.[]' "$INPUT_FILE")
fi

# Check failure threshold (SPEC-029 REQ-005)
TOTAL_PROCESSED=$((SUCCESS_COUNT + FAILURE_COUNT))
if [ $TOTAL_PROCESSED -gt 0 ]; then
    FAILURE_RATE=$(awk "BEGIN {printf \"%.2f\", ($FAILURE_COUNT / $TOTAL_PROCESSED) * 100}")

    if (( $(echo "$FAILURE_COUNT / $TOTAL_PROCESSED > 0.5" | bc -l) )); then
        print_header "Import Failed"

        print_error "ABORT: Import failed - $FAILURE_COUNT/$TOTAL_PROCESSED documents failed ($FAILURE_RATE%)"
        echo ""
        echo "Failure threshold exceeded (>50%). This may indicate:"
        echo "  - API connectivity issues"
        echo "  - Invalid document format"
        echo "  - Database errors"
        echo ""
        echo "Failed documents:"
        for failed in "${FAILED_DOCS[@]}"; do
            echo "  - $failed"
        done

        exit 1
    fi
fi

if [ "$DRY_RUN" = false ]; then
    # Trigger index upsert (skip in dry-run mode)
    print_header "Finalizing Import"

    print_info "Upserting index..."
    UPSERT_RESPONSE=$(curl -s -w "\n%{http_code}" "$API_URL/upsert" 2>&1)

    # Extract HTTP status code from response
    HTTP_CODE=$(echo "$UPSERT_RESPONSE" | tail -n1)
    UPSERT_BODY=$(echo "$UPSERT_RESPONSE" | sed '$d')

    if [ "$HTTP_CODE" = "200" ]; then
        # Verify response is valid JSON (null is acceptable)
        if echo "$UPSERT_BODY" | jq '.' > /dev/null 2>&1; then
            print_success "Index upserted successfully"
        else
            print_error "Upsert returned HTTP 200 but invalid JSON: $UPSERT_BODY"
            exit 1
        fi
    else
        print_error "Upsert failed (HTTP $HTTP_CODE): $UPSERT_BODY"
        echo ""
        echo "The import added documents to the database, but indexing failed."
        echo "Documents will NOT be searchable until the index is rebuilt."
        echo ""
        echo "To retry indexing:"
        echo "  curl $API_URL/upsert"
        exit 1
    fi

    # Write audit log (skip in dry-run mode)
    if [ ${#IMPORTED_IDS[@]} -gt 0 ]; then
        print_info "Writing audit log..."

        # Write document IDs to temp file (avoids ARG_MAX limit)
        DOC_IDS_FILE=$(mktemp)
        for id in "${IMPORTED_IDS[@]}"; do
            echo "$id" >> "$DOC_IDS_FILE"
        done

        # Call Python helper to write audit log
        if python3 "$SCRIPT_DIR/audit-import.py" "$INPUT_FILE" "$SUCCESS_COUNT" "$FAILURE_COUNT" "$DOC_IDS_FILE" 2>/dev/null; then
            print_success "Audit log written"
        else
            print_warning "Failed to write audit log (non-fatal)"
        fi

        # Cleanup temp file
        rm -f "$DOC_IDS_FILE"
    fi
fi

# Summary
if [ "$DRY_RUN" = true ]; then
    print_header "Dry-Run Complete"
else
    print_header "Import Complete"
fi

if [ "$DRY_RUN" = true ]; then
    echo "Summary (preview only - no changes made):"
    TOTAL_WOULD_IMPORT=$((SUCCESS_COUNT - SKIPPED_COUNT))
    print_success "Would import: $TOTAL_WOULD_IMPORT new document(s)"

    if [ $SKIPPED_COUNT -gt 0 ]; then
        print_warning "Would skip:   $SKIPPED_COUNT duplicate(s)"
    fi

    echo ""
    echo "Total: $SUCCESS_COUNT document(s) (${TOTAL_WOULD_IMPORT} new, ${SKIPPED_COUNT} duplicates)"
    echo ""
    echo -e "${BLUE}[DRY RUN] No changes were made. Run without --dry-run to perform actual import.${NC}"
else
    echo "Summary:"
    print_success "Successful:  $SUCCESS_COUNT document(s)"

    if [ $FAILURE_COUNT -gt 0 ]; then
        print_error "Failed:      $FAILURE_COUNT document(s)"

        echo ""
        echo "Failed documents:"
        for failed in "${FAILED_DOCS[@]}"; do
            echo "  - $failed"
        done
    fi

    if [ $SKIPPED_COUNT -gt 0 ]; then
        print_warning "Skipped:     $SKIPPED_COUNT duplicate(s)"
    fi

    echo ""
    echo "Total processed: $TOTAL_PROCESSED document(s)"

    if [ $FAILURE_COUNT -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✓ All documents imported successfully!${NC}"
    else
        echo ""
        print_warning "Some documents failed to import. Review errors above."
    fi
fi

echo ""
