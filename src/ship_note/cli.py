from __future__ import annotations

import argparse
import json
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

    if s.startswith("docs:"):
        return any(token in s for token in ("devlog", "release notes", "changelog"))

    if s.startswith("chore:"):
        return any(
            token in s
            for token in (
                "release",
                "version",
                "bump deps",
                "bump dependencies",
                "dependency",
                "changelog",
            )
        )

    return False


def filter_low_signal_commits(commits: list[Commit]) -> list[Commit]:
    return [c for c in commits if not _is_low_signal_subject(c.subject)]


def _default_title_template(*, preset: str, destination: str) -> str:
    short = preset == "short"
    if short:
        if destination == "social":
            return "# {repo} social update"
        if destination == "internal":
            return "# {repo} internal update"
        return "# {repo} update"

    if destination == "social":
        return "# {repo} social draft"
    if destination == "internal":
        return "# {repo} internal release brief"
    if destination == "update":
        return "# {repo} update draft"
    return "# {repo} devlog draft"


def _build_why_lines(
    *,
    base_ref: str,
    target_ref: str,
    raw_commit_count: int,
    commit_items_used: int,
    changelog_items_used: int,
    has_content: bool,
) -> list[str]:
    range_label = f"{base_ref or 'start'}..{target_ref}"

    if not has_content:
        return ["- No substantive draft items were found for the selected range; this may be a no-change or maintenance-only release."]

    lines = [f"- Covers `{range_label}` using {commit_items_used} distilled bullet(s) from {raw_commit_count} commit(s)."]

    if changelog_items_used > 0:
        lines.append(f"- Adds {changelog_items_used} changelog bullet(s) to fill context that commit subjects alone may miss.")
    else:
        lines.append("- Keeps the summary focused on commit-level changes for faster release communication.")

    return lines


def _build_render_data(
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
    include_why: bool,
    max_bullets: int,
) -> dict[str, object]:
    bullet_rows: list[tuple[str, str]] = []  # (line, source) where source in {commit,changelog,header}
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

                bullet_rows.append((f"- [{scope}]", "header"))
                for item in scope_items:
                    bullet_rows.append((f"  - {item}", "commit"))
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
                    bullet_rows.append((f"- {item}", "commit"))

    for item in changelog_items:
        canon = _canonical_item(item)
        if not canon or canon in seen_items:
            continue
        seen_items.add(canon)
        bullet_rows.append((f"- {item}", "changelog"))

    selected_rows = bullet_rows[:max_bullets]
    selected_lines = [line for line, _ in selected_rows]
    commit_items_used = sum(1 for _, src in selected_rows if src == "commit")
    changelog_items_used = sum(1 for _, src in selected_rows if src == "changelog")

    if selected_lines:
        what_shipped_lines = selected_lines
    else:
        what_shipped_lines = ["- No commits or changelog bullets found for selected range."]

    why_lines = _build_why_lines(
        base_ref=base_ref,
        target_ref=target_ref,
        raw_commit_count=len(commits),
        commit_items_used=commit_items_used,
        changelog_items_used=changelog_items_used,
        has_content=bool(selected_lines),
    )

    links: list[str] = []
    if repo_url:
        links.append(f"- Repo: {repo_url}")
    if release_url:
        links.append(f"- Release: {release_url}")
    if not links:
        links.append("- Repo: <add-repo-url>")

    title = title_template.replace("{repo}", repo_name)

    return {
        "title": title,
        "what_shipped_lines": what_shipped_lines,
        "why_lines": why_lines,
        "include_why": include_why,
        "include_validation": include_validation,
        "include_links": include_links,
        "links": links,
        "stats": {
            "commit_items_used": commit_items_used,
            "changelog_items_used": changelog_items_used,
            "bullet_line_count": len(selected_lines),
        },
    }


def _render_markdown_from_data(data: dict[str, object]) -> str:
    out: list[str] = [
        str(data["title"]),
        "",
        "## What shipped",
        "\n".join(data["what_shipped_lines"]),
        "",
    ]

    if bool(data.get("include_why", True)):
        out.extend([
            "## Why it matters",
            "\n".join(data["why_lines"]),
            "",
        ])

    if bool(data["include_validation"]):
        out.extend([
            "## Validation",
            "- Tests: <fill>",
            "- Secret scan: <fill>",
            "",
        ])

    if bool(data["include_links"]):
        out.extend([
            "## Links",
            *[str(x) for x in data["links"]],
            "",
        ])

    return "\n".join(out)


def _line_to_item_text(line: str) -> str | None:
    s = line.strip()
    if not s.startswith("-"):
        return None
    text = s[1:].strip()
    if not text:
        return None
    if text.startswith("[") and text.endswith("]"):
        return None
    return text


