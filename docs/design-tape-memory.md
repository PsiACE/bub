# Design: Tape-Native Memory System

> Status: **Implemented** (Phase 1–2 complete)
> Date: 2026-02-10

---

## 1. Motivation

nanobot uses an independent `MemoryStore` backed by the filesystem (`memory/YYYY-MM-DD.md` + `MEMORY.md`). While simple, this design is disconnected from the tape — memories cannot be replayed, do not participate in anchor semantics, and cannot be queried through tape search.

Bub already has an **append-only tape** as its core infrastructure. The goal is to **embed memory as a "zone" inside the tape**, sharing the same JSONL stream as the conversation, addressable via anchor pointers, and automatically injected into the LLM system prompt.

---

## 2. Architecture Context

### 2.1 Tape Data Model

```
TapeEntry(id, kind, payload, meta)
```

- `kind` discriminates entry types: `message`, `tool_call`, `tool_result`, `anchor`, `event`
- Tape is **append-only JSONL**, one per workspace
- **Anchor/Handoff** entries mark phase boundaries (milestones)

### 2.2 TapeService Key Capabilities

| Method | Purpose |
|---|---|
| `append_event(name, data)` | Append an event entry |
| `append_system(content)` | Append a system message |
| `handoff(name, state)` | Write an anchor with optional state |
| `from_last_anchor(kinds)` | Query from the last anchor forward |
| `after_anchor(name, kinds)` | Query after a named anchor |
| `between_anchors(start, end, kinds)` | Query between two anchors |
| `search(query, limit)` | Full-text search across entries |

### 2.3 Context Selection (used by ModelRunner)

`TapeContext.select` converts tape entries into LLM messages. The current implementation only processes `message` / `tool_call` / `tool_result` kinds — memory events are intentionally excluded from the conversation history and instead injected as a dedicated `<memory>` block in the system prompt.

### 2.4 Session Lifecycle

```
AppRuntime.get_session(session_id)
  → TapeService(llm, tape_name)
  → tape.ensure_bootstrap_anchor()   # writes "session/start" anchor
  → tape.memory.ensure()             # ensures memory zone exists
  → ModelRunner(tape, router, ...)
  → AgentLoop(router, model_runner, tape)
```

---

## 3. Design

### 3.1 Core Idea: Memory Zone = Anchor-Delimited Region

A pair of special anchors marks the memory zone inside the tape:

```
┌──────────────────────────────────────────────────────────┐
│  tape (append-only JSONL)                                │
│                                                          │
│  [anchor] session/start                                  │
│  [anchor] memory/open  ◄── zone start pointer            │
│  [event]  memory.long_term  { content: "..." }           │
│  [event]  memory.daily      { date: "2026-02-10", ... }  │
│  [event]  memory.daily      { date: "2026-02-09", ... }  │
│  [anchor] memory/seal  ◄── zone end pointer              │
│  [message] user: "hello"                                 │
│  [tool_call] ...                                         │
│  [message] assistant: "..."                              │
│  ...                                                     │
└──────────────────────────────────────────────────────────┘
```

**Key rules:**

1. **`memory/open` anchor** — marks the start of the memory zone
2. **`memory/seal` anchor** — marks the end (temporarily frozen)
3. Each anchor carries `state={"version": N}` for precise identification
4. **Updates** append a *new* versioned pair at the end of the tape (append-only rewrite); the old zone is naturally superseded
5. **Reads** find the highest-version `memory/seal`, walk backwards to the matching `memory/open`, and parse the entries between them

### 3.2 Memory Entry Types

Two event kinds:

#### `memory.long_term` — Persistent preferences and facts

```json
{
  "id": 42,
  "kind": "event",
  "payload": {
    "name": "memory.long_term",
    "data": {
      "content": "User prefers Python 3.12. Always use type hints.",
      "updated_at": "2026-02-10T10:00:00+00:00"
    }
  },
  "meta": {}
}
```

#### `memory.daily` — Daily work notes

```json
{
  "id": 43,
  "kind": "event",
  "payload": {
    "name": "memory.daily",
    "data": {
      "date": "2026-02-10",
      "content": "# 2026-02-10\n\n- Implemented tape memory zone\n- Fixed model_runner tests",
      "updated_at": "2026-02-10T10:05:00+00:00"
    }
  },
  "meta": {}
}
```

### 3.3 Memory Lifecycle

