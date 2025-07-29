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

Bub supports multiple AI providers through Any-LLM. Configure provider and model:

```bash
# For OpenAI
export BUB_PROVIDER="openai"
export BUB_MODEL_NAME="gpt-4"
export BUB_API_KEY="sk-..."

# For Anthropic
export BUB_PROVIDER="anthropic"
export BUB_MODEL_NAME="claude-3-sonnet-20240229"
export BUB_API_KEY="your-anthropic-key"

# For local models with Ollama
export BUB_PROVIDER="ollama"
export BUB_MODEL_NAME="llama2"
# No API key needed for local models
```

### 2. Start using Bub

```bash
# Interactive chat mode
bub chat

# Run a single command
bub run "Create a Python script that prints 'Hello, World!'"

# Specify workspace and model
bub chat --workspace /path/to/project --model gpt-4

# Get help
bub --help
```

## Usage Examples

```bash
# Create files
bub run "Create a README.md for a Python project"

# Code assistance
bub run "Add error handling to my main.py file"

# Project setup
bub run "Initialize a new FastAPI project with basic structure"

# Code review
bub run "Review my code and suggest improvements"
```

## Configuration

Bub can be configured via environment variables or a `.env` file:

```bash
BUB_API_KEY=your-api-key-here
BUB_MODEL=gpt-4                    # AI model to use
BUB_API_BASE=https://api.custom.ai # Custom API endpoint
BUB_MAX_TOKENS=4000               # Maximum response tokens
BUB_WORKSPACE_PATH=/path/to/work  # Default workspace
BUB_SYSTEM_PROMPT="custom prompt" # Custom system prompt
```

### Custom System Prompt with BUB.md

You can customize Bub's behavior by creating a `BUB.md` file in your workspace. This file will be automatically read and used as the system prompt, allowing you to define project-specific instructions, coding standards, and behavior guidelines.

**Example BUB.md:**

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

The BUB.md file takes precedence over the `BUB_SYSTEM_PROMPT` environment variable, making it easy to share consistent AI behavior across your development team.

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
