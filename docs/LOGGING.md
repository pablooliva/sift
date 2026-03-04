# Logging Configuration

Persistent file-based logging is now configured for the txtai application.

## Log Files Location

Logs are accessible on the host machine at:
```
./logs/
├── frontend/
│   ├── frontend.log    # All application logs (INFO level and above)
│   └── errors.log       # Error logs only (ERROR and CRITICAL)
└── api/
    └── (txtai API logs if configured)
```

## Log File Details

### Frontend Logs (`logs/frontend/frontend.log`)
- **Level**: INFO and above (INFO, WARNING, ERROR, CRITICAL)
- **Rotation**: Automatic rotation at 10MB file size
- **Retention**: Keeps 5 backup files (total ~50MB)
- **Format**: `timestamp - logger_name - level - file:line - message`
- **Example**:
  ```
  2025-12-06 15:24:32 - utils.api_client - INFO - api_client.py:129 - Error adding documents: Connection refused
  ```

### Error Logs (`logs/frontend/errors.log`)
- **Level**: ERROR and CRITICAL only
- **Purpose**: Quick access to problems without sifting through info logs
- **Same rotation and retention as frontend.log**

## Accessing Logs

### From Host Machine
```bash
# View latest logs
tail -f logs/frontend/frontend.log

# View errors only
tail -f logs/frontend/errors.log

# Search for specific errors
grep "Connection" logs/frontend/frontend.log

# View last 100 lines
tail -100 logs/frontend/frontend.log
```

### From Docker Container
```bash
# View logs inside container
docker exec txtai-frontend cat /logs/frontend.log

# Follow logs in real-time
docker exec txtai-frontend tail -f /logs/frontend.log

# Docker's native logging (stdout/stderr) still works
docker logs txtai-frontend
docker logs -f txtai-frontend
```

## Log Levels

The application uses standard Python logging levels:
- **DEBUG**: Detailed diagnostic information (disabled by default)
- **INFO**: General informational messages
- **WARNING**: Warning messages for potentially problematic situations
- **ERROR**: Error messages for failures
- **CRITICAL**: Critical problems requiring immediate attention

### Changing Log Level

To enable DEBUG logging, set the `DEBUG` environment variable in `docker-compose.yml`:

```yaml
frontend:
  environment:
    - DEBUG=True
```

Then restart the container:
```bash
docker restart txtai-frontend
```

## RAG Workflow Logging

The RAG (Retrieval-Augmented Generation) query workflow is comprehensively logged at each step. When a user asks a question, the following information is captured:

### What Gets Logged (INFO level)

**Workflow Start:**
```
================================================================================
RAG WORKFLOW START - Question: [user's question]
================================================================================
```

**Step 1 - Document Search:**
- Search completion time
- SQL query executed
- Number of results found
- Full search results (document IDs, scores, text snippets)

**Step 2 - Context Extraction:**
- Number of documents extracted
- Source titles/filenames
- Total context length in characters

**Step 3 - Prompt Formatting:**
- Prompt length in characters

**Step 4 - LLM Generation:**
- LLM generation time

**Step 5 - Answer Delivery:**
- Generated answer (first 200 characters)
- Breakdown of timing (search vs LLM)
- Number of sources returned

**Workflow Complete:**
```
================================================================================
RAG WORKFLOW COMPLETE - Success: True, Time: 2.34s
================================================================================
```

### What Gets Logged (DEBUG level)

Enable DEBUG logging to see the full content:
- Complete context sent to LLM
- Full prompt with instructions
- Raw LLM API response

### Example RAG Log Output

```
2025-12-06 15:30:45 - utils.api_client - INFO - api_client.py:1236 - ================================================================================
2025-12-06 15:30:45 - utils.api_client - INFO - api_client.py:1237 - RAG WORKFLOW START - Question: What is txtai?
2025-12-06 15:30:45 - utils.api_client - INFO - api_client.py:1238 - ================================================================================
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1271 - STEP 1 - Search completed in 0.42s, found 5 results
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1272 - STEP 1 - SQL query: SELECT id, text, data, score FROM txtai WHERE similar('What is txtai?', 0.5) LIMIT 5
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1342 - STEP 2 - Context extraction complete: 5 documents, 5 sources
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1343 - STEP 2 - Source titles: ['README.md', 'intro.md', 'features.md', 'quickstart.md', 'api.md']
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1344 - STEP 2 - Context length: 8456 characters
2025-12-06 15:30:46 - utils.api_client - INFO - api_client.py:1365 - STEP 3 - Prompt formatted, length: 8923 characters
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1408 - STEP 4 - LLM generation completed in 1.82s
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1433 - STEP 5 - Answer generated: txtai is an all-in-one embeddings database for semantic search, LLM orchestration and language model workflows. It's built on top of sentence transformers...
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1434 - STEP 5 - Total workflow time: 2.34s (search: 0.42s, LLM: 1.82s)
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1435 - STEP 5 - Returning 5 sources
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1442 - ================================================================================
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1443 - RAG WORKFLOW COMPLETE - Success: True, Time: 2.34s
2025-12-06 15:30:48 - utils.api_client - INFO - api_client.py:1444 - ================================================================================
```

### Viewing RAG Logs

**View all RAG queries:**
```bash
# From host machine
grep "RAG WORKFLOW" logs/frontend/frontend.log

# See complete workflow for a specific question
grep -A 30 "Question: What is txtai" logs/frontend/frontend.log
```

**Monitor RAG queries in real-time:**
```bash
# Follow all logs
tail -f logs/frontend/frontend.log

# Filter for RAG-specific logs only
tail -f logs/frontend/frontend.log | grep "RAG\|STEP"
```

