# Bub - Bub it. Build it.

[![Release](https://img.shields.io/github/v/release/psiace/bub)](https://github.com/psiace/bub/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/psiace/bub/main.yml?branch=main)](https://github.com/psiace/bub/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/psiace/bub)](https://github.com/psiace/bub/graphs/commit-activity)
[![License](https://img.shields.io/github/license/psiace/bub)](LICENSE)

Bub is an AI-powered CLI tool that helps you build, develop, and manage projects using natural language commands. With access to file operations, command execution, and intelligent reasoning, Bub acts as your coding assistant.

## Installation

```bash
# Install from PyPI (when available)
pip install bub

# Or install from source
git clone https://github.com/psiace/bub.git
cd bub
uv sync
uv run bub --help
```

## Quick Start

### 1. Set up your API key

Bub supports multiple AI providers through Republic. Configure your model (provider:model):

```bash
# For OpenAI
export BUB_MODEL="openai:gpt-4"
export BUB_API_KEY="sk-..."

# For Anthropic
export BUB_MODEL="anthropic:claude-3-sonnet-20240229"
export BUB_API_KEY="your-anthropic-key"
```

### 2. Start using Bub

```bash
# Interactive chat mode
bub chat

# Specify workspace and model
bub chat --workspace /path/to/project --model openai:gpt-4

# Get help
bub --help
```

## Usage Examples

```bash
# Start a session
bub chat

# Then, inside the session:
$tape.info
summarize $tape.search query=TODO
$handoff summary="Pause work" next_steps="Resume tests"
```

## Unified Input

Bub treats `$` as a command intent marker. Commands and natural language share the same input line.

```bash
# Internal commands
$tape.info
$tape.search query=handoff
$handoff name=handoff/2026-02-05 summary="Reset scope"

# Shell commands
$git status
$ rg "TODO" src

# Mixed input (command output feeds the model)
summarize $tape.anchors --limit 3
```

Notes:
- `$` is only an intent marker. If a command is ambiguous or fails, Bub falls back to the agent when there is other text.
- When a line contains only a command, Bub executes it and returns the result without invoking the agent.
- Tapes are persisted in `~/.bub/tapes/<workspace_hash>.jsonl` (override with `BUB_HOME`).
- File tools use the `fs.*` prefix to avoid shell conflicts. Tool names still take precedence; use `$bash <command>` for explicit shell behavior.

## Configuration

Bub can be configured via environment variables or a `.env` file:

```bash
BUB_API_KEY=your-api-key-here
BUB_MODEL=openai:gpt-4             # AI model to use (provider:model)
BUB_API_BASE=https://api.custom.ai # Custom API endpoint
BUB_MAX_TOKENS=4000               # Maximum response tokens
BUB_WORKSPACE_PATH=/path/to/work  # Default workspace
BUB_SYSTEM_PROMPT="custom prompt" # Custom system prompt
BUB_HOME=/path/to/bub/home        # Bub home (default: ~/.bub)
```

### Custom System Prompt with AGENTS.md

You can customize Bub's behavior by creating an `AGENTS.md` file in your workspace. This file will be automatically read and used as the system prompt, allowing you to define project-specific instructions, coding standards, and behavior guidelines.

**Example AGENTS.md:**

```markdown
# Project Assistant

You are a Python development assistant for this specific project.

## Guidelines
- Follow PEP 8 style guidelines
- Use type hints for all functions
- Write comprehensive tests with pytest
- Focus on security and performance

## Project Structure
- `/src` - Main source code
- `/tests` - Test files
- `/docs` - Documentation

When making changes, always run tests first.
```

The AGENTS.md file takes precedence over the `BUB_SYSTEM_PROMPT` environment variable, making it easy to share consistent AI behavior across your development team.

### Reusable Skills

Bub can discover reusable skills from both project and global locations:

- `<workspace>/.agent/skills`
- `~/.agent/skills`
- Built-in package skills under `src/bub/skills`

Each skill should be stored in its own directory with a `SKILL.md` file. Bub reads skill metadata from frontmatter and injects an `<available_skills>` block into the system prompt, so the agent can load matching skills on demand.

When skill names conflict, precedence is: project > global > built-in.

## Development

```bash
# Clone the repository
git clone https://github.com/psiace/bub.git
cd bub

# Install dependencies
uv sync --dev

# Run tests
just test

# Run linting and type checking
just check

# Build documentation
just docs
```

> If you don't have `just` installed, you can use `uv run just` instead of `just`.

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Links

- **GitHub Repository**: https://github.com/psiace/bub/
- **Documentation**: https://bub.build/
- **PyPI Package**: https://pypi.org/project/bub/

## License

This project is licensed under the Apache-2.0 License - see the [LICENSE](LICENSE) file for details.
