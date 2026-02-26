# ship-note

Generate concise release/devlog drafts from git history and optional release metadata.

## Install (dev)

```bash
pip install -e .
```

## Quickstart

```bash
ship-note draft --path .
ship-note draft --since-tag v0.1.0
ship-note draft --since-commit HEAD~5
ship-note draft --preset short --group-by scope
ship-note draft --preset short --destination social
ship-note draft --preset short --max-bullets 3 --max-changelog-items 2
ship-note draft --with-why --destination internal
ship-note draft --json
ship-note draft --output notes/devlog-draft.md
```

## What it outputs

By default: deterministic markdown sections:
- Title
- What shipped (commit-derived bullets + optional CHANGELOG bullets)
- Validation
- Links

Optional section:
- Why it matters (`--with-why`)

Optional: structured JSON payload (`--json`) for agents/tools, including:
- schema/version metadata
- range/options/stats
- normalized item list
- section arrays + rendered markdown

## CLI docs

See `docs/CLI.md` for full options and behavior.

## Development

```bash
PYTHONPATH=src pytest -q
```

Security note: run `repo-preflight`/`gitleaks` before publishing.
