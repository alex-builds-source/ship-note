# CLI

## Command

`ship-note draft`

Render a markdown devlog draft from git commit history, optionally enriched with `CHANGELOG.md` bullets.

## Options

- `--path <repo>`: repository path (default: current directory)
- `--since-tag <tag>`: base commit range from tag
- `--since-commit <ref>`: base commit range from commit/ref
- `--repo-url <url>`: include repository URL in links section
- `--release-url <url>`: include release URL in links section
- `--include-type <type>`: only include commit types (repeatable)
- `--exclude-type <type>`: exclude commit types (repeatable)
- `--group-by <type|scope>`: group commit bullets by type or conventional-commit scope
- `--title-template <text>`: customize title (supports `{repo}` placeholder)
- `--no-validation`: skip Validation section
- `--no-links`: skip Links section
- `--output <path>`: write rendered markdown to file instead of stdout

## Range behavior

- If `--since-commit` is set, range is `<since-commit>..HEAD`
- Else if `--since-tag` is set, range is `<since-tag>..HEAD`
- Else if a tag exists, range is `<latest-tag>..HEAD`
- Else fallback is `HEAD` (all reachable commits)

## Changelog behavior

- If `CHANGELOG.md` exists, top bullet items are merged into `What shipped` (deduplicated against commit-derived bullets).

## Examples

```bash
ship-note draft
ship-note draft --since-tag v0.1.0
ship-note draft --since-commit 8f2c2a1
ship-note draft --repo-url https://github.com/org/repo --release-url https://github.com/org/repo/releases/tag/v0.2.0
ship-note draft --include-type feat --include-type fix --exclude-type docs
ship-note draft --group-by scope --title-template "# {repo} release notes" --no-validation
ship-note draft --output notes/devlog-draft.md
```
