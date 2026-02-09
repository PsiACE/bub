from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _python_blocks(text: str) -> list[str]:
    return [match.strip() for match in PYTHON_BLOCK.findall(text)]


def _normalize_block(block: str) -> str:
    lines = []
    for line in block.splitlines():
        if line.strip().startswith("# test:skip"):
            continue
        lines.append(line)
    return "\n".join(lines)


@pytest.mark.parametrize("path", [Path("README.md"), *sorted(Path("docs").rglob("*.md"))])
def test_markdown_python_blocks_are_valid_python(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    blocks = _python_blocks(text)
    for block in blocks:
        ast.parse(_normalize_block(block))


@pytest.mark.parametrize("path", sorted(Path("examples").glob("*.py")))
def test_examples_are_valid_python(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    ast.parse(source)
