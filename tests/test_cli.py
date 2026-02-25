from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ship_note.cli import (
    Commit,
    cmd_draft,
    collect_commits,
    extract_changelog_items,
    filter_commits,
    filter_low_signal_commits,
    render_draft,
    resolve_range,
)


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
        changelog_items=["Added smoke coverage"],
        base_ref="HEAD~1",
        target_ref="HEAD",
        repo_url="https://example.com/repo",
        release_url=None,
        group_by="type",
        title_template="# {repo} devlog draft",
        include_validation=True,
        include_links=True,
        max_bullets=12,
    )
    assert "# demo devlog draft" in draft
    assert "- patch bug" in draft
    assert "- Added smoke coverage" in draft
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


def test_extract_changelog_items(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(
        repo,
        "CHANGELOG.md",
        "# Changelog\n\n## [0.2.0]\n- Added new parser\n  - nested detail should be ignored\n- Added docs\n\n## [0.1.0]\n- Added draft command\n- Added tests\n",
    )
    items = extract_changelog_items(repo)
    assert items == ["Added new parser", "Added docs"]


def test_cmd_draft_writes_output_file(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _write(repo, "CHANGELOG.md", "# Changelog\n\n- Added draft support\n")
    _commit_all(repo, "feat: init")

    args = argparse.Namespace(
        path=str(repo),
        since_tag=None,
        since_commit=None,
        repo_url=None,
        release_url=None,
        include_type=None,
        exclude_type=None,
        include_scope=None,
        exclude_scope=None,
        preset="standard",
        group_by="type",
        title_template=None,
        no_validation=False,
        no_links=False,
        keep_low_signal=False,
        max_bullets=None,
        max_changelog_items=None,
        output="out/devlog.md",
    )
    rc = cmd_draft(args)
    assert rc == 0
    out = repo / "out" / "devlog.md"
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "devlog draft" in text
    assert "Added draft support" in text


def test_cmd_draft_short_preset_omits_validation_and_uses_short_title(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _commit_all(repo, "feat: init")

    args = argparse.Namespace(
        path=str(repo),
        since_tag=None,
        since_commit=None,
        repo_url=None,
        release_url=None,
        include_type=None,
        exclude_type=None,
        include_scope=None,
        exclude_scope=None,
        preset="short",
        group_by="type",
        title_template=None,
        no_validation=False,
        no_links=False,
        keep_low_signal=False,
        max_bullets=None,
        max_changelog_items=None,
        output="out/short.md",
    )
    rc = cmd_draft(args)
    assert rc == 0
    text = (repo / "out" / "short.md").read_text(encoding="utf-8")
    assert "# repo update" in text
    assert "## Validation" not in text


def test_cmd_draft_short_drops_low_signal_when_changelog_exists(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _write(repo, "CHANGELOG.md", "# Changelog\n\n## [0.2.0]\n- Added parser improvements\n")
    _commit_all(repo, "docs: publish v0.1.0 devlog")

    args = argparse.Namespace(
        path=str(repo),
        since_tag=None,
        since_commit=None,
        repo_url=None,
        release_url=None,
        include_type=None,
        exclude_type=None,
        include_scope=None,
        exclude_scope=None,
        preset="short",
        group_by="type",
        title_template=None,
        no_validation=False,
        no_links=False,
        keep_low_signal=False,
        max_bullets=None,
        max_changelog_items=None,
        output="out/short.md",
    )
    rc = cmd_draft(args)
    assert rc == 0
    text = (repo / "out" / "short.md").read_text(encoding="utf-8")
    assert "Added parser improvements" in text
    assert "publish v0.1.0 devlog" not in text


def test_cmd_draft_short_keeps_low_signal_when_no_changelog(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _commit_all(repo, "docs: publish v0.1.0 devlog")

    args = argparse.Namespace(
        path=str(repo),
        since_tag=None,
        since_commit=None,
        repo_url=None,
        release_url=None,
        include_type=None,
        exclude_type=None,
        include_scope=None,
        exclude_scope=None,
        preset="short",
        group_by="type",
        title_template=None,
        no_validation=False,
        no_links=False,
        keep_low_signal=False,
        max_bullets=None,
        max_changelog_items=None,
        output="out/short.md",
    )
    rc = cmd_draft(args)
    assert rc == 0
    text = (repo / "out" / "short.md").read_text(encoding="utf-8")
    assert "publish v0.1.0 devlog" in text


def test_cmd_draft_drops_changelog_when_range_has_no_commits(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _write(repo, "README.md", "x\n")
    _write(repo, "CHANGELOG.md", "# Changelog\n\n## [0.1.0]\n- Added major feature\n")
    _commit_all(repo, "feat: init")
    _run(["git", "tag", "v0.1.0"], repo)

    args = argparse.Namespace(
        path=str(repo),
        since_tag="v0.1.0",
        since_commit=None,
        repo_url=None,
        release_url=None,
        include_type=None,
        exclude_type=None,
        include_scope=None,
        exclude_scope=None,
        preset="short",
        group_by="type",
        title_template=None,
        no_validation=False,
        no_links=False,
        keep_low_signal=False,
        max_bullets=None,
        max_changelog_items=None,
        output="out/short.md",
    )
    rc = cmd_draft(args)
    assert rc == 0
    text = (repo / "out" / "short.md").read_text(encoding="utf-8")
    assert "Added major feature" not in text
    assert "No commits or changelog bullets found" in text


def test_filter_low_signal_commits_drops_release_admin_noise():
    commits = [
        Commit(sha="1", subject="feat: add parser"),
        Commit(sha="2", subject="docs: publish v0.1.0 devlog"),
        Commit(sha="3", subject="chore: prepare v0.1.4 release notes and version"),
    ]
    filtered = filter_low_signal_commits(commits)
    assert [c.sha for c in filtered] == ["1"]


def test_filter_commits_include_exclude_types():
    commits = [
        Commit(sha="1", subject="feat: add CLI"),
        Commit(sha="2", subject="fix: patch bug"),
        Commit(sha="3", subject="docs: update readme"),
    ]

    only_feat = filter_commits(
        commits,
        include_types={"feat"},
        exclude_types=None,
        include_scopes=None,
        exclude_scopes=None,
    )
    assert [c.sha for c in only_feat] == ["1"]

    no_docs = filter_commits(
        commits,
        include_types=None,
        exclude_types={"docs"},
        include_scopes=None,
        exclude_scopes=None,
    )
    assert [c.sha for c in no_docs] == ["1", "2"]


def test_filter_commits_include_exclude_scopes():
    commits = [
        Commit(sha="1", subject="feat(api): add endpoint"),
        Commit(sha="2", subject="fix(ui): patch modal"),
        Commit(sha="3", subject="chore: clean up"),
    ]

    only_api = filter_commits(
        commits,
        include_types=None,
        exclude_types=None,
        include_scopes={"api"},
        exclude_scopes=None,
    )
    assert [c.sha for c in only_api] == ["1"]

    no_general = filter_commits(
        commits,
        include_types=None,
        exclude_types=None,
        include_scopes=None,
        exclude_scopes={"general"},
    )
    assert [c.sha for c in no_general] == ["1", "2"]


def test_render_draft_dedupes_changelog_items_against_commits():
    commits = [Commit(sha="1", subject="feat: add parser")]
    draft = render_draft(
        repo_name="demo",
        commits=commits,
        changelog_items=["Add parser.", "Added docs"],
        base_ref="v0.1.0",
        target_ref="HEAD",
        repo_url=None,
        release_url=None,
        group_by="type",
        title_template="# {repo} devlog draft",
        include_validation=True,
        include_links=False,
        max_bullets=12,
    )
    assert draft.lower().count("add parser") == 1
    assert "- Added docs" in draft


def test_render_draft_group_by_scope_and_toggle_sections():
    commits = [
        Commit(sha="1", subject="feat(api): add endpoint"),
        Commit(sha="2", subject="fix(ui): patch modal"),
    ]

    draft = render_draft(
        repo_name="demo",
        commits=commits,
        changelog_items=[],
        base_ref="v0.1.0",
        target_ref="HEAD",
        repo_url=None,
        release_url=None,
        group_by="scope",
        title_template="# Release notes for {repo}",
        include_validation=False,
        include_links=False,
        max_bullets=12,
    )
    assert "# Release notes for demo" in draft
    assert "- [api]" in draft
    assert "- [ui]" in draft
    assert "## Validation" not in draft
    assert "## Links" not in draft


def test_render_draft_respects_max_bullets_cap():
    commits = [
        Commit(sha="1", subject="feat: add one"),
        Commit(sha="2", subject="fix: add two"),
        Commit(sha="3", subject="docs: add three"),
    ]
    draft = render_draft(
        repo_name="demo",
        commits=commits,
        changelog_items=["Added four"],
        base_ref="v0.1.0",
        target_ref="HEAD",
        repo_url=None,
        release_url=None,
        group_by="type",
        title_template="# {repo} devlog draft",
        include_validation=False,
        include_links=False,
        max_bullets=2,
    )
    section = draft.split("## What shipped\n", 1)[1].split("\n\n## Why", 1)[0]
    bullet_lines = [line for line in section.splitlines() if line.strip().startswith("-")]
    assert len(bullet_lines) == 2
