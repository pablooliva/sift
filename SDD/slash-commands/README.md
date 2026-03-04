# Claude Code Slash Commands Archive

This directory contains archived copies of Claude Code slash commands created for this project.

## Purpose

These slash command files are archived here for:
- **Documentation**: Understanding how features are implemented
- **Version control**: Tracking changes to command behavior over time
- **Portability**: Easily sharing commands across team members or projects
- **Reference**: Understanding implementation patterns for future commands

## Active vs Archived

- **Active commands**: Located in `.claude/commands/` (user's home directory)
- **Archived commands**: Located here in `SDD/slash-commands/` (project directory)

To use an archived command, copy it to your `.claude/commands/` directory:

```bash
cp SDD/slash-commands/ask.md ~/.claude/commands/ask.md
```

## Available Commands

### `/ask` - Intelligent Document Query with RAG

**File**: `ask.md`
**Created**: 2025-12-05
**SPEC**: SPEC-013 Phase 3 - Hybrid Architecture
**Purpose**: Query documents using intelligent routing between fast RAG and thorough manual analysis

**Key Features**:
- Automatic routing: simple queries → RAG (~7s), complex → manual analysis
- Transparent communication about approach used
- Quality validation with fallback mechanisms
- Conservative decision-making (quality over speed)

**Usage**:
```
/ask <your question>
```

**Examples**:
- `/ask What financial documents do I have?` - Routes to RAG
- `/ask Analyze budget trends and recommend improvements` - Routes to manual

**Requirements**:
- txtai API running at localhost:8300
- Together AI API key configured (TOGETHERAI_API_KEY)
- Documents indexed in the system

**Testing**: See `test_phase3_routing.py` for routing logic tests

---

## Command Development Guidelines

When creating new slash commands for this project:

1. **Document thoroughly**: Include usage examples, requirements, and behavior
2. **Test comprehensively**: Create test files like `test_phase3_routing.py`
3. **Archive in project**: Copy to `SDD/slash-commands/` for version control
4. **Reference specs**: Link to relevant SPEC and RESEARCH documents
5. **Include metadata**: Creation date, SPEC reference, purpose

## Related Documentation

- **SPEC-013**: `SDD/requirements/SPEC-013-model-upgrades-rag.md`
- **RESEARCH-013**: `SDD/research/RESEARCH-013-model-upgrades-rag.md`
- **Phase 3 Completion**: `PHASE3_COMPLETION_SPEC013.md`
- **Routing Tests**: `test_phase3_routing.py`
- **Implementation Tracking**: `SDD/prompts/PROMPT-013-model-upgrades-rag-2025-12-03.md`

## Version History

### ask.md

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-12-05 | Initial implementation (SPEC-013 Phase 3) |
| 1.1 | 2025-12-05 | Added ambiguous pattern detection for improved routing |

---

**Note**: Always test slash commands in a development environment before deploying to production workflows.