def _build_structured_items(
    *,
    what_shipped_lines: list[str],
    commits: list[Commit],
    changelog_items: list[str],
) -> list[dict[str, object]]:
    commit_lookup: dict[str, dict[str, object]] = {}
    for c in commits:
        normalized = _normalize_subject(c.subject)
        key = _canonical_item(normalized)
        if key and key not in commit_lookup:
            commit_lookup[key] = {
                "source": "commit",
                "text": normalized,
                "sha": c.sha,
                "type": _commit_type(c.subject),
                "scope": _commit_scope(c.subject),
            }

    changelog_lookup: dict[str, str] = {}
    for item in changelog_items:
        key = _canonical_item(item)
        if key and key not in changelog_lookup:
            changelog_lookup[key] = item

    out: list[dict[str, object]] = []
    seen_keys: set[str] = set()
    for line in what_shipped_lines:
        text = _line_to_item_text(line)
        if not text:
            continue
        key = _canonical_item(text)
        if not key or key in seen_keys:
            continue
        seen_keys.add(key)

        if key in commit_lookup:
            out.append(commit_lookup[key])
        elif key in changelog_lookup:
            out.append({"source": "changelog", "text": changelog_lookup[key]})
        else:
            out.append({"source": "derived", "text": text})

    return out


def build_structured_payload(
    *,
    schema_version: str,
    repo_name: str,
    base_ref: str,
    target_ref: str,
    range_spec: str,
    preset: str,
    destination: str,
    group_by: str,
    commits: list[Commit],
    changelog_items: list[str],
    render_data: dict[str, object],
    markdown: str,
) -> dict[str, object]:
    stats = dict(render_data["stats"])  # shallow copy
    return {
        "schema_version": schema_version,
        "repo": {"name": repo_name},
        "range": {
            "base_ref": base_ref or None,
            "target_ref": target_ref,
            "range_spec": range_spec,
        },
        "options": {
            "preset": preset,
            "destination": destination,
            "group_by": group_by,
        },
        "stats": {
            "raw_commit_count": len(commits),
            "selected_commit_count": len(commits),
            **stats,
        },
        "sections": {
            "title": render_data["title"],
            "what_shipped": render_data["what_shipped_lines"],
            "why_it_matters": (render_data["why_lines"] if bool(render_data.get("include_why", True)) else []),
            "links": render_data["links"],
        },
        "items": _build_structured_items(
            what_shipped_lines=list(render_data["what_shipped_lines"]),
            commits=commits,
            changelog_items=changelog_items,
        ),
        "markdown": markdown,
    }


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
    data = _build_render_data(
        repo_name=repo_name,
        commits=commits,
        changelog_items=changelog_items,
        base_ref=base_ref,
        target_ref=target_ref,
        repo_url=repo_url,
        release_url=release_url,
        group_by=group_by,
        title_template=title_template,
        include_validation=include_validation,
        include_links=include_links,
        include_why=True,
        max_bullets=max_bullets,
    )
    return _render_markdown_from_data(data)


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

    destination = getattr(args, "destination", None) or "release"
    if destination not in {"release", "update", "social", "internal"}:
        raise ValueError("destination must be one of: release, update, social, internal")

    default_title_template = _default_title_template(preset=preset, destination=destination)
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
        elif raw_commit_count > 0:
            if changelog_items:
                # all in-range commits are low-signal; avoid stale changelog carryover
                commits = []
                changelog_items = []
            # else: keep low-signal commits so output is not empty
        elif changelog_items:
            # no in-range commits, but changelog may still carry useful context
            commits = []

    repo_name = repo_path.name
    render_data = _build_render_data(
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
        include_why=bool(getattr(args, "with_why", False)),
        max_bullets=max_bullets,
    )
    markdown = _render_markdown_from_data(render_data)

    json_output = bool(getattr(args, "json", False))
    if json_output:
        payload = build_structured_payload(
            schema_version="1.0",
            repo_name=repo_name,
            base_ref=base_ref,
            target_ref=target_ref,
            range_spec=range_spec,
            preset=preset,
            destination=destination,
            group_by=group_by,
            commits=commits,
            changelog_items=changelog_items,
            render_data=render_data,
            markdown=markdown,
        )
        output_text = json.dumps(payload, indent=2, sort_keys=True)
    else:
        output_text = markdown

    if args.output:
        out_path = Path(args.output)
        if not out_path.is_absolute():
            out_path = repo_path / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text + ("\n" if json_output else ""), encoding="utf-8")
        print(f"Wrote draft: {out_path}")
        return 0

    print(output_text, end="" if not json_output else "\n")
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
    draft.add_argument(
        "--destination",
        choices=["release", "update", "social", "internal"],
        default="release",
        help="Destination tone/template hint for generated title and rationale",
    )
    draft.add_argument("--group-by", choices=["type", "scope"], default="type", help="Group commit bullets by type or scope")
    draft.add_argument("--max-bullets", type=int, help="Cap bullet lines in What shipped")
    draft.add_argument("--max-changelog-items", type=int, help="Cap changelog bullets considered for enrichment")
    draft.add_argument("--keep-low-signal", action="store_true", help="In short preset, keep low-signal release/admin commits")
    draft.add_argument("--title-template", help="Title template, supports {repo} placeholder")
    draft.add_argument("--no-validation", action="store_true", help="Skip Validation section")
    draft.add_argument("--no-links", action="store_true", help="Skip Links section")
    draft.add_argument("--with-why", action="store_true", help="Include Why it matters section (off by default)")
    draft.add_argument("--json", action="store_true", help="Emit structured JSON payload (includes markdown)")
    draft.add_argument("--output", help="Write output to a file (markdown by default, JSON with --json)")
    draft.set_defaults(func=cmd_draft)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
