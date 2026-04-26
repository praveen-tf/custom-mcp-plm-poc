# dotfiles

A foundational infrastructure repository that serves as the base environment for all coding projects. Runs in GitHub Codespaces with Claude Code as the AI-powered coding assistant at the center.

This repository provides a fully configured development environment with integrated tools, skills, and workflows for rapid project development.

## Quick Setup

```bash
# Run the installation script
bash install.sh

# Reload your shell to activate new aliases and PATH changes
source ~/.bashrc
```

The `install.sh` script installs:

- **Python & Node.js**: Python 3, pip, Node.js, npm, yarn
- **Docker & Container Tools**: Docker, docker-compose
- **CLI Tools**: GitHub CLI, ripgrep (rg), ngrok
- **Package Managers**: uv (Python), prek (pre-commit runner)
- **AI & API Tools**: Claude Code, SpecStory CLI, Context Hub (chub), Firecrawl CLI
- **Browser Automation**: Playwright CLI + Chromium headless shell
- **Python Utilities**: ipython, jupyter, ruff, ipykernel

It also sets up useful shell aliases for common commands (git, docker, uv shortcuts, etc.).

## Core Development Workflow

### 1. Start Claude with SpecStory

`install.sh` installs the [SpecStory CLI](https://specstory.com/) and sets two aliases:

```bash
cc    # runs: specstory run claude
ccc   # runs: specstory run claude -c "claude --dangerously-skip-permissions"
```

Always launch Claude via `cc` or `ccc` — SpecStory wraps Claude to automatically capture conversation history and link it to specs and commits.

### 2. Create a Spec

For any significant feature, bug fix, or refactor, generate a spec before writing code:

```
/create-spec
# Describe: Add multi-language support to content export
```

This creates a markdown file in `specs/NNN-feature-name.md` with requirements, design decisions, affected files, reference docs, an implementation checklist, and acceptance criteria. Review and approve the spec before proceeding.

### 3. Execute the Spec

Once the spec is approved, implement it end-to-end:

```
/execute-spec specs/001-feature-name.md
```

Claude reads the spec, fetches referenced docs, completes all checklist tasks in order, and creates a commit and PR when done.

### 4. Quality Checks

Before committing, run all quality gates (from inside the project directory, **not** the dotfiles root):

```bash
# Confirm you're in the right repo
git rev-parse --show-toplevel

# Tests
uv run pytest

# Format
uv run ruff format .

# Lint and auto-fix
uv run ruff check --fix .

# Pre-commit hooks (config lives one level up in dotfiles root)
uv run prek run --all-files --config ../.pre-commit-config.yaml
```

Hooks enforced by prek include: **ruff** (format + lint), **trailing-whitespace**, **end-of-file-fixer**, **check-yaml**, **detect-private-key**, and **mypy** (on pre-push).

Never use `--no-verify`. Fix the issue, re-stage, and retry.

### 5. Commit and PR

**Never commit directly to `main`.** Always work on a feature branch:

```bash
# Create branch (include Jira ticket if known)
git checkout -b feature/PROJ-123-short-description

# Stage specific files (review git status first — never blindly git add .)
git add <file>

# Commit via the git-agent slash command
/commit

# Create a draft PR
/create-pr
```

Commit messages follow conventional format: `<type>(<scope>): <subject> [PROJ-123]`
Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

See `.claude/skills/commits-prs/SKILL.md` for branch naming conventions and full workflow details.

### 6. Automated PR Review with Codex

Connect [Codex](https://codex.openai.com/) to your GitHub account and install it on all your repositories. In Codex settings, enable:

> **"All your pull requests in a Codex enabled repository will be automatically reviewed."**

Every PR you open will receive an automated review before human reviewers look at it.

---

## Core Principles

All development in projects using this infrastructure follows these 8 guiding principles:

1. **ALWAYS PRIORITIZE READABILITY** — Readability is the most important principle. Prioritize it even if code is longer or has duplication.
2. **RESEARCH FIRST** — Read/research thoroughly, scrape official documentation, use Context Hub, and save findings in `project_docs/`.
3. **FOLLOW EXISTING PATTERNS** — Don't invent new approaches; use patterns already established in the codebase.
4. **SURGICAL CHANGES** — Touch only what you must; avoid unnecessary modifications.
5. **KISS** — Keep it simple; prioritize simplicity over complexity.
6. **YAGNI** — You aren't gonna need it; build only what's required now.
7. **MAX 3 LAYERS DEEP** — Follow the 3-layer architecture pattern (see below).
8. **NO THIN WRAPPER FUNCTIONS** — Don't wrap 1-2 lines of code in functions; prioritize readability over DRY.

## Project Architecture

All projects follow a 3-layer architecture with tests co-located with code:

```
.claude/               # Cross project skills, agents, commands (e.g. the core tools defined in this repo)
agent_docs/            # General development guidelines (shared across projects)
specs/                 # Feature specifications (markdown, versioned)
your-project/
  .claude/             # optional project specific skills, agents, rules
    skills/
    agents/
    rules/
  main.py              # Layer 1: Entry point (CLI, app initialization)
  class_1.py           # Layer 2: Core business logic classes
  utils.py             # Layer 3: Helper utilities for reuse
  config.py            # Layer 3: Configuration and environment variables
  deploy.py            # Deployment script for production
  project_docs/        # Reference documentation for APIs, libraries, services
  .env                 # Environment configuration (one per project)
  spec_archive/        # Archive of completed specs
  tests/
    test_class_1.py    # Tests for Layer 2
    test_utils.py      # Tests for Layer 3
```

**Why this structure?**

- **Layer 1** keeps your entry point clean and serves as a "table of contents" for the project
- **Layer 2** contains your domain logic and core classes
- **Layer 3** provides reusable helpers and configuration
- **Tests live next to code** so it's easy to see what's tested and update tests when code changes
- **project_docs/** keeps API/library reference material centralized and up-to-date
- **specs/** creates a paper trail of what was built and why

## Skills

The repository includes reusable skills in `.claude/skills/` — each provides a structured approach to a specific development task:

### 1. **readme-manager** — Lifecycle for README files
Procedures for creating new READMEs and updating existing ones following a consistent structure (title, prerequisites, installation, usage, architecture, tech stack).

### 2. **commits-prs** — Git workflow and code review
Conventions for feature branches, conventional commit messages, pre-commit quality gates (tests, linting, formatting), and pull request creation.

### 3. **create-spec** — Feature specifications
Template and guidelines for writing specs in `specs/` folder. Specs define the "what" and "why" before implementation begins, with implementation checklists and acceptance criteria.

### 4. **project-docs** — API/library documentation management
Standards for maintaining `project_docs/` folder with curated reference documentation for external APIs, packages, and services used in projects.

### 5. **context-hub** — Fetch current API docs
Use `chub search` and `chub get` to retrieve up-to-date documentation for libraries and APIs before writing code — never rely on training data alone.

### 6. **playwright-cli** — Browser automation
Automate browser interactions for web testing, form filling, screenshots, and data extraction. Useful for testing web apps and scraping web content.

### 7. **firecrawl-cli** — Web scraping and crawling
Web scraping, search, crawling, and browser automation CLI for extracting data from websites.

## Sub-Agents

Three specialized sub-agents are available to handle focused tasks:

### git-agent
Handles commits, branches, and pull requests. Runs pre-commit quality gates, formats code with ruff, and creates PRs with conventional commit messages.

Command: `/commit` — stage changes and let the git-agent handle branching, quality checks, and committing.

### project-docs-researcher
Researches external APIs and services and documents them in `project_docs/`. Fetches current docs from official sources, summarizes key details, and maintains up-to-date reference material.

Dispatch when: Starting work on a feature that uses a new external API or package.

### readme-manager
Creates and updates README files following project conventions. Ensures READMEs stay in sync with code changes, setup requirements, and new features.

Commands: `/create-readme` — create a new README; `/update-readme` — update an existing README.

## Slash Commands

Six slash commands are available for common workflows:

### /commit
Stage your changes and commit them following the project's git conventions. The git-agent will handle branching, quality checks, and commit message formatting.

### /create-pr
Create a pull request from your feature branch. The git-agent will format the PR title, write the description, and push the branch.

### /create-readme
Create a new README.md by analyzing the project structure, dependencies, and source code. Generates documentation following the standard README structure.

### /update-readme
Update an existing README to reflect recent changes. Provide a summary of what changed, and the readme-manager will update relevant sections.

### /create-spec
Write a specification for a new feature or refactoring. Creates a markdown spec in `specs/` with requirements, design decisions, affected files, reference documents, and an implementation checklist.

### /execute-spec
Implement a spec end-to-end. Reads the spec, fetches referenced documentation, completes all checklist tasks in order, and creates a commit and PR when complete.

```bash
/execute-spec specs/001-feature-name.md
```

## Key Workflows

### Project Docs Library

Maintain `project_docs/` inside each project (`<project>/src/project_docs/`) as a curated library of reference documentation:

1. **Before building** — Research external APIs/packages and save docs to `project_docs/`
2. **While building** — Reference `project_docs/` instead of relying on training data
3. **When encountering issues** — Update docs to reflect what you learned
4. **Dispatching researchers** — Use the **project-docs-researcher** agent to fetch and document new dependencies

Docs follow a standard format (source URL, retrieval date, overview, setup, key concepts, usage patterns, configuration, error handling, gotchas).

Read `.claude/skills/project-docs/SKILL.md` for the full standard.

## Agent Docs

General development guidelines are stored in `agent_docs/` and shared across all projects:

- **venv_management_uv.md** — How to use `uv` for Python package and environment management
- **testing_guidelines.md** — Test-driven development conventions and pytest patterns
- **logging_guidelines.md** — When and how to log; log levels and formatting
- **style_guidelines.md** — Code style, naming conventions, formatting standards
- **configs_data_models.md** — Managing configuration and data models
- **create_new_repo.md** — Onboarding a new project repository

## Dev Container

The GitHub Codespace is configured via `.devcontainer/devcontainer.json`:

- **Base image**: Ubuntu with Docker support
- **Dockerfile**: Custom build in `.devcontainer/Dockerfile`
- **Permissions**: Write access to all repositories under `jesse-miller-thoughtfully/*` (update accordingly)
- **Startup**: Runs `install.sh` automatically

The dev container provides a fully configured environment — no additional setup required when spinning up a new Codespace.
```

To access repositories where you're a collaborator but not an owner:
```bash
unset GITHUB_TOKEN
gh auth login -h github.com -p https --web -s repo
```

## MCP Servers

The `.mcp.json` file configures Model Context Protocol (MCP) servers for enhanced capabilities:

- **deep-wiki** — Structured documentation for any GitHub repository (read repo structure, docs, ask questions)
- **Context7** — Retrieve up-to-date documentation for libraries, APIs, and services
- **Excalidraw** — Create and edit diagrams collaboratively

These integrations are available to Claude Code and provide specialized tools for research, documentation, and project management.
