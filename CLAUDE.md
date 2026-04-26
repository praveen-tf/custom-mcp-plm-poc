# CLAUDE.md

## Core Principles

1. **ALWAYS PRIORITIZE READABILITY**: this is the MOST IMPORTANT PRINCIPLE and should be your absolute guiding north star, always prioritize readability even if it makes the code longer or causes some duplication. Humans need to be able to easily read and understand the code.
2. **RESEARCH FIRST**: Always read/research first, understand context fully, scrape the official website, use Context Hub, use deepwiki mcp, etc., to make sure you really understand how APIs, packages, services, etc. work and save your findings in the project_docs/ folder.
3. **FOLLOW EXISTING PATTERNS**: Don't invent new approaches
4. **SURGICAL CHANGES**: Touch only what you must.
5. **KISS**: Simplicity over complexity
6. **YAGNI**: Build only what's needed now
7. **MAX 3 LAYERS DEEP**: see [Project Architecture](#project-architecture)
8. **NO THIN WRAPPER FUNCTIONS**: DO NOT wrap a couple lines of code in a function just because it gets reused once, this makes it incredibly hard to read the code because things get masked behind these thin wrappers and the user needs to constantly hit control+F to figure out what is in the function. ALWAYS PRIORITIZE READABILITY.


## 🏛️ Guidelines

- **No Dead Code**: Delete unused functions immediately, Git has history if needed
- **Detailed Errors**: Explicit exceptions over silent failures - identify and fix issues fast
- **ALWAYS use UV for Python package and environment management.**: see `agent_docs/venv_management_uv.md` for instructions on how to use UV effectively.
- for testing guidelines, see `agent_docs/testing_guidelines.md`.
- for configuration management and data model guidelines, see `agent_docs/configs_data_models.md`.
- for logging guidelines, see `agent_docs/logging_guidelines.md`.
- for style and conventions guidelines, see `agent_docs/style_guidelines.md`.
- One `.env` file per project
- Maintain `.gitignore`, `.dockerignore` to exclude test files, deploy files, logs, .env, etc.
- README: Keep concise - Use the readme-manager subagent and follow the guidelines in `.claude/skills/readme-manager/SKILL.md`.
- Commits & PRs: use the git-agent subagent and follow the commit and PR guidelines in `.claude/skills/commits-prs/SKILL.md`.

## Spec Driven Development
- when kicking off a new project or feature, we will use plan mode to create a spec in the `specs/` folder
- review `.claude/skills/create-spec/SKILL.md` for how to write good specs and use them to drive development

## Project Docs Library
- use the `project_docs/` folder to store documentation for core APIs, packages, and services used in the project. This ensures accurate, up-to-date information is always at hand during development.
- review `.claude/skills/project-docs/SKILL.md` for guidelines on how to retrieve and summarize documentation effectively, as well as standards for maintaining the project docs library.
- use the **project-docs-researcher** subagent to research and document any external dependency — dispatch it whenever a new API, package, or service needs to be documented.
- ALWAYS review the project_docs to confirm the proper syntax for API calls, library usage, and other details when implementing features that rely on external services or packages. Do not rely on training knowledge alone for these details, as they can be easily looked up and are often updated.

### When to Create or Update the Project Docs Library
- **Before building** — search online retrieve current docs for core APIs, packages, and services and summarize relevant details
- **When you encounter unexpected behavior** — check and update docs to reflect what you learn
- **When the user asks you to correct something** — check and update docs to reflect what you learn

## Project Architecture

Follow the 3-layer architecture with tests next to the code they test (for more complex projects a subfolder structure should be used, but conceptually it should align with the below):

```
.claude/
agent_docs/            # General development guidelines (shared across projects)
specs/                 # Feature specifications (markdown, versioned)
your-project/
  main.py              # Layer 1: Entry point (CLI, app initialization)
  class_1.py           # Layer 2: Core business logic classes (if code is only used by one class, then keep it contained here)
  utils.py             # Layer 3: Helper utilities for re-use across multiple classes
  config.py            # Layer 3: Configuration and environment variables for re-use across multiple classes
  deploy.py            # Deployment script for production
  project_docs/        # Reference documentation for APIs, libraries, services
  .env                 # Environment configuration (one per project)
  spec_archive/        # Archive of completed specs
  tests/
    test_class_1.py    # Tests for Layer 2
    test_utils.py      # Tests for Layer 3
```

## Available Tools

**CLI**
- `gh` — GitHub (repos, PRs, issues, actions)
- `rg` (ripgrep) — Fast code searching
- `chub` (context-hub) — Fetch up-to-date docs for libraries and APIs; see `.claude/skills/context-hub/SKILL.md`
- `playwright-cli` — Browser automation and web dev testing (via Bash tool)
- `firecrawl` — web scraping, search, crawling, and browser automation CLI; see `.claude/skills/firecrawl-cli/SKILL.md`

**MCP**
- `Context7` — Retrieve up-to-date documentation for libraries, APIs, and services
- `deep-wiki` — Retrieve structured documentation for any GitHub repo
