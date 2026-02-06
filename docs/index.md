# Bub

Bub is a tape-native CLI and runtime for human + agent workflows. It unifies commands and natural language into a single input line, while keeping behavior predictable and shell-friendly.

**Philosophy**
- Tape-first: the session is a single append-only tape.
- Unified input: `$` is an intent marker, not a mode switch.
- Human + agent parity: the same commands and tools are available to both.
- Async-first: input and response are decoupled like IM.
- Shell-native: designed to live inside a terminal prompt.

**Quick Start**
- Install:
```bash
pip install bub
```
- Setup:
```bash
export BUB_MODEL="openai:gpt-4o-mini"
export BUB_API_KEY="sk-..."
```
- Usage:
```bash
# Interactive session (async)
bub chat
```

**Interaction Model**

**Unified Input**
- `$` can appear at line start or after whitespace.
- Commands and text share the same line.
- Bub scans left-to-right, segments commands, and executes them in order.

```bash
# Internal commands
$tape.info
$tape.search query=handoff
$handoff name=handoff/2026-02-05 summary="Reset scope"

# Shell commands
$git status
$ rg "TODO" src

# Mixed input (command output feeds the agent)
summarize $tape.anchors --limit 3
```

**Routing Rules**
- Command resolution order: internal tools, then shell commands, then fallback to text.
- Shell commands are executed through the `bash` tool for consistent logging.
- File tools use the `fs.*` prefix to avoid shadowing shell commands.
- Tool names still take precedence; to force a shell command, use `$bash <command>`.
- Tool arguments support `key=value`, `--key=value`, `--key value`, and boolean `--flag`. Positional args are only used by `$bash` and `$bub`.
- If a value starts with `-`, use `key=-value` or `--key=-value` to avoid ambiguity.
- If a command is ambiguous or fails, Bub falls back to the agent by default.
- If a line contains only a command and it succeeds, Bub returns the result without entering the agent.
- When commands appear with surrounding text, Bub executes commands first and passes `<cmd ...>` result blocks to the agent.

**Assistant Loop (Agent-Decided Stop)**
- Assistant output is parsed with the same `$` rules.
- If the assistant emits commands, Bub executes them and feeds `<cmd ...>` results back to the agent.
- If the assistant returns plain text without follow-up commands, Bub ends the loop for that turn.
- The loop also stops when the assistant outputs `$done` or when the max-steps guard is reached.
- Default max steps per turn: `100`.
- `$done` should appear on its own line and is stripped from the UI view.

**Tool Observation Contract**
- Function-tool observations are returned as JSON strings with keys:
  - `tool`: called tool name.
  - `signature`: stable signature from tool name + normalized arguments.
  - `category`: one of `verification` or `operation`.
  - `status`: one of `ok`, `error`, `stagnant`.
  - `repeat`: whether this observation repeats a prior identical observation for the same signature.
  - `machine_readable`: structured value for model-side reasoning (`format=json|text`, plus `value`).
  - `human_preview`: concise preview string for readable summarization.
- `status=stagnant` means repeated calls produced no new information.
- On `stagnant`, the agent should stop repeating the same call and provide a final answer or explicit blocker.
- If user intent explicitly requests verification, the assistant should prefer including successful
  `category=verification` tool results before declaring completion.

**Async-First UX**
- Input does not block on agent completion.
- Messages arrive as they are appended to the tape, like IM.
- Tool traces are hidden by default and visible when `$debug` is enabled.

**Tape Lanes**
- Bub keeps a single tape with lane metadata.
- Lane `main`: human + agent messages and anchors (the UI timeline).
- Lane `work`: tool calls, tool results, and assistant-executed commands.
- Lane `control`: hidden loop markers and internal routing messages.

**UI/UX Expectations (Deterministic View)**
- User input appears immediately in the timeline as a `user` message.
- A line that is only a command shows command output and does not enter the agent.
- A line with both text and commands executes commands first, then sends `<cmd ...>` blocks to the agent.
- Agent responses appear as they are produced, in order.
- Assistant `$done` is not shown in the timeline.
- Tool calls and tool results are hidden unless `$debug` is enabled.
- Commands executed by the assistant are hidden unless `$debug` is enabled.
- Anchors render as compact markers in the timeline.

**Help Output (Programmatic Groups)**
- Groups are derived from the command prefix before the first dot.
- Commands without a dot are grouped under `Core`.
```text
Core
  $debug         Toggle debug
  $done          End the agent run
  $handoff       Create handoff anchor
  $help          Show available commands
  $quit          End the session
  $status        Show unified status panel
  $tools         Show available tools

FS
  $fs.edit       Edit file contents
  $fs.glob       List files by glob
  $fs.grep       Search file contents
  $fs.read       Read file contents
  $fs.write      Write file contents

Tape
  $tape.anchors  List tape anchors
  $tape.info     Show tape summary
  $tape.reset    Reset tape
  $tape.search   Search tape entries

Shell
  $<command>      Run a shell command via bash
```

**Status Views (Always Available)**
- Timeline view: the default stream (lane `main` only).
- Debug view: timeline + work lane (`$debug` toggles).
- Audit view: on-demand queries with `tape.info`, `tape.search`, and `tape.anchors`.

**Interaction Flows (ASCII)**

Command-only input:
```text
User Input
  |
  v
Router -----> Command Exec -----> Tape (lane=main)
  |                                   |
  |                                   v
  +------------------------------> UI View
```

