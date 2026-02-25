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
```

## What it outputs

Deterministic markdown sections:
- Title
- What shipped
- Why it matters
- Validation
- Links

## CLI docs

See `docs/CLI.md` for full options and behavior.

## Development

```bash
PYTHONPATH=src pytest -q
```

Security note: run `repo-preflight`/`gitleaks` before publishing.