```
Session Start
    │
    ▼
ensure_bootstrap_anchor()          # existing logic
    │
    ▼
tape.memory.ensure()               # create empty zone if none exists,
    │                                 otherwise load latest snapshot
    ▼
_render_system_prompt()            # injects <memory> block into system prompt
    │                                 with usage hints + today/recent split
    ▼
Agent Loop (conversation proceeds normally)
    │
    ├─ user: "remember: I prefer dark mode"
    │   → tool call: memory_save(content="...")
    │   → internally: _bump_and_write(snapshot)
    │
    ├─ LLM autonomously notices important context
    │   → tool call: memory_save / memory_daily
    │   (guided by runtime_contract rule 7)
    │
    ├─ user: "what did we do yesterday?"
    │   → tool call: memory_recall(days=2)
    │   → reads from in-memory snapshot
    │
    ▼
Session End / Handoff
    │
    ▼
(zone persists in tape; next session auto-recovers)
```

### 3.4 Update Strategy: Append-Only Rewrite

Because the tape is append-only, "updating" memory means appending a new zone:

```python
def _write_zone(self, snap: MemorySnapshot) -> None:
    self._tape.handoff("memory/open", state={"version": snap.version})

    if snap.long_term:
        self._tape.append_event("memory.long_term", {
            "content": snap.long_term,
            "updated_at": _utc_now_iso(),
        })

    for daily in snap.dailies:
        self._tape.append_event("memory.daily", {
            "date": daily.date,
            "content": daily.content,
            "updated_at": _utc_now_iso(),
        })

    self._tape.handoff("memory/seal", state={"version": snap.version})
```

Reading finds only the latest pair:

```python
def _load_snapshot(self) -> MemorySnapshot | None:
    entries = self._tape.read_entries()
    seal_index, best_version = self._find_latest_seal(entries)
    if seal_index is None:
        return None
    open_index = self._find_matching_open(entries, seal_index, best_version)
    if open_index is None:
        return None
    return self._parse_zone_entries(entries[open_index + 1 : seal_index], best_version)
```

### 3.5 System Prompt Injection

The `<memory>` block is injected into the system prompt by `ModelRunner._render_system_prompt()`:

```xml
<memory>
Use `memory.save` to update long-term memory, `memory.daily` to append to
daily notes, and `memory.recall` to search past memories.

## Long-term Memory
User prefers Python 3.12. Always use type hints.

## Today's Notes
# 2026-02-10

- Implemented tape memory zone

## Recent Notes
### 2026-02-09
# 2026-02-09

- Designed memory architecture
</memory>
```

Key design choices influenced by nanobot's `ContextBuilder`:

- **Usage hints** are included so the LLM knows *how* to interact with memory
- **Today's notes** are separated from **recent history** (last 7 days, excluding today)
- **Current date/time** is injected via `_runtime_contract()` so the LLM knows "today"
- **Rule 7** in the runtime contract instructs the LLM to proactively save user preferences

---

## 4. Module Layout

### 4.1 Files

| File | Contents |
|---|---|
| `src/bub/tape/memory.py` | `MemoryZone`, `MemorySnapshot`, `DailyNote` |
| `src/bub/tape/service.py` | `TapeService.memory` property (lazy init) |
| `src/bub/tape/__init__.py` | Re-exports `MemoryZone`, `MemorySnapshot`, `DailyNote` |
| `src/bub/tools/builtin.py` | 5 tools: `memory.save`, `.daily`, `.recall`, `.show`, `.clear` |
| `src/bub/core/model_runner.py` | `<memory>` block injection + date in runtime contract |
| `src/bub/app/runtime.py` | `tape.memory.ensure()` on session start |
| `tests/test_tape_memory.py` | 21 tests covering snapshot ops and zone lifecycle |

### 4.2 MemoryZone API

```python
class MemoryZone:
    def __init__(self, tape: TapeService, *, retention_days: int = 30) -> None: ...

    # Read
    def ensure(self) -> None: ...
    def read(self) -> MemorySnapshot: ...
    def get_context(self) -> str: ...

    # Write
    def save_long_term(self, content: str) -> None: ...
    def append_daily(self, content: str, date: str | None = None) -> None: ...
    def clear(self) -> None: ...
    def prune(self) -> int: ...
```

### 4.3 Registered Tools

| Tool | Description | Input |
|---|---|---|
| `memory.save` | Replace long-term memory | `content: str` |
| `memory.daily` | Append to daily notes | `content: str`, `date?: str` |
| `memory.recall` | Recall memories with optional search | `query?: str`, `days: int = 7` |
| `memory.show` | Show memory zone summary | _(none)_ |
| `memory.clear` | Clear all memory | _(none)_ |

---

## 5. Tape Data Flow Examples

### 5.1 Initial State (empty memory)

```
#0  [anchor] session/start  state={"owner": "human"}
#1  [anchor] memory/open    state={"version": 1}
#2  [anchor] memory/seal    state={"version": 1}
#3  [message] user: "hello"
#4  [message] assistant: "Hi! How can I help?"
```

