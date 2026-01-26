# Claude Code Configuration

This directory contains configuration and rules for Claude Code CLI tool.

## Structure

```
.claude/
├── README.md                       # This file
├── settings.local.json             # Local permissions (gitignored)
└── rules/                          # Project-specific rules (committed to git)
    ├── enviroment.md              # Environment setup and dependencies
    ├── llm-model-for-agents.md    # AI model configuration
    ├── development-workflow.md    # Development and testing workflows
    ├── coding-standards.md        # Code style and best practices
    └── debugging.md               # Troubleshooting guide
```

## Files Purpose

### `settings.local.json`

Contains pre-approved permissions for common operations:
- Python commands (venv, pip)
- Docker commands (compose, build)
- Git operations (add, commit)
- Database queries (sqlite3)
- Web scraping tools (Playwright, Firecrawl)
- Documentation lookup (Context7)

This file is gitignored - each developer sets their own permissions.

### `rules/` Directory

Contains markdown files that guide Claude's behavior:

1. **enviroment.md** - How to set up and run the project
2. **llm-model-for-agents.md** - Which AI models to use
3. **development-workflow.md** - Step-by-step development process
4. **coding-standards.md** - Code style and architecture patterns
5. **debugging.md** - Common issues and solutions

These files ARE committed to git and shared across the team.

## Main Project Documentation

The primary project documentation is in `CLAUDE.md` at the root level, which provides:
- System architecture overview
- Microservices communication patterns
- Database schema
- Redis pub/sub channels
- Timing configuration
- Troubleshooting guides

## Usage

When working with Claude Code:

1. Claude automatically reads `CLAUDE.md` and all files in `.claude/rules/`
2. These instructions guide Claude's responses and suggestions
3. Update rules when project patterns or requirements change
4. Keep rules focused and actionable

## Best Practices

- Keep rule files concise and scannable
- Use code examples for complex patterns
- Document "why" not just "what"
- Update rules when fixing bugs or adding features
- Remove outdated guidance promptly
