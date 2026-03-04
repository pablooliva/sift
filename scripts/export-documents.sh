#!/bin/bash
#
# Export documents from txtai database
# SPEC-029 REQ-004: Export documents indexed after specific commit or date
#
# Usage:
#   ./scripts/export-documents.sh --since-commit abc1234
#   ./scripts/export-documents.sh --since-date 2026-01-15
#   ./scripts/export-documents.sh --since-date 2026-01-15 --format json
#   ./scripts/export-documents.sh --since-date 2026-01-15 --list-only
#
# Output formats:
#   jsonl (default): One document per line, streaming-friendly
#   json: Pretty-printed array of all documents
#   files: Individual .txt files + manifest.jsonl
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
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Default options
OUTPUT_DIR="$PROJECT_ROOT/exports/export_$TIMESTAMP"
FORMAT="jsonl"
LIST_ONLY=false
SINCE_COMMIT=""
SINCE_DATE=""
SINCE_EPOCH=""

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

print_info() {
    echo -e "  $1"
}

show_usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Export documents indexed after a specific commit or date.

Options:
  --since-commit HASH    Export documents indexed after this git commit
  --since-date DATE      Export documents indexed after this date (YYYY-MM-DD, UTC 00:00:00)
  --output DIR           Custom output directory (default: ./exports/export_TIMESTAMP)
  --format FORMAT        Output format: jsonl (default), json, files
  --list-only            Preview affected documents without exporting
  --help, -h             Show this help message

Examples:
  # Export documents added after commit abc1234
  $0 --since-commit abc1234

  # Export documents added after January 15, 2026 (UTC)
  $0 --since-date 2026-01-15

  # Preview what would be exported
  $0 --since-date 2026-01-15 --list-only

  # Export as JSON array instead of JSONL
  $0 --since-date 2026-01-15 --format json

  # Export as individual text files
  $0 --since-date 2026-01-15 --format files

Output:
  Creates export directory with documents in chosen format.
  All formats preserve full text content and AI-generated metadata
  (summaries, captions, transcriptions, labels).
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --since-commit)
            SINCE_COMMIT="$2"
            shift 2
            ;;
        --since-date)
            SINCE_DATE="$2"
            shift 2
            ;;
        --output|-o)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --format|-f)
            FORMAT="$2"
            shift 2
            ;;
        --list-only)
            LIST_ONLY=true
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

# Validate inputs
if [ -z "$SINCE_COMMIT" ] && [ -z "$SINCE_DATE" ]; then
    echo -e "${RED}Error: Must specify either --since-commit or --since-date${NC}"
    echo ""
    show_usage
    exit 1
fi

if [ -n "$SINCE_COMMIT" ] && [ -n "$SINCE_DATE" ]; then
    echo -e "${RED}Error: Cannot specify both --since-commit and --since-date${NC}"
    exit 1
fi

# Validate format
if [[ ! "$FORMAT" =~ ^(jsonl|json|files)$ ]]; then
    echo -e "${RED}Error: Invalid format '$FORMAT'. Must be: jsonl, json, or files${NC}"
    exit 1
fi

# Convert commit hash or date to Unix epoch timestamp
print_header "Export Configuration"

if [ -n "$SINCE_COMMIT" ]; then
    # Get commit timestamp
    if ! SINCE_EPOCH=$(git show -s --format=%ct "$SINCE_COMMIT" 2>/dev/null); then
        echo -e "${RED}Error: Invalid commit hash '$SINCE_COMMIT'${NC}"
        exit 1
    fi
    COMMIT_DATE=$(date -u -d "@$SINCE_EPOCH" '+%Y-%m-%d %H:%M:%S UTC')
    print_info "Since commit:    $SINCE_COMMIT"
    print_info "Commit date:     $COMMIT_DATE"
else
    # Convert date string to Unix epoch (UTC 00:00:00)
    if ! SINCE_EPOCH=$(date -u -d "$SINCE_DATE 00:00:00" +%s 2>/dev/null); then
        echo -e "${RED}Error: Invalid date format '$SINCE_DATE'. Use YYYY-MM-DD${NC}"
        exit 1
    fi
    print_info "Since date:      $SINCE_DATE 00:00:00 UTC"
fi

print_info "Timestamp:       $SINCE_EPOCH (Unix epoch)"
print_info "Output format:   $FORMAT"
if [ "$LIST_ONLY" = true ]; then
    print_info "Mode:            Preview only (--list-only)"
else
    print_info "Output directory: $OUTPUT_DIR"
fi

# Check if PostgreSQL container is running
print_header "Checking Database"

if ! docker ps --format '{{.Names}}' | grep -q "^txtai-postgres$"; then
    echo -e "${RED}Error: PostgreSQL container (txtai-postgres) is not running${NC}"
    echo ""
    echo "Start services with:"
    echo "  docker compose up -d"
    exit 1
fi

print_success "PostgreSQL container is running"

# Query documents from database
print_header "Querying Documents"

# Build PostgreSQL query
QUERY="
SELECT
    id,
    text,
    data
FROM txtai
WHERE (data->>'indexed_at')::numeric > $SINCE_EPOCH
ORDER BY (data->>'indexed_at')::numeric ASC;
"

# Execute query and capture output as JSON
# Use -t (no headers) and jsonb_build_object to get proper JSON
QUERY_JSON="
SELECT json_agg(
    jsonb_build_object(
        'id', id,
        'text', text,
        'data', data
    )
)::text
FROM (
    SELECT id, text, data
    FROM txtai
    WHERE (data->>'indexed_at')::numeric > $SINCE_EPOCH
    ORDER BY (data->>'indexed_at')::numeric ASC
) subq;
"

