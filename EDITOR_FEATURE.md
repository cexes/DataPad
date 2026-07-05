# Editor Integration Feature

Allow users to set their preferred terminal editor (neovim, vim, vi, nano) to write queries, instead of the inline prompt.

## Config

Store preference in `~/.terminal_db/config.json`:

```json
{ "editor": "nvim" }
```

**Resolution order:**
1. `~/.terminal_db/config.json`
2. `$EDITOR` env var
3. `$VISUAL` env var
4. First available: `nvim` → `vim` → `vi` → `nano`

## CLI (`main.py` — prompt_toolkit)

New meta commands:

| Command | Description |
|---|---|
| `.editor` | Show current editor |
| `.editor nvim` | Set preferred editor |
| `.edit` | Open query buffer in editor, load back on exit |

**How `.edit` works:**
1. Write `query_buffer` content to a tempfile (`.sql` extension for syntax highlight)
2. `subprocess.call([editor, tempfile])` — editor takes over the terminal naturally
3. Read file back into `query_buffer`
4. If content ends with `;`, auto-execute (or leave for the user to decide)

No special terminal suspension needed — `prompt_toolkit` doesn't hold terminal state.

## TUI (`query_screen.py` — Textual)

Keybinding `Ctrl+E` on the `TextArea`:
1. `app.suspend()` context manager (Textual built-in for this exact use case)
2. Write `TextArea` content to tempfile
3. Open editor
4. Read back into `TextArea`

## Files to touch

- `src/terminal_db/config.py` — add `UserConfig` model with `editor` field + load/save from `~/.terminal_db/config.json`
- `src/terminal_db/main.py` — add `.editor` and `.edit` commands, load `UserConfig`
- `src/terminal_db/ui/query_screen.py` — add `Ctrl+E` keybinding + suspend/resume logic

---

## MCP Evolution

### The core pattern (editor + LLM)

```
user: "vendas do mês agrupadas por região"
  → LLM inspects schema via MCP (get_full_schema)
  → LLM generates SQL
  → SQL opens in user's editor (nvim) for review
  → user saves and exits → query executes
```

The editor becomes the **human review step** before execution. The LLM writes, the user adjusts, the DB runs.

### New MCP tools to implement

**Schema intelligence** — give the LLM enough context to write accurate queries:

| Tool | Description |
|---|---|
| `get_full_schema` | All tables + columns + types in one call |
| `search_schema` | Search by column or table name (useful on large schemas) |
| `get_relationships` | Foreign keys so the LLM understands JOINs |

**Query library** — reusable named queries:

| Tool | Description |
|---|---|
| `save_query` | Save a named query to `~/.terminal_db/queries/` |
| `load_query` | Load a saved query by name |
| `list_queries` | List all saved queries |

**Analysis:**

| Tool | Description |
|---|---|
| `explain_query` | Return execution plan before running |
| `sample_table` | Return N sample rows so the LLM understands data shape |

### Priority

**Editor integration and MCP are separate concerns — do not mix them.**

| Mode | Review step | Editor relevant? |
|---|---|---|
| CLI/TUI standalone | `.edit` opens nvim/vim/nano | Yes |
| MCP with LLM client | The chat itself | No |

When the user is working via MCP, the LLM client's chat is already the review interface. Spawning an editor from inside an MCP tool doesn't work — the server runs headless with no terminal ownership.

**Current focus: MCP context tools.**
The highest-value investment is giving the LLM enough schema context to generate accurate queries without guessing:

1. `get_full_schema` — first to implement, unlocks everything else
2. `get_relationships` — foreign keys so the LLM understands JOINs
3. `search_schema` — useful on large schemas
4. `sample_table` — LLM understands data shape before writing queries
5. `explain_query` — safety net before execution

Editor integration (CLI/TUI) is a separate, lower-priority track.
