from __future__ import annotations

import subprocess
from pathlib import Path

from ship_note.cli import collect_commits, render_draft, resolve_range


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, text=True)


def _init_repo(path: Path) -> None:
    _run(["git", "init", "-b", "main"], path)
    _run(["git", "config", "user.name", "Test"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)


def _write(path: Path, rel: str, content: str) -> None:
    full = path / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


def _commit_all(path: Path, msg: str) -> None:
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", msg], path)


def test_resolve_range_defaults_to_last_tag(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _commit_all(repo, "feat: init")
    _run(["git", "tag", "v0.1.0"], repo)
    _write(repo, "src/a.txt", "x\n")
    _commit_all(repo, "fix: patch")

    base, target, range_spec = resolve_range(repo, since_tag=None, since_commit=None)
    assert base == "v0.1.0"
    assert target == "HEAD"
    assert range_spec == "v0.1.0..HEAD"


def test_collect_commits_and_render(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _commit_all(repo, "feat: add command")
    _write(repo, "README.md", "y\n")
    _commit_all(repo, "fix: patch bug")

    commits = collect_commits(repo, range_spec="HEAD~1..HEAD")
    assert len(commits) == 1
    assert commits[0].subject == "fix: patch bug"

    draft = render_draft(
        repo_name="demo",
        commits=commits,
        base_ref="HEAD~1",
        target_ref="HEAD",
        repo_url="https://example.com/repo",
        release_url=None,
    )
    assert "# demo devlog draft" in draft
    assert "- patch bug" in draft
    assert "## Links" in draft
    assert "https://example.com/repo" in draft


def test_resolve_range_rejects_both_flags(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _commit_all(repo, "chore: init")

    try:
        resolve_range(repo, since_tag="v0.1.0", since_commit="abc123")
    except ValueError as e:
        assert "only one" in str(e).lower()
    else:
        raise AssertionError("Expected ValueError")
