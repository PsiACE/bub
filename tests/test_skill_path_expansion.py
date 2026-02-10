import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script_module(name: str, relative_path: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / relative_path
    module_dir = str(module_path.parent)
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, module_dir)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if sys.path and sys.path[0] == module_dir:
            sys.path.pop(0)
    return module


def test_init_skill_expands_home_in_path(monkeypatch, tmp_path: Path) -> None:
    module = _load_script_module(
        "skill_creator_init_script",
        "src/bub/skills/skill-creator/scripts/init_skill.py",
    )

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    created = module.init_skill("demo-skill", "~/skills", [], False, [])

    expected = (fake_home / "skills" / "demo-skill").resolve()
    assert created == expected
    assert (expected / "SKILL.md").exists()


def test_installer_expands_home_in_dest(monkeypatch, tmp_path: Path) -> None:
    module = _load_script_module(
        "skill_installer_script",
        "src/bub/skills/skill-installer/scripts/install-skill-from-github.py",
    )

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    repo_root = tmp_path / "repo"
    skill_src = repo_root / "skills" / "demo"
    skill_src.mkdir(parents=True)
    (skill_src / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")

    def _fake_prepare_repo(source, method, tmp_dir):
        _ = (method, tmp_dir)
        assert source.paths == ["skills/demo"]
        return str(repo_root)

    monkeypatch.setattr(module, "_prepare_repo", _fake_prepare_repo)

    exit_code = module.main(
        [
            "--repo",
            "owner/repo",
            "--path",
            "skills/demo",
            "--dest",
            "~/installed-skills",
            "--method",
            "download",
        ]
    )

    expected = (fake_home / "installed-skills" / "demo").resolve()
    assert exit_code == 0
    assert (expected / "SKILL.md").exists()
