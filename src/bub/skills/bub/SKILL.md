---
name: bub
description: Bub agent CLI for running sub-tasks and spawning child agent instances. Use when Bub needs to (1) Delegate a task to a sub-agent, (2) Run a one-off command in a separate session, (3) Execute tasks with different tools or skills enabled, or (4) Test or validate operations in an isolated context.
---

# Bub CLI Skill

Run sub-tasks using the `bub run` command to spawn child agent instances.

## Quick Start

```bash
# Run a simple task
bub run "List all Python files in the current directory"

# Run with specific workspace
bub run -w /path/to/workspace "Analyze the project structure"

# Run with specific model
bub run --model claude-3-opus "Write a summary of the codebase"
```

## Command Reference

### `bub run <message>`

Run a single message and exit. Useful for quick testing or one-off commands.

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `message` | Yes | The task/message to send to the agent |

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--workspace` | `-w` | Working directory path |
| `--model` | | Model to use (e.g., claude-3-opus, gpt-4) |
| `--max-tokens` | | Maximum tokens for response |
| `--session-id` | | Session identifier (default: cli) |
| `--tools` | | Allowed tool names (repeatable or comma-separated) |
| `--skills` | | Allowed skill names (repeatable or comma-separated) |

## Common Usage Patterns

### Delegate a Sub-task

```bash
bub run "Review the code in src/utils.py and suggest improvements"
```

### Run with Limited Tools

```bash
bub run --tools fs.read,fs.write "Create a hello.txt file with greeting"
```

### Run with Specific Skills

```bash
bub run --skills python,git "Analyze the Python project and create a README"
```

### Isolated Testing

```bash
bub run -w /tmp/test-workspace "Create a sample project structure"
```

## Running Long Tasks

For tasks that are expected to take a long time, run in background and schedule a check:

### Pattern: Background Execution with Scheduled Result Check

```bash
# 1. Run task in background, redirect output to file
nohup bub run "Perform extensive code analysis" > /tmp/bub_task_output.log 2>&1 &

# 2. Use schedule tool to check result later
# Schedule a reminder to check the output file after N seconds
```

### Example Workflow

```bash
# Step 1: Start long-running task in background
nohup bub run -w /workspace/big-project "Analyze all modules and generate documentation" > /tmp/doc_gen.log 2>&1 &
echo $! > /tmp/bub_task.pid

# Step 2: Schedule a check (using schedule.add tool)
# After 300 seconds, check if task is complete and report results

# Step 3: Check results when scheduled reminder triggers
cat /tmp/doc_gen.log
```

### Tips for Long Tasks

- Always redirect output to a file for later inspection: `> output.log 2>&1`
- Save the PID for process management: `echo $! > task.pid`
- Use `nohup` to prevent task termination on session disconnect
- Schedule result checks at reasonable intervals based on expected task duration

## Other Commands

| Command | Description |
|---------|-------------|
| `bub chat` | Run interactive CLI session |
| `bub telegram` | Run Telegram adapter with agent loop |

## Notes

- **Default behavior**: When `--session-id` and `--workspace` are not specified, child agents share the parent's session (same tape, same workspace)
- **Isolation**: To run child agents in isolation, explicitly set `--session-id` and/or `--workspace` to different values
- Use `--session-id` to correlate or group related runs
- Combine with `--tools` and `--skills` to limit child agent capabilities
