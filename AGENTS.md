# AGENTS.md - Bub Development Guide

## Commands
- **Test**: `uv run pytest --doctest-modules` or `just test`
- **Test single**: `uv run pytest tests/test_specific.py::test_function`
- **Test with coverage**: `uv run pytest --cov=src/bub`
- **Lint/Check**: `just check` (runs prek, mypy, lock check)
- **Type check**: `uv run mypy` (targets `src/` only)
- **Format**: `uv run ruff format .` and `uv run ruff check --fix .`
- **Build**: `just build` (creates wheel with uvx pyproject-build)
- **Docs**: `just docs` (serve) or `just docs-test` (build only)
- **Install dev**: `just install` (uv sync + prek install)
- **Sync dependencies**: `uv sync`
- **Add dependency**: `uv add package-name` or `uv add --dev package-name`
- **Update lock**: `uv lock`

## Python Style Guidelines

### Naming Conventions
- **Variables, functions, methods, packages, modules**: `snake_case_with_underscores`
- **Classes and Exceptions**: `PascalCase`
- **Protected methods**: `_single_leading_underscore`
- **Private methods**: `__double_leading_underscore`
- **Constants**: `ALL_CAPS_WITH_UNDERSCORES`

### Code Style Best Practices
- **Line length**: 120 chars max (ruff configured)
- **Type hints**: Required for all functions and methods (mypy strict mode)
- **Equality**: Use `is` for None/True/False, not `==`
- **List comprehensions**: Preferred over for loops when possible
- **File handling**: Always use `with` statement for file operations
- **Comments**: Use sparingly, prefer self-documenting code

### Imports Organization
Organize imports in three sections, separated by blank lines:
1. **System imports** (stdlib)
2. **Third-party imports** (external packages)
3. **Local imports** (project modules)

```python
import os
from pathlib import Path

import pydantic
from typer import Typer

from bub.events import EventManager
from bub.hooks import BaseHook
```

### Documentation
- **Docstrings**: Follow PEP 257 guidelines
- **One-line docstrings**: For obvious functions
- **Multi-line docstrings**: Include summary, args, return type
- **Class docstrings**: Document `__init__` parameters in class docstring

```python
def process_event(event: BaseEvent) -> bool:
    """Process an event and return success status."""
    pass

class EventProcessor:
    """Processes events from the shell hook system.

    Args:
        config: Configuration object for the processor
        logger: Optional logger instance
    """
    def __init__(self, config: Config, logger: Optional[Logger] = None):
        pass
```

### Function Design
- **Single responsibility**: Functions should do one thing
- **2 or fewer parameters**: Use dataclasses/TypedDict for complex parameters
- **Avoid flags**: Split functions instead of boolean parameters
- **Descriptive names**: Function names should explain what they do
- **One abstraction level**: Don't mix high and low-level operations

### Testing Guidelines
- **100% coverage goal**: Strive for complete test coverage
- **Descriptive test names**: Test names should read like scenarios
- **Isolated tests**: No external dependencies (real databases, networks)
- **Use factories**: Prefer factory pattern over fixtures
- **Fast tests**: Unit tests should be quick to run

## UV Package Management

### Project Setup
```bash
# Initialize new project
uv init my-project

# Add dependencies
uv add requests 'flask>=2.0.0' 'pytest[testing]'

# Add development dependencies
uv add --dev black ruff mypy pytest-cov

# Install all dependencies
uv sync
```

### Virtual Environment
- UV automatically manages `.venv` in project root
- Activates automatically for `uv run` commands
- Manual activation: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows)

### Dependency Management Best Practices
- **Lock dependencies**: Always commit `uv.lock` file
- **Semantic versioning**: Use `~=2.0.0` for compatible releases
- **Version ranges**: Use `>=2.0.0,<3.0.0` for major version constraints
- **Regular updates**: Run `uv lock --upgrade` periodically

### CI/CD Integration
```yaml
# .github/workflows/ci.yml
- name: Install UV
  run: curl -LsSf https://astral.sh/uv/install.sh | sh

- name: Setup Python
  run: uv python install 3.12

- name: Install dependencies
  run: uv sync

- name: Run tests
  run: uv run pytest --cov=src/bub
```

## Version Control Best Practices
- **Commit `uv.lock`**: Ensures reproducible builds
- **Ignore `.venv/`**: Virtual environment shouldn't be versioned
- **Ignore `__pycache__/`**: Python bytecode files
- **Ignore `.pytest_cache/`**: Test cache directories

## Development Workflow
1. **Setup**: `just install` or `uv sync && prek install`
2. **Add feature**: Create feature branch
3. **Code**: Follow style guidelines, add tests
4. **Check**: Run `just check` before committing
5. **Test**: Run `uv run pytest --cov=src/bub`
6. **Commit**: Pre-commit hooks will run automatically
7. **PR**: Submit pull request with tests and documentation

## Performance Considerations
- **Concurrent operations**: UV downloads packages in parallel
- **Cache management**: UV caches wheels and metadata
- **Build optimization**: Use prebuilt wheels when available
- **Memory usage**: Monitor during large dependency installations