**View RAG timing performance:**
```bash
# Find slow queries (>5 seconds)
grep "exceeded 5s target" logs/frontend/frontend.log

# Extract all workflow times
grep "RAG WORKFLOW COMPLETE" logs/frontend/frontend.log | grep -oP "Time: \K[0-9.]+s"
```

**Debug RAG failures:**
```bash
# See all failed RAG workflows
grep "RAG WORKFLOW FAILED" logs/frontend/errors.log

# Check for specific error types
grep "Timeout\|API request error\|Unexpected error" logs/frontend/errors.log
```

### Tuning RAG Search Quality

The RAG system supports configurable search parameters via environment variables:

**`RAG_SEARCH_WEIGHTS`** (default: 0.5)
- Controls hybrid search balance between semantic and keyword matching
- `0.0` = Pure semantic search (meaning-based)
- `0.5` = Balanced (50% semantic, 50% keyword/BM25)
- `1.0` = Pure keyword search (exact term matching)
- Lower values (0.0-0.4) favor semantic understanding
- Higher values (0.6-1.0) favor exact keyword matches

**`RAG_SIMILARITY_THRESHOLD`** (default: 0.5)
- Minimum similarity score for documents to be included (0.0-1.0)
- Higher values (0.6-0.8) return only highly relevant documents
- Lower values (0.3-0.5) are more permissive
- Use higher thresholds to filter out weakly related documents

**`RAG_MAX_DOCUMENT_CHARS`** (default: 10000)
- Maximum characters per document sent to LLM
- Default 10,000 chars (~2,500 tokens) optimized for 131k context models
- With 5 docs, uses ~12,500 tokens, leaving 118k for prompts/response
- Adjust based on model context window and cost/latency preferences:
  - 5,000 = Conservative, faster, cheaper
  - 10,000 = Balanced (recommended)
  - 20,000 = More context for complex documents
  - 40,000 = Maximum detail (uses ~50k tokens for 5 docs)

**Example configuration in `.env`:**
```bash
# Favor semantic search with strict relevance filtering and full document context
RAG_SEARCH_WEIGHTS=0.3
RAG_SIMILARITY_THRESHOLD=0.7
RAG_MAX_DOCUMENT_CHARS=20000
```

After changing values, restart the frontend:
```bash
docker restart txtai-frontend
```

Check the logs to see the impact:
```bash
# View search scores and SQL query
grep "STEP 1 - Search completed" logs/frontend/frontend.log
grep "STEP 1 - SQL query" logs/frontend/frontend.log
```

### Troubleshooting "No Relevant Information Found"

If the UI shows "No relevant information found" but Docker logs show output, the issue is likely:

1. **LLM correctly identified insufficient context** - Check the logs:
   ```bash
   grep -B 10 "I don't have enough information" logs/frontend/frontend.log
   ```
   Look at the search results and source titles to see if relevant documents were retrieved.

2. **Empty search results** - Check if any documents were found:
   ```bash
   grep "STEP 1 - Search completed" logs/frontend/frontend.log
   ```
   If it shows `found 0 results`, your index may be empty or the query doesn't match indexed content.

3. **Low relevance scores** - Check document scores in the search results:
   ```bash
   grep "score" logs/frontend/frontend.log | tail -20
   ```
   If scores are below your `RAG_SIMILARITY_THRESHOLD`, increase the threshold or adjust search weights.

4. **Print statements vs. file logs** - The Docker stdout logs (`docker logs txtai-frontend`) contain `print()` debug statements. The persistent logs in `logs/frontend/frontend.log` contain the structured logging. Both should show similar information, but file logs are better organized.

## Log Rotation

Logs automatically rotate to prevent disk space issues:
- **Max file size**: 10 MB
- **Backup files**: 5 (named `frontend.log.1`, `frontend.log.2`, etc.)
- **Total storage**: ~60 MB per log type
- **Oldest logs are automatically deleted** when the 6th rotation occurs

## Troubleshooting

### No logs being generated
1. Check if the container is running:
   ```bash
   docker ps | grep txtai-frontend
   ```

2. Verify the /logs directory exists in the container:
   ```bash
   docker exec txtai-frontend ls -la /logs/
   ```

3. Check for permission issues:
   ```bash
   ls -la logs/frontend/
   ```

4. Test logging manually:
   ```bash
   docker exec txtai-frontend python -c "import logging_config; import logging; logging_config.setup_logging(); logging.info('Test message')"
   ```

### Permission denied errors
If you see permission errors, fix ownership:
```bash
sudo chown -R $USER:$USER logs/
```

### Logs not rotating
Check file size:
```bash
ls -lh logs/frontend/frontend.log
```

If it exceeds 10MB but hasn't rotated, the application might need a restart:
```bash
docker restart txtai-frontend
```

## Best Practices

1. **Monitor error logs regularly** to catch issues early:
   ```bash
   tail -f logs/frontend/errors.log
   ```

2. **Archive old logs** if needed before they're automatically rotated out:
   ```bash
   cp logs/frontend/frontend.log.5 archive/frontend_$(date +%Y%m%d).log
   ```

3. **Use log analysis tools** for better insights:
   ```bash
   # Count errors by type
   grep ERROR logs/frontend/frontend.log | cut -d'-' -f5 | sort | uniq -c

   # Find slowest operations
   grep "took" logs/frontend/frontend.log | sort -t':' -k4 -n
   ```

4. **Clean up old logs** periodically if disk space is limited:
   ```bash
   # Remove logs older than 30 days
   find logs/ -name "*.log.*" -mtime +30 -delete
   ```

## Additional Configuration

The logging configuration is defined in `frontend/logging_config.py`. You can customize:
- Log file paths
- Rotation size and count
- Log format
- Third-party library log levels

After making changes, restart the container:
```bash
docker restart txtai-frontend
```
