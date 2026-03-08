# Bub

Bub is a common shape for agents.

It exists to answer a harder question than "can an agent finish a task?":
when many humans and agents work in the same environment, what kind of agent remains understandable, reviewable, and safe to continue?

Bub's answer is an agent form with explicit boundaries, visible evidence, and safe handoff.
The current repository is one implementation of that idea, using hook-based composition, [Republic](https://github.com/bubbuild/republic) as the context runtime, and [constructing context from tape](https://tape.systems) as the current context model.

## Quick Start

Install dependencies and create local config:

```bash
git clone https://github.com/bubbuild/bub.git
cd bub
uv sync
cp env.example .env
```

Run interactive local chat:

```bash
uv run bub chat
```

Run a one-shot task:

```bash
uv run bub run "summarize this repository"
```

Start channel listener mode:

```bash
uv run bub gateway
```

## Deployment

For production setup and operations, read:

- [Deployment Guide](deployment.md)
- [Channels Overview](channels/index.md)
- [Telegram Channel](channels/telegram.md)

## Read Next

- [Core Overview](core/index.md): architecture and capability summary in one place
- [Workflows Overview](workflows/index.md): CLI and skills usage in one place
- [Extension Guide](extension-guide.md): build and publish hook-based extensions
- [Posts](posts/index.md): project notes and updates
