# Bub - Bub it. Build it.

[![Release](https://img.shields.io/github/v/release/psiace/bub)](https://github.com/psiace/bub/releases)
[![Build status](https://img.shields.io/github/actions/workflow/status/psiace/bub/main.yml?branch=main)](https://github.com/psiace/bub/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/psiace/bub)](https://github.com/psiace/bub/graphs/commit-activity)
[![License](https://img.shields.io/github/license/psiace/bub)](https://github.com/psiace/bub/blob/main/LICENSE)

Bub is an AI-powered CLI tool that helps you build, develop, and manage projects using natural language commands. With access to file operations, command execution, and intelligent reasoning, Bub acts as your coding assistant.

## Quick Start

### Installation

```bash
# Install from PyPI (when available)
pip install bub

# Or install from source
git clone https://github.com/psiace/bub.git
cd bub
uv sync
uv run bub --help
```

### Setup

Configure your AI provider and model:

```bash
# For OpenAI
export BUB_PROVIDER="openai"
export BUB_MODEL_NAME="gpt-4"
export BUB_API_KEY="sk-..."

# For Anthropic
export BUB_PROVIDER="anthropic"
export BUB_MODEL_NAME="claude-3-5-sonnet-20241022"
export BUB_API_KEY="your-anthropic-key"
```

### Usage

```bash
# Interactive chat mode
bub chat

# Run a single command
bub run "Create a Python script that prints 'Hello, World!'"

# Specify workspace and model (provider/model format)
bub chat --workspace /path/to/project --model openai/gpt-4

# Get help
bub --help
```

## Examples

Here are some ways you can use Bub:

**File Creation**
```bash
bub run "Create a README.md for a Python project"
```

**Code Assistance**
```bash
bub run "Add error handling to my main.py file"
```

**Project Setup**
```bash
bub run "Initialize a new FastAPI project with basic structure"
```

**Code Review**
```bash
bub run "Review my code and suggest improvements"
```

## Configuration

Configure Bub via environment variables or a `.env` file:

| Variable | Description | Example |
|----------|-------------|---------|
| `BUB_PROVIDER` | AI provider name (required) | `openai`, `anthropic`, `ollama` |
| `BUB_MODEL_NAME` | Model name from provider (required) | `gpt-4`, `claude-3-5-sonnet-20241022` |
| `BUB_API_KEY` | API key for provider (not needed for local models) | `sk-...` |
| `BUB_API_BASE` | Custom API endpoint (optional) | `https://api.custom.ai` |
| `BUB_MAX_TOKENS` | Maximum response tokens (optional) | `4000` |
| `BUB_WORKSPACE_PATH` | Default workspace directory (optional) | `/path/to/work` |
| `BUB_SYSTEM_PROMPT` | Custom system prompt (optional) | `"You are a helpful assistant..."` |

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

### Supported Providers

Bub supports all providers available through [Any-LLM](https://mozilla-ai.github.io/any-llm/):

- **OpenAI**: `openai` - GPT-4, GPT-3.5-turbo, etc.
- **Anthropic**: `anthropic` - Claude models
- **Ollama**: `ollama` - Local models (Llama, CodeLlama, etc.)
- **Groq**: `groq` - Fast inference for open models
- **Mistral**: `mistral` - Mistral AI models
- **Cohere**: `cohere` - Cohere models
- **Google**: `google` - Gemini models
- **And many more...**

## Commands

### `bub chat`

Start an interactive chat session with Bub.

**Options:**
- `--workspace PATH`: Set the workspace directory
- `--model MODEL`: Specify the AI model to use
- `--max-tokens INT`: Set maximum response tokens

**Interactive Commands:**
- `quit`, `exit`, `q`: End the session
- `reset`: Clear conversation history
- `debug`: Toggle debug mode to see AI reasoning process

### `bub run`

Execute a single command with Bub.

**Usage:**
```bash
bub run "COMMAND" [OPTIONS]
```

**Options:**
- `--workspace PATH`: Set the workspace directory
- `--model MODEL`: Specify the AI model to use
- `--max-tokens INT`: Set maximum response tokens

## Links

- **GitHub Repository**: [https://github.com/psiace/bub/](https://github.com/psiace/bub/)
- **Issues & Bug Reports**: [https://github.com/psiace/bub/issues](https://github.com/psiace/bub/issues)
- **Contributing**: [https://github.com/psiace/bub/blob/main/CONTRIBUTING.md](https://github.com/psiace/bub/blob/main/CONTRIBUTING.md)
