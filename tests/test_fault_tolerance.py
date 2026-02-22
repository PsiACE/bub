from __future__ import annotations

from pathlib import Path

import pytest

from bub.framework import BubFramework


def _write_broken_skill(workspace: Path) -> None:
    broken = workspace / ".agent" / "skills" / "broken"
    adapter_file = broken / "agents" / "bub" / "adapter.py"
    adapter_file.parent.mkdir(parents=True)
    adapter_file.write_text("import missing_module\n", encoding="utf-8")
    (broken / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: broken",
                "description: broken skill",
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
    skill_dir = workspace / ".agent" / "skills" / "broken-output"
    adapter_file = skill_dir / "agents" / "bub" / "adapter.py"
    adapter_file.parent.mkdir(parents=True)
    adapter_file.write_text(
        "\n".join(
            [
                "from bub.hookspecs import hookimpl",
                "",
                "class BrokenOutputSkill:",
                "    @hookimpl",
                "    def render_outbound(self, message, session_id, state, model_output):",
                "        raise RuntimeError('output broke on purpose')",
                "",
                "adapter = BrokenOutputSkill()",
            ]
        ),
        encoding="utf-8",
    )

    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: broken-output",
                "description: runtime broken output skill",
                "---",
            ]
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_runtime_broken_skill_isolated_from_main_flow(tmp_path: Path) -> None:
    _write_runtime_error_skill(tmp_path)

    framework = BubFramework(tmp_path)
    framework.load_skills()

    result = await framework.process_inbound({"channel": "stdout", "chat_id": "c2", "sender_id": "u1", "content": "safe"})

    assert "broken-output" not in framework.failed_skills
    assert result.outbounds
    assert "safe" in result.model_output
