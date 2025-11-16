# LLM-CONTEXT Directory

This directory contains planning documents, requirements analysis, and context information used during the development of `check_zpools`. These files are primarily for LLM-assisted development and project understanding.

## Contents

### Planning & Requirements
- **REQUIREMENTS.md** - Comprehensive functional requirements, data models, and specifications
- **IMPLEMENTATION_PLAN.md** - Detailed 10-phase implementation roadmap with tasks and estimates
- **testdata.md** - Sample ZFS JSON output for testing and development

## Purpose

These documents serve several purposes:

1. **LLM Context** - Provide rich context for AI coding assistants (Claude Code, Cursor, etc.)
2. **Project Planning** - Track implementation progress and architectural decisions
3. **Knowledge Base** - Document design rationale and implementation approach
4. **Onboarding** - Help new developers understand project structure and goals

## Usage Guidelines

### For LLM-Assisted Development
When working with an LLM assistant:
- Reference these documents to maintain consistency with the plan
- Update documents as requirements change or implementation deviates
- Use as context when asking for implementation help

### For Human Developers
- Read REQUIREMENTS.md first to understand the project goals
- Follow IMPLEMENTATION_PLAN.md phases for structured development
- Update documents when making architectural changes

## Maintenance

These documents should be:
- ✅ **Kept in sync** with actual implementation
- ✅ **Updated** when requirements change
- ✅ **Referenced** during code reviews
- ✅ **Versioned** with the codebase (committed to git)

## Document Status

| Document | Status | Last Updated | Notes |
|----------|--------|--------------|-------|
| REQUIREMENTS.md | ✅ Complete | 2025-11-16 | Initial requirements gathered |
| IMPLEMENTATION_PLAN.md | ✅ Complete | 2025-11-16 | 10-phase plan with 29 tasks |
| testdata.md | ✅ Complete | 2025-11-16 | Sample ZFS JSON for degraded pool |

## See Also

- **CLAUDE.md** - Claude Code specific development guidelines (root directory)
- **AGENTS.md** - Agent-specific development instructions (root directory)
- **DEVELOPMENT.md** - General development workflow (root directory)
- **docs/systemdesign/** - Detailed system design documentation
