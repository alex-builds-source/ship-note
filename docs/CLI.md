# CLI

## Command

`ship-note draft`

Render a markdown devlog draft from git commit history.

## Options

- `--path <repo>`: repository path (default: current directory)
- `--since-tag <tag>`: base commit range from tag
- `--since-commit <ref>`: base commit range from commit/ref
- `--repo-url <url>`: include repository URL in links section
- `--release-url <url>`: include release URL in links section

## Range behavior

- If `--since-commit` is set, range is `<since-commit>..HEAD`
- Else if `--since-tag` is set, range is `<since-tag>..HEAD`
- Else if a tag exists, range is `<latest-tag>..HEAD`
- Else fallback is `HEAD` (all reachable commits)

## Examples

```bash
ship-note draft
ship-note draft --since-tag v0.1.0
ship-note draft --since-commit 8f2c2a1
ship-note draft --repo-url https://github.com/org/repo --release-url https://github.com/org/repo/releases/tag/v0.2.0
```
