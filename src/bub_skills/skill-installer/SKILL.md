---
name: skill-installer
description: Install Bub skills into the shared skills directory from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos).
metadata:
  short-description: Install curated skills from openai/skills or other repos
---

# Skill Installer

Helps install skills. By default these are from https://github.com/openai/skills/tree/main/skills/.curated, but users can also provide other locations. Experimental skills live in https://github.com/openai/skills/tree/main/skills/.experimental and can be installed the same way.

Use `npx skills` based on the task:
- List skills when the user asks what is available, or if the user uses this skill without specifying what to do. Default listing is `.curated`, but you can pass `--path skills/.experimental` when they ask about experimental skills.
- Install from the curated list when the user provides a skill name.
- Install from another repo when the user provides a GitHub repo/path (including private repos).

## Install Location Policy

Use one of these roots for installed skills:

1. Project-local: `$workspace/.agent/skills/<skill-name>`
2. Global: `~/.agent/skills/<skill-name>` (shared across workspaces)

Prefer project-local for repo-specific workflows. Use global only when the user asks for cross-workspace availability.

## Communication

When listing skills, output approximately as follows, depending on the context of the user's request. If they ask about experimental skills, list from `.experimental` instead of `.curated` and label the source accordingly:
"""
Skills from {repo}:
1. skill-1
2. skill-2 (already installed)
3. ...
Which ones would you like installed?
"""

After installing a skill, tell the user: "Restart Bub to pick up new skills."

## Commands

All of these commands use network.

- List curated skills: `npx skills add openai/skills --list --skill '*' --agent antigravity --yes`
- List experimental skills: `npx skills add https://github.com/openai/skills/tree/main/skills/.experimental --list --skill '*' --agent antigravity --yes`
- Install curated skill (project-local): `npx skills add https://github.com/openai/skills/tree/main/skills/.curated/<skill-name> --agent antigravity --yes`
- Install curated skill (global): `npx skills add https://github.com/openai/skills/tree/main/skills/.curated/<skill-name> --agent antigravity --yes --global`
- Install from URL: `npx skills add https://github.com/<owner>/<repo>/tree/<ref>/<path> --agent antigravity --yes`
- Install from shorthand: `npx skills add <owner>/<repo>@<skill-name> --agent antigravity --yes`
- Show installed skills in current scope: `npx skills list`
- Show installed global skills: `npx skills list --global`

## Behavior and Options

- `npx skills add` handles discovery and installation directly.
- Use project scope by default; use `--global` for cross-workspace availability.
- Always pass `--agent antigravity` so install location matches Bub discovery (`.agent/skills`).
- Prefer non-interactive usage with `--yes` when you already know the target skill.

## Notes

- Curated/experimental listings are resolved by `npx skills add ... --list`.
- Private GitHub repos depend on `npx skills` auth support and your local git/npm credentials.
- The skills at https://github.com/openai/skills/tree/main/skills/.system are preinstalled, so no need to help users install those. If they ask, just explain this. If they insist, you can download and overwrite.
- Installed annotations come from `npx skills list` in the active scope.
