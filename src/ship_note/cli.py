from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Commit:
    sha: str
    subject: str


def _run_git(path: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(path), capture_output=True, text=True)


def _is_git_repo(path: Path) -> bool:
    proc = _run_git(path, ["rev-parse", "--is-inside-work-tree"])
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def _latest_tag(path: Path) -> str | None:
    proc = _run_git(path, ["describe", "--tags", "--abbrev=0"])
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return out or None


def resolve_range(path: Path, *, since_tag: str | None, since_commit: str | None) -> tuple[str, str, str]:
    if since_tag and since_commit:
        raise ValueError("Use only one of --since-tag or --since-commit")

    target = "HEAD"
    if since_commit:
        return since_commit, target, f"{since_commit}..{target}"

    if since_tag:
        return since_tag, target, f"{since_tag}..{target}"

    last_tag = _latest_tag(path)
    if last_tag:
        return last_tag, target, f"{last_tag}..{target}"

    return "", target, target


def collect_commits(path: Path, *, range_spec: str) -> list[Commit]:
    args = ["log", "--pretty=format:%H\t%s"]
    if range_spec:
        args.append(range_spec)

    proc = _run_git(path, args)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or "git log failed"
        raise ValueError(f"Could not read git history: {err}")

    commits: list[Commit] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        commits.append(Commit(sha=parts[0], subject=parts[1]))
    return commits


def _normalize_subject(subject: str) -> str:
    normalized = re.sub(r"^(feat|fix|docs|refactor|test|chore)(\([^)]*\))?!?:\s*", "", subject, flags=re.IGNORECASE)
    normalized = normalized.strip()
    return normalized or subject


def _bucket_for_subject(subject: str) -> str:
    lower = subject.lower()
    if lower.startswith("feat"):
        return "features"
    if lower.startswith("fix"):
        return "fixes"
    if lower.startswith("docs"):
        return "docs"
    return "other"


def render_draft(
    *,
    repo_name: str,
    commits: list[Commit],
    base_ref: str,
    target_ref: str,
    repo_url: str | None,
    release_url: str | None,
) -> str:
    if commits:
        grouped: dict[str, list[str]] = {"features": [], "fixes": [], "docs": [], "other": []}
        for c in commits:
            grouped[_bucket_for_subject(c.subject)].append(_normalize_subject(c.subject))

        bullets: list[str] = []
        for key in ("features", "fixes", "docs", "other"):
            for item in grouped[key]:
                bullets.append(f"- {item}")

        what_shipped = "\n".join(bullets[:8])
        why = f"- Captures {len(commits)} commit(s) from `{base_ref or 'start'}..{target_ref}` into a publish-ready summary."
    else:
        what_shipped = "- No commits found for selected range."
        why = "- Helps keep release communication consistent even when no code changes are detected."

    links: list[str] = []
    if repo_url:
        links.append(f"- Repo: {repo_url}")
    if release_url:
        links.append(f"- Release: {release_url}")
    if not links:
        links.append("- Repo: <add-repo-url>")

    return "\n".join(
        [
            f"# {repo_name} devlog draft",
            "",
            "## What shipped",
            what_shipped,
            "",
            "## Why it matters",
            why,
            "",
            "## Validation",
            "- Tests: <fill>",
            "- Secret scan: <fill>",
            "",
            "## Links",
            *links,
            "",
        ]
    )


def cmd_draft(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    if not _is_git_repo(repo_path):
        raise ValueError(f"Not a git repository: {repo_path}")

    base_ref, target_ref, range_spec = resolve_range(
        repo_path,
        since_tag=args.since_tag,
        since_commit=args.since_commit,
    )
    commits = collect_commits(repo_path, range_spec=range_spec)

    repo_name = repo_path.name
    output = render_draft(
        repo_name=repo_name,
        commits=commits,
        base_ref=base_ref,
        target_ref=target_ref,
        repo_url=args.repo_url,
        release_url=args.release_url,
    )
    print(output, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ship-note", description="Generate release/devlog drafts from git history")
    sub = parser.add_subparsers(dest="command", required=True)

    draft = sub.add_parser("draft", help="Render a markdown devlog draft")
    draft.add_argument("--path", default=".", help="Repository path (default: current directory)")
    draft.add_argument("--since-tag", help="Base range from the specified tag")
    draft.add_argument("--since-commit", help="Base range from the specified commit sha/ref")
    draft.add_argument("--repo-url", help="Repository URL for links section")
    draft.add_argument("--release-url", help="Release URL for links section")
    draft.set_defaults(func=cmd_draft)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
