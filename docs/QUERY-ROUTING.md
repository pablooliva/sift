[← Back to README](../README.md)

# Intelligent Query Routing (RAG)

The `/ask` command provides automatic routing between fast RAG answers and deep manual analysis, selecting the best approach based on query complexity.

## Overview

The `/ask` command provides intelligent query routing with automatic decision-making:
- **Fast RAG answers** (~7s) for simple factual queries
- **Deep manual analysis** (~30-60s) for complex tasks requiring reasoning
- **Automatic fallback** if RAG fails or quality is insufficient

## How It Works

```
User Query → Pattern Analysis → Route Decision
                                      ↓
                        ┌─────────────┴─────────────┐
                        ↓                           ↓
                   Simple Query              Complex Query
                        ↓                           ↓
                  RAG Workflow               Manual Analysis
                   (~7s fast)                 (~30-60s thorough)
                        ↓                           ↓
                 Quality Check ──(fails)────────────┘
                        ↓
                   User Answer
```

## Query Routing Logic

**Simple queries routed to RAG:**
- Factual questions: "What documents mention X?"
- Information retrieval: "Find documents about Y"
- Definition lookups: "What is Z in the documents?"
- Direct questions with clear answers

**Complex queries routed to manual analysis:**
- Multi-step reasoning: "Compare A and B, then suggest C"
- Analytical tasks: "Analyze the architecture"
- Tasks requiring tools: "Search for X, read Y, then summarize Z"
- Ambiguous queries: "Help me with the documents"

**Conservative routing:** When uncertain, prefer manual analysis (quality > speed)

## RAG Workflow Details

**Architecture:**
1. **Retrieval**: Top-5 most relevant documents via txtai semantic search (~0.03s)
2. **Generation**: Together AI Qwen2.5-72B generates answer from context (~7s)
3. **Validation**: Quality checks ensure answer is grounded in documents
4. **Fallback**: Automatic switch to manual if RAG fails or quality insufficient

**Anti-Hallucination Measures:**
- Conservative prompt: "Use ONLY provided context"
- Explicit "I don't know" instructions for unanswerable queries
- Temperature 0.3 for factual accuracy (not creative generation)
- Quality validation checks before returning answer

## Fallback Mechanisms

RAG automatically falls back to manual analysis when:

1. **Timeout** (>30s): "⚠️ RAG query timed out. Switching to detailed analysis..."
2. **API Error**: "⚠️ RAG service unavailable. Using manual document analysis..."
3. **Low Quality**: "⚠️ RAG provided insufficient information. Analyzing documents in detail..."
4. **No Documents**: Reports finding gracefully, no fallback needed

**User always knows which approach is used** via transparent communication messages.

## Usage Examples

**Example 1: Simple Factual Query (RAG)**
```bash
/ask What documents mention txtai?

# Response in ~7s:
# 🚀 Using RAG for quick answer...
#
# Based on your documents, txtai is mentioned in:
# 1. README.md - Setup and configuration guide
# 2. config.yml - Model configurations
# 3. RESEARCH-013 - Model upgrade analysis
```

**Example 2: Complex Analytical Query (Manual)**
```bash
/ask Analyze the architecture patterns in the codebase and suggest improvements

# Response in ~30-60s:
# 🔍 Analyzing documents thoroughly...
#
# [Claude Code performs deep analysis with file reading, pattern recognition, reasoning]
#
# Architecture Analysis:
# 1. Current Patterns: [detailed analysis]
# 2. Strengths: [reasoning]
# 3. Improvement Suggestions: [specific recommendations]
```

**Example 3: RAG Fallback (Automatic)**
```bash
/ask What is the meaning of life according to my documents?

# RAG attempts, finds no relevant information:
# ⚠️ RAG provided insufficient information. Analyzing documents in detail...
#
# [Switches to manual analysis]
#
# I searched your documents but didn't find any discussions about the meaning of life.
# Your documents focus on: [list of actual topics found]
```

## Performance Characteristics

| Metric | RAG Workflow | Manual Analysis |
|--------|--------------|-----------------|
| **Response Time** | ~7s average | 30-60s typical |
| **Best For** | Factual queries | Complex reasoning |
| **Quality** | Good for simple Q&A | Excellent for analysis |
| **Cost** | ~$0.0006 per query | Free (local) |
| **Accuracy** | 90%+ for factoid questions | 95%+ for all tasks |
| **Fallback** | Automatic to manual | N/A |

## Configuration

**RAG is enabled by default** via the `/ask` command. No additional configuration needed.

**To disable RAG routing:**
```bash
# Simply remove or rename the slash command
rm .claude/commands/ask.md
```

**To adjust routing behavior:**
Edit `.claude/commands/ask.md` and modify the routing patterns.

## Monitoring (Optional)

Server-side monitoring tools are available (see `frontend/utils/monitoring.py`):
- Track RAG vs manual query distribution
- Monitor response times and success rates
- Identify fallback patterns

```bash
# Run analytics dashboard (server-side only)
python scripts/monitoring_dashboard.py --days 7
```

## Troubleshooting

**"RAG query timed out" frequently:**
- Together AI API may be experiencing high latency
- Check API status at [status.together.ai](https://status.together.ai)
- Queries automatically fall back to manual analysis

**"RAG service unavailable":**
- Check Together AI API key is configured in `.env`
- Verify `TOGETHER_API_KEY` environment variable
- Restart Docker containers: `docker-compose restart`

**Poor RAG answer quality:**
- RAG works best for factual, straightforward questions
- Complex queries should auto-route to manual (check routing logic)
- If RAG is selected but quality is poor, it should auto-fallback
