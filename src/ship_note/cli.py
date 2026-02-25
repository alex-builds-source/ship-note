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


def extract_changelog_items(path: Path, *, max_items: int = 6) -> list[str]:
    changelog = path / "CHANGELOG.md"
    if not changelog.exists():
        return []

    lines = changelog.read_text(encoding="utf-8").splitlines()

    start_idx: int | None = None
    end_idx = len(lines)

    for i, line in enumerate(lines):
        if line.strip().startswith("## "):
            start_idx = i + 1
            break

    if start_idx is not None:
        for j in range(start_idx, len(lines)):
            if lines[j].strip().startswith("## "):
                end_idx = j
                break
        scan = lines[start_idx:end_idx]
    else:
        scan = lines

    out: list[str] = []
    for line in scan:
        if not line.startswith("- "):
            continue
        item = line[2:].strip()
        if not item:
            continue
        out.append(item)
        if len(out) >= max_items:
            break

    return out


def _normalize_subject(subject: str) -> str:
    normalized = re.sub(r"^(feat|fix|docs|refactor|test|chore)(\([^)]*\))?!?:\s*", "", subject, flags=re.IGNORECASE)
    normalized = normalized.strip()
    return normalized or subject


def _canonical_item(text: str) -> str:
    normalized = text.lower().replace("`", "")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _commit_type(subject: str) -> str:
    lower = subject.lower()
    for kind in ("feat", "fix", "docs", "refactor", "test", "chore"):
        if lower.startswith(kind):
            return kind
    return "other"


def _commit_scope(subject: str) -> str:
    m = re.match(r"^[a-z]+\(([^)]+)\)!?:", subject.strip(), flags=re.IGNORECASE)
    if not m:
        return "general"
    scope = m.group(1).strip().lower()
    return scope or "general"


def _bucket_for_subject(subject: str) -> str:
    commit_type = _commit_type(subject)
    if commit_type == "feat":
        return "features"
    if commit_type == "fix":
        return "fixes"
    if commit_type == "docs":
        return "docs"
    return "other"


def filter_commits(
    commits: list[Commit],
    *,
    include_types: set[str] | None,
    exclude_types: set[str] | None,
    include_scopes: set[str] | None,
    exclude_scopes: set[str] | None,
) -> list[Commit]:
    include = include_types or set()
    exclude = exclude_types or set()
    include_scope_set = {s.lower() for s in (include_scopes or set())}
    exclude_scope_set = {s.lower() for s in (exclude_scopes or set())}

    out: list[Commit] = []
    for c in commits:
        ctype = _commit_type(c.subject)
        scope = _commit_scope(c.subject)
        if include and ctype not in include:
            continue
        if ctype in exclude:
            continue
        if include_scope_set and scope not in include_scope_set:
            continue
        if scope in exclude_scope_set:
            continue
        out.append(c)
    return out


def _is_low_signal_subject(subject: str) -> bool:
    s = subject.strip().lower()
    return (
        (s.startswith("docs:") and "devlog" in s)
        or (s.startswith("chore:") and "release" in s)
        or (s.startswith("chore:") and "version" in s)
    )


def filter_low_signal_commits(commits: list[Commit]) -> list[Commit]:
    return [c for c in commits if not _is_low_signal_subject(c.subject)]


