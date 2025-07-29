# Default recipe - show help
default:
    @just --list

# Install the virtual environment and install the pre-commit hooks
install:
    #!/usr/bin/env bash
    echo "🚀 Creating virtual environment using uv"
    uv sync
    uv run pre-commit install

# Run code quality tools
check:
    #!/usr/bin/env bash
    echo "🚀 Checking lock file consistency with 'pyproject.toml'"
    uv lock --locked
    echo "🚀 Linting code: Running pre-commit"
    uv run pre-commit run -a
    echo "🚀 Static type checking: Running mypy"
    uv run mypy

# Run vulture to check for unused code
vulture:
    #!/usr/bin/env bash
    echo "🚀 Checking for unused code with vulture"
    uv run pre-commit run vulture --hook-stage manual --all-files

# Test the code with pytest
test:
    #!/usr/bin/env bash
    echo "🚀 Testing code: Running pytest"
    uv run python -m pytest --doctest-modules

# Clean build artifacts
clean-build:
    #!/usr/bin/env bash
    echo "🚀 Removing build artifacts"
    uv run python -c "import shutil; import os; shutil.rmtree('dist') if os.path.exists('dist') else None"

# Build wheel file
build: clean-build
    #!/usr/bin/env bash
    echo "🚀 Creating wheel file"
    uvx --from build pyproject-build --installer uv

# Publish a release to PyPI
publish:
    #!/usr/bin/env bash
    echo "🚀 Publishing."
    uvx twine upload --repository-url https://upload.pypi.org/legacy/ dist/*

# Build and publish
build-and-publish: build publish

# Test if documentation can be built without warnings or errors
docs-test:
    #!/usr/bin/env bash
    uv run mkdocs build -s

# Build and serve the documentation
docs:
    #!/usr/bin/env bash
    uv run mkdocs serve