Mixed input (text + commands):
```text
User Input
  |
  v
Router -----> Command Exec -----> Tape (lane=work)
  |                                   |
  |                                   v
  |                          <cmd ...> blocks
  |                                   |
  v                                   v
Agent Worker --------------------> Tape (lane=main)
  |
  v
UI View
```

Async agent loop with $done:
```text
User Input
  |
  v
Tape (lane=main) -----> Agent Worker -----> Assistant Output
                                |                |
                                |                v
                                |          Route Assistant
                                |                |
                                |                v
                                |          Command Exec
                                |                |
                                |                v
                                |         Tape (lane=work)
                                |                |
                                +----------------+
                                |
                                v
                              $done
                                |
                                v
                              Stop
```

Debug view toggle:
```text
$debug
  |
  v
Command Exec -----> Tape (lane=control)
  |
  v
UI View (toggle work lane visibility)
```

Parallel tasks (async interleaving):
```text
User A -----------------------> Tape (main)
                                   |
Agent Loop A ----> work events -----+-----+--> UI (main)
                                   |     |
User B -----------------------> Tape (main)
                                   |
Agent Loop B ----> work events -----+-----+
```

Status panel (ASCII, via `$status`):
```text
┌─────────────────────────────────────────────┐
│ Bub Status                                  │
├─────────────────────────────────────────────┤
│ Active Loops: 2                             │
│ - loop#7 (last: 12s ago)                    │
│ - loop#8 (last: 3s ago)                     │
│                                             │
│ Recent Anchors                              │
│ - handoff/2026-02-05  summary=Reset scope   │
│ - phase:execute     summary=Implement CLI   │
│                                             │
│ Recent Commands (debug)                     │
│ - $git status    ok    120ms                │
│ - $tape.search   ok     12ms                │
└─────────────────────────────────────────────┘
```

**Anchor State Keys**
- `summary`: short description of the current state.
- `next_steps`: short list or sentence of what to do next.
- Extra keys are allowed but not required.

**Session Controls**
- `$quit` ends the session.
- `$done` ends the current agent run.
- `$debug` toggles tool trace visibility.
- `$help` shows human-visible commands.
- `$tools` shows the full tool list (agent-visible).
- `$status` shows the unified status panel.

**In-Session `bub chat`**
- Nested sessions are not supported.
- `$bub chat` inside a session returns a short notice and suggests `tape.reset` or `handoff`.

**Command Reference (Core)**

| Command | Syntax | Purpose | Visibility | Route | Fallback |
| --- | --- | --- | --- | --- | --- |
| `tape.info` | `$tape.info` | Show tape summary | Human + Agent | Tool | Yes |
| `tape.search` | `$tape.search query=<q>` | Search tape entries | Human + Agent | Tool | Yes |
| `tape.anchors` | `$tape.anchors` | List anchors | Human + Agent | Tool | Yes |
| `tape.reset` | `$tape.reset [--archive]` | Reset tape | Human + Agent | Tool | Yes |
| `handoff` | `$handoff --summary ...` | Create handoff anchor | Human + Agent | Tool | Yes |
| `status` | `$status` | Show unified status panel | Human + Agent | Tool | Yes |
| `help` | `$help` | Show available commands | Human + Agent | Tool | Yes |
| `tools` | `$tools` | Show tool list | Human + Agent | Tool | Yes |
| `shell` | `$<command>` | Run shell command | Human + Agent | Tool | Yes |
| `quit` | `$quit` | End the session | Human | Tool | No |
| `done` | `$done` | End the agent run | Human + Agent | Control | No |
| `debug` | `$debug` | Toggle debug | Human | Tool | No |

**Command Reference (Advanced, Hidden in `$help`)**

| Command | Syntax | Purpose | Notes |
| --- | --- | --- | --- |
| `fs.read` | `$fs.read path=... [--offset N --limit N]` | Read file contents | File tool |
| `fs.write` | `$fs.write path=... --content "..."` | Write file contents | File tool |
| `fs.edit` | `$fs.edit path=... --old "..." --new "..." [--all]` | Edit file contents | File tool |
| `fs.glob` | `$fs.glob --pattern "*.py" [--path .]` | List files by glob | File tool |
| `fs.grep` | `$fs.grep --pattern "TODO" [--path .]` | Search file contents | File tool |
| `bash` | `$bash <command>` | Run a shell command explicitly | Use to bypass tool shadowing |

**Tape and Persistence**
- Each workspace has a dedicated tape file identified by a stable workspace hash.
- `handoff` creates a named anchor for context transfer and session boundaries.
- `tape.reset --archive` rotates the tape file into a timestamped archive.
- Commands, tool calls, and tool results are recorded with lane metadata.

**Configuration**

| Variable | Description | Example |
| --- | --- | --- |
| `BUB_MODEL` | Model identifier (provider:model) | `openai:gpt-4o-mini` |
| `BUB_API_KEY` | API key for provider (not required for local providers) | `sk-...` |
| `BUB_API_BASE` | Custom API endpoint | `https://api.custom.ai` |
| `BUB_MAX_TOKENS` | Maximum response tokens | `4000` |
| `BUB_WORKSPACE_PATH` | Default workspace directory | `/path/to/work` |
| `BUB_SYSTEM_PROMPT` | Custom system prompt | `"You are a helpful assistant..."` |
| `BUB_HOME` | Bub home directory | `~/.bub` |

**Custom System Prompt with AGENTS.md**
- Bub uses `AGENTS.md` from the closest workspace parent as the system prompt when present.

**Tooling**
- Bub exposes tools for file operations, shell execution, and tape management.
- Humans and agents share the same runnable tools.
- `$help` is curated for human readability; advanced commands remain available by name.