def render_draft(
    *,
    repo_name: str,
    commits: list[Commit],
    changelog_items: list[str],
    base_ref: str,
    target_ref: str,
    repo_url: str | None,
    release_url: str | None,
    group_by: str,
    title_template: str,
    include_validation: bool,
    include_links: bool,
    max_bullets: int,
) -> str:
    bullets: list[str] = []
    seen_items: set[str] = set()

    if commits:
        if group_by == "scope":
            grouped_scope: dict[str, list[str]] = {}
            for c in commits:
                scope = _commit_scope(c.subject)
                grouped_scope.setdefault(scope, []).append(_normalize_subject(c.subject))

            for scope in sorted(grouped_scope.keys()):
                scope_items: list[str] = []
                for item in grouped_scope[scope]:
                    canon = _canonical_item(item)
                    if not canon or canon in seen_items:
                        continue
                    seen_items.add(canon)
                    scope_items.append(item)

                if not scope_items:
                    continue

                bullets.append(f"- [{scope}]")
                for item in scope_items:
                    bullets.append(f"  - {item}")
        else:
            grouped: dict[str, list[str]] = {"features": [], "fixes": [], "docs": [], "other": []}
            for c in commits:
                grouped[_bucket_for_subject(c.subject)].append(_normalize_subject(c.subject))

            for key in ("features", "fixes", "docs", "other"):
                for item in grouped[key]:
                    canon = _canonical_item(item)
                    if not canon or canon in seen_items:
                        continue
                    seen_items.add(canon)
                    bullets.append(f"- {item}")

    for item in changelog_items:
        canon = _canonical_item(item)
        if not canon or canon in seen_items:
            continue
        seen_items.add(canon)
        bullets.append(f"- {item}")

    if bullets:
        what_shipped = "\n".join(bullets[:max_bullets])
        why = f"- Captures {len(commits)} commit(s) from `{base_ref or 'start'}..{target_ref}` with changelog context when available."
    else:
        what_shipped = "- No commits or changelog bullets found for selected range."
        why = "- Helps keep release communication consistent even when no code changes are detected."

    links: list[str] = []
    if repo_url:
        links.append(f"- Repo: {repo_url}")
    if release_url:
        links.append(f"- Release: {release_url}")
    if not links:
        links.append("- Repo: <add-repo-url>")

    title = title_template.replace("{repo}", repo_name)

    out = [
        title,
        "",
        "## What shipped",
        what_shipped,
        "",
        "## Why it matters",
        why,
        "",
    ]

    if include_validation:
        out.extend([
            "## Validation",
            "- Tests: <fill>",
            "- Secret scan: <fill>",
            "",
        ])

    if include_links:
        out.extend([
            "## Links",
            *links,
            "",
        ])

    return "\n".join(out)


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
    raw_commit_count = len(commits)

    include_types = set(args.include_type or [])
    exclude_types = set(args.exclude_type or [])
    allowed_types = {"feat", "fix", "docs", "refactor", "test", "chore", "other"}
    unknown = sorted((include_types | exclude_types) - allowed_types)
    if unknown:
        raise ValueError(f"Unknown commit types: {', '.join(unknown)}")

    commits = filter_commits(
        commits,
        include_types=include_types,
        exclude_types=exclude_types,
        include_scopes=set(args.include_scope or []),
        exclude_scopes=set(args.exclude_scope or []),
    )

    group_by = args.group_by or "type"
    if group_by not in {"type", "scope"}:
        raise ValueError("group_by must be one of: type, scope")

    preset = args.preset or "standard"
    if preset not in {"short", "standard"}:
        raise ValueError("preset must be one of: short, standard")

    default_title_template = "# {repo} update" if preset == "short" else "# {repo} devlog draft"
    default_include_validation = preset != "short"
    default_max_bullets = 4 if preset == "short" else 12
    default_max_changelog_items = 4 if preset == "short" else 6

    max_bullets = args.max_bullets if args.max_bullets is not None else default_max_bullets
    max_changelog_items = (
        args.max_changelog_items if args.max_changelog_items is not None else default_max_changelog_items
    )
    if max_bullets <= 0:
        raise ValueError("max_bullets must be > 0")
    if max_changelog_items <= 0:
        raise ValueError("max_changelog_items must be > 0")

    changelog_items = extract_changelog_items(repo_path, max_items=max_changelog_items)
    if raw_commit_count == 0:
        # avoid stale "what shipped" bullets when range has no new commits
        changelog_items = []

    if preset == "short" and not args.keep_low_signal:
        filtered = filter_low_signal_commits(commits)
        if filtered:
            commits = filtered
        elif changelog_items:
            # prefer changelog signal over low-signal commit noise
            commits = []
        # else: keep original commits so output is not empty when no changelog exists

    repo_name = repo_path.name
    output = render_draft(
        repo_name=repo_name,
        commits=commits,
        changelog_items=changelog_items,
        base_ref=base_ref,
        target_ref=target_ref,
        repo_url=args.repo_url,
        release_url=args.release_url,
        group_by=group_by,
        title_template=args.title_template or default_title_template,
        include_validation=default_include_validation and (not args.no_validation),
        include_links=not args.no_links,
        max_bullets=max_bullets,
    )

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = repo_path / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Wrote draft: {out_path}")
        return 0

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
    draft.add_argument(
        "--include-type",
        action="append",
        help="Only include commits with this type (repeatable: feat|fix|docs|refactor|test|chore|other)",
    )
    draft.add_argument(
        "--exclude-type",
        action="append",
        help="Exclude commits with this type (repeatable: feat|fix|docs|refactor|test|chore|other)",
    )
    draft.add_argument(
        "--include-scope",
        action="append",
        help="Only include commits with this scope (repeatable, conventional commit scope; use 'general' when no scope)",
    )
    draft.add_argument(
        "--exclude-scope",
        action="append",
        help="Exclude commits with this scope (repeatable, conventional commit scope; use 'general' when no scope)",
    )
    draft.add_argument(
        "--preset",
        choices=["short", "standard"],
        default="standard",
        help="Output preset: short is concise for chat updates; standard is fuller release notes",
    )
    draft.add_argument("--group-by", choices=["type", "scope"], default="type", help="Group commit bullets by type or scope")
    draft.add_argument("--max-bullets", type=int, help="Cap bullet lines in What shipped")
    draft.add_argument("--max-changelog-items", type=int, help="Cap changelog bullets considered for enrichment")
    draft.add_argument("--keep-low-signal", action="store_true", help="In short preset, keep low-signal release/admin commits")
    draft.add_argument("--title-template", help="Title template, supports {repo} placeholder")
    draft.add_argument("--no-validation", action="store_true", help="Skip Validation section")
    draft.add_argument("--no-links", action="store_true", help="Skip Links section")
    draft.add_argument("--output", help="Write markdown output to a file")
    draft.set_defaults(func=cmd_draft)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