### 5.2 User says "remember: I like Python"

```
#0  [anchor] session/start
#1  [anchor] memory/open    state={"version": 1}   ← old zone (ignored)
#2  [anchor] memory/seal    state={"version": 1}   ← old zone (ignored)
#3  [message] user: "hello"
#4  [message] assistant: "Hi!"
#5  [message] user: "remember: I like Python"
#6  [tool_call] memory_save(content="User likes Python")
#7  [tool_result] "saved to long-term memory"
#8  [anchor] memory/open    state={"version": 2}   ← current zone
#9  [event]  memory.long_term {content: "User likes Python"}
#10 [anchor] memory/seal    state={"version": 2}   ← current zone
#11 [message] assistant: "Got it, I'll remember that!"
```

### 5.3 Next day: appending a daily note

```
... (previous entries) ...
#20 [anchor] memory/open    state={"version": 3}
#21 [event]  memory.long_term {content: "User likes Python"}
#22 [event]  memory.daily {date: "2026-02-09", content: "..."}
#23 [event]  memory.daily {date: "2026-02-10", content: "..."}
#24 [anchor] memory/seal    state={"version": 3}
```

---

## 6. Comparison with nanobot MemoryStore

| Dimension | nanobot MemoryStore | Bub MemoryZone |
|---|---|---|
| Storage | Separate filesystem (`memory/*.md`) | Tape-embedded zone (JSONL entries) |
| Consistency | Disconnected from conversation | Same tape — auditable and replayable |
| Addressing | File paths | Anchor pointers + version matching |
| Mutation | In-place file writes | Append-only zone rewrite |
| Context injection | Manual system prompt assembly | Automatic `<memory>` block with usage hints |
| Persistence | Filesystem | Tape (JSONL file) |
| Cross-session | Requires manual management | Native — same tape across sessions |
| Search | None | Reuses `tape.search` |
| LLM guidance | Embeds memory path in identity prompt | Runtime contract rule 7 + usage hints in `<memory>` |
| Today vs history | `read_today()` separate method | `get_context()` splits Today's Notes / Recent Notes |

---

## 7. Edge Cases and Considerations

### 7.1 Memory Zone Growth Control

- **Daily retention**: configurable via `retention_days` (default 30). Pruning is explicit via `zone.prune()`, not automatic on every write.
- **Long-term memory size**: recommended < 4KB. The LLM can summarize and update via `memory.save`.
- **Old zone garbage**: naturally cleaned up by `tape.archive()`.

### 7.2 Concurrency Safety

- `FileTapeStore` has a `threading.Lock`; memory operations go through tape writes.
- Single session = single thread. No concurrent memory writes.

### 7.3 Behavior on `tape.reset`

- `tape.reset()` clears the entire tape including the memory zone.
- `tape.reset(archive=True)` archives first, then clears.
- After reset, `tape.memory.ensure()` recreates an empty zone.

### 7.4 Backward Compatibility

- Old tapes without a memory zone: `ensure()` creates an empty zone — non-destructive.
- New event kinds (`memory.long_term`, `memory.daily`) are invisible to existing context selection logic, which only processes `message/tool_call/tool_result`.

---

## 8. Implementation Status

### Phase 1: Infrastructure ✅

1. `src/bub/tape/memory.py` — `MemoryZone`, `MemorySnapshot`, `DailyNote`
2. `TapeService.memory` lazy property
3. `tape.memory.ensure()` called on session start
4. `tests/test_tape_memory.py` — 21 tests

### Phase 2: Tool & Prompt Integration ✅

5. `builtin.py` — `memory.save`, `memory.daily`, `memory.recall`, `memory.show`, `memory.clear`
6. `model_runner.py` — `<memory>` block injection with usage hints, today/history split
7. `_runtime_contract()` — current date/time injection + rule 7 (proactive memory saving)
8. Model runner tests updated for `FakeMemoryZone`

### Phase 3: Future Enhancements 🔜

9. Auto-prune on session start (call `zone.prune()` in `ensure()`)
10. Memory export before `tape.reset` (backup to standalone file)
11. `memory.forget` tool — remove specific entries by rewriting without them
12. Cross-session shared memory (workspace-level "shared memory tape")

---

## 9. Open Questions

1. **Should memory be shared across sessions within the same workspace?**
   Current design: each tape has its own memory zone. A workspace-level "shared memory tape" could be introduced if needed.

2. **Version upper bound?**
   Theoretically unbounded. In practice, rewrites happen only on explicit save/daily calls — a typical session stays well under 100 versions.

3. **Should pruning be automatic?**
   Currently explicit (`zone.prune()`). Could be triggered on session start to keep zone size bounded.
