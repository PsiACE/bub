---
name: gh
description: GitHub CLI skill for interacting with GitHub via the gh command line tool. Use when Bub needs to (1) Create, view, or manage GitHub repositories, (2) Work with issues and pull requests, (3) Create and manage releases, (4) Run and monitor GitHub Actions workflows, (5) Create and manage gists, or (6) Perform any GitHub operations via command line.
---

# GitHub CLI (gh) Skill

Interact with GitHub using the gh command line tool.

## Prerequisites

The GitHub PAT is available via `GITHUB_TOKEN` environment variable or `gh` CLI authentication.

Check authentication:
```bash
gh auth status
```

If not authenticated:
```bash
gh auth login
```

## Repository Operations

```bash
gh repo create <name> [--public|--private]
gh repo clone <owner/repo>
gh repo fork <owner/repo>
gh repo view [owner/repo]
gh repo list [owner]
```

## Issue Operations

```bash
gh issue create --title "Title" --body "Body"
gh issue list [--state open|closed]
gh issue view <number>
gh issue close <number>
gh issue comment <number> --body "Comment"
```

## Pull Request Operations

```bash
gh pr create --title "Title" --body "Body"
gh pr list [--state open|closed]
gh pr view <number>
gh pr checkout <number>
gh pr merge <number>
gh pr review <number> --approve
```

## Release Operations

```bash
gh release create <tag> --generate-notes
gh release list
gh release download <tag>
gh release upload <tag> <file>
```

## Workflow Operations

```bash
gh workflow list
gh workflow run <name>
gh run list
gh run view <run-id>
gh run watch <run-id>
```

## Gist Operations

```bash
gh gist create <file>
gh gist list
gh gist view <id>
```

## Tips

- Use --web to open in browser
- Use -R owner/repo to specify repository
- Use --json with --jq for scripting