RESULT=$(docker exec txtai-postgres psql -U postgres -d txtai -t -c "$QUERY_JSON" 2>&1)

if [ $? -ne 0 ]; then
    echo -e "${RED}Error querying database:${NC}"
    echo "$RESULT"
    exit 1
fi

# Check if result is null (no documents found)
if [ "$RESULT" = " " ] || [ -z "$RESULT" ] || echo "$RESULT" | grep -q "null"; then
    echo -e "${YELLOW}No documents found matching criteria${NC}"
    print_info "0 documents indexed after timestamp $SINCE_EPOCH"
    exit 0
fi

# Parse document count
DOC_COUNT=$(echo "$RESULT" | jq '. | length' 2>/dev/null)

if [ -z "$DOC_COUNT" ] || [ "$DOC_COUNT" = "null" ]; then
    echo -e "${YELLOW}No documents found matching criteria${NC}"
    exit 0
fi

print_success "Found $DOC_COUNT document(s)"

# List-only mode: show documents and exit
if [ "$LIST_ONLY" = true ]; then
    print_header "Document Preview"

    echo "$RESULT" | jq -r '.[] | "\(.data.filename // .id) - indexed: \(.data.indexed_at)"' | while read -r line; do
        print_info "$line"
    done

    echo ""
    print_info "Total: $DOC_COUNT document(s)"
    echo ""
    echo "To export these documents, remove --list-only flag"
    exit 0
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Export documents based on format
print_header "Exporting Documents"

case $FORMAT in
    jsonl)
        # JSONL format: One JSON object per line
        OUTPUT_FILE="$OUTPUT_DIR/documents.jsonl"

        echo "$RESULT" | jq -c '.[]' > "$OUTPUT_FILE"

        SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        print_success "Exported to JSONL: $OUTPUT_FILE ($SIZE)"
        ;;

    json)
        # JSON format: Pretty-printed array
        OUTPUT_FILE="$OUTPUT_DIR/documents.json"

        echo "$RESULT" | jq '.' > "$OUTPUT_FILE"

        SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        print_success "Exported to JSON: $OUTPUT_FILE ($SIZE)"
        ;;

    files)
        # Files format: Individual .txt files + manifest.jsonl
        DOCS_DIR="$OUTPUT_DIR/documents"
        MANIFEST_FILE="$OUTPUT_DIR/manifest.jsonl"

        mkdir -p "$DOCS_DIR"

        # Export each document as individual file
        INDEX=0
        echo "$RESULT" | jq -c '.[]' | while IFS= read -r doc; do
            DOC_ID=$(echo "$doc" | jq -r '.id')
            DOC_TEXT=$(echo "$doc" | jq -r '.text')
            FILENAME=$(echo "$doc" | jq -r '.data.filename // "unknown"')

            # Sanitize filename
            SAFE_FILENAME=$(echo "$FILENAME" | tr '/' '_' | tr ' ' '_')
            FILE_PATH="$DOCS_DIR/${INDEX}_${SAFE_FILENAME}.txt"

            # Write text content to file
            echo "$DOC_TEXT" > "$FILE_PATH"

            # Write metadata to manifest
            echo "$doc" >> "$MANIFEST_FILE"

            ((INDEX++))
        done

        print_success "Exported $DOC_COUNT text files to: $DOCS_DIR/"
        print_success "Manifest: $MANIFEST_FILE"
        ;;
esac

# Create README
README_FILE="$OUTPUT_DIR/README.md"
cat > "$README_FILE" <<EOF
# Document Export

**Export Date:** $(date -u '+%Y-%m-%d %H:%M:%S UTC')
**Source:** txtai database
**Filter:** Documents indexed after timestamp $SINCE_EPOCH

EOF

if [ -n "$SINCE_COMMIT" ]; then
    echo "**Since Commit:** $SINCE_COMMIT ($COMMIT_DATE)" >> "$README_FILE"
else
    echo "**Since Date:** $SINCE_DATE 00:00:00 UTC" >> "$README_FILE"
fi

cat >> "$README_FILE" <<EOF

**Documents Exported:** $DOC_COUNT
**Format:** $FORMAT

## Import

To re-import these documents:

\`\`\`bash
./scripts/import-documents.sh $OUTPUT_DIR/documents.$FORMAT
\`\`\`

For JSONL/JSON imports, use the manifest file.
For files format, use manifest.jsonl.

## Contents

All exported documents include:
- Full text content
- All metadata (filename, categories, etc.)
- AI-generated fields (summary, auto_labels, image_caption, ocr_text, transcription)
- Original document IDs (for audit trail correlation)

EOF

print_success "Created README: $README_FILE"

# Summary
print_header "Export Complete"

echo "Summary:"
print_info "Documents exported:  $DOC_COUNT"
print_info "Output directory:    $OUTPUT_DIR"
print_info "Format:              $FORMAT"

echo ""
echo "To re-import these documents:"
if [ "$FORMAT" = "files" ]; then
    echo -e "  ${BLUE}./scripts/import-documents.sh $OUTPUT_DIR/manifest.jsonl${NC}"
else
    echo -e "  ${BLUE}./scripts/import-documents.sh $OUTPUT_DIR/documents.$FORMAT${NC}"
fi
echo ""
