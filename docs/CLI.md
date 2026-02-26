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
- `--include-scope <scope>`: only include commit scopes (repeatable, use `general` for unscoped commits)
- `--exclude-scope <scope>`: exclude commit scopes (repeatable, use `general` for unscoped commits)
- `--preset <short|standard>`: output style preset (`short` for concise updates, `standard` for fuller notes)
- `--destination <release|update|social|internal>`: destination tone/template hint
- `--group-by <type|scope>`: group commit bullets by type or conventional-commit scope
- `--max-bullets <n>`: cap bullet lines in `What shipped`
- `--max-changelog-items <n>`: cap changelog bullets used for enrichment
- `--keep-low-signal`: in `short` preset, keep release/admin commits that are filtered by default
- `--title-template <text>`: customize title (supports `{repo}` placeholder)
- `--no-validation`: skip Validation section
- `--no-links`: skip Links section
- `--json`: emit structured JSON payload (includes rendered markdown)
- `--output <path>`: write output to file (markdown by default, JSON with `--json`)

## Range behavior

- If `--since-commit` is set, range is `<since-commit>..HEAD`
- Else if `--since-tag` is set, range is `<since-tag>..HEAD`
- Else if a tag exists, range is `<latest-tag>..HEAD`
- Else fallback is `HEAD` (all reachable commits)

## Changelog behavior

- If `CHANGELOG.md` exists, bullets from the latest changelog section are merged into `What shipped` (deduplicated against commit-derived bullets).
- When the selected commit range has no commits, changelog enrichment is suppressed to avoid stale summaries.

## Short preset behavior

- `--preset short` defaults to tighter bullet budgets and omits `Validation`.
- It also filters common low-signal release/admin commits by default (e.g., docs devlog/changelog/release-notes updates and chore release/version/dependency/changelog maintenance).
- Use `--keep-low-signal` to disable that filter.
- If all in-range commits are filtered as low-signal, changelog carryover is suppressed to avoid stale summaries.
- If filtering would remove all commits and no changelog bullets exist, commit bullets are kept to avoid an empty draft.

## Structured output (`--json`)

Use `--json` to emit a stable machine-consumable payload for agents/tools.
The payload includes:
- `schema_version`
- `repo` + `range`
- `options` + `stats`
- `sections` (title / what_shipped / why_it_matters / links)
- `items` (commit/changelog-derived normalized entries)
- `markdown` (rendered draft)

## Examples

```bash
ship-note draft
ship-note draft --since-tag v0.1.0
ship-note draft --since-commit 8f2c2a1
ship-note draft --repo-url https://github.com/org/repo --release-url https://github.com/org/repo/releases/tag/v0.2.0
ship-note draft --include-type feat --include-type fix --exclude-type docs
ship-note draft --include-scope api --exclude-scope general --group-by scope
ship-note draft --preset short --group-by scope --title-template "# {repo} release notes"
ship-note draft --group-by scope --title-template "# {repo} release notes" --no-validation
ship-note draft --preset short --max-bullets 3 --max-changelog-items 2
ship-note draft --preset short --destination social
ship-note draft --preset short --keep-low-signal
ship-note draft --json
ship-note draft --json --output notes/devlog-draft.json
ship-note draft --output notes/devlog-draft.md
```
