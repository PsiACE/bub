from __future__ import annotations

from pathlib import Path

import pytest

from bub.framework import BubFramework


def _write_broken_skill(workspace: Path) -> None:
    broken = workspace / ".agent" / "skills" / "broken"
    broken.mkdir(parents=True)
    (broken / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: broken",
                "description: broken skill",
                "kind: model",
                "entrypoint: missing.module:plugin",
                "---",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_broken_skill_does_not_break_framework(tmp_path: Path) -> None:
    _write_broken_skill(tmp_path)

    framework = BubFramework(tmp_path)
    framework.load_skills()

    assert "broken" in framework.failed_skills
    result = await framework.process_inbound({"channel": "stdout", "chat_id": "c1", "sender_id": "u1", "content": "still works"})
    assert "still works" in result.model_output


def _write_runtime_error_skill(workspace: Path) -> None:
    package = workspace / "runtime_plugins"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "broken_output.py").write_text(
        "\n".join(
            [
                "from bub.hookspecs import hookimpl",
                "",
                "class BrokenOutputSkill:",
                "    @hookimpl",
                "    def render_outbound(self, message, session_id, state, model_output):",
                "        raise RuntimeError('output broke on purpose')",
                "",
                "plugin = BrokenOutputSkill()",
            ]
        ),
        encoding="utf-8",
    )

    skill_dir = workspace / ".agent" / "skills" / "broken-output"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: broken-output",
                "description: runtime broken output skill",
                "kind: output",
                "entrypoint: runtime_plugins.broken_output:plugin",
                "---",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_runtime_broken_skill_isolated_from_main_flow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_runtime_error_skill(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound({"channel": "stdout", "chat_id": "c2", "sender_id": "u1", "content": "safe"})

    assert "broken-output" not in framework.failed_skills
    assert result.outbounds
    assert "safe" in result.model_output
