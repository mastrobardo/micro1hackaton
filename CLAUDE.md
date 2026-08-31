# ghostc — project instructions

Personal hackathon project. **Working memory lives in-repo at `./memory/*.md`**
(index: `./memory/MEMORY.md`). Do **not** write session notes to `~/.agent/memory.md`
or any other home-folder memory for this project — keep everything in the repo.

## Where things are

- **`docs/PROGRESS.md`** — running status, decision log, workflow diagram. Read first.
- **`docs/SESSION_TODO.md`** — the immediate next action + open questions.
- **`memory/`** — durable notes (one topic per file; `MEMORY.md` is the index).
- **`TODO.md`** — the full 16-phase long-term roadmap.

## Package layout

| package | role | may import |
|---|---|---|
| `ghostc/` | deterministic privacy compiler + `ghostc` CLI | stdlib, tree-sitter, rapidfuzz, networkx |
| `bridge/` | boundary-neutral plumbing (git forge, LLM client) | stdlib, `anthropic`, `langsmith` — **not** ghostc/client_agent/consultancy_agent |
| `client_agent/` | company-side LangGraph orchestrator (`ghostc-agent`) | `ghostc`, `bridge`, `consultancy_agent` |
| `consultancy_agent/` | external coding agent | `bridge` only — **never** `ghostc` or `client_agent` (enforced by `tests/test_boundary.py`) |

`ghostc-mcp` (`ghostc/mcp_server.py`) exposes the deterministic capabilities as MCP tools.

## Conventions

- Plan before acting; wait for confirmation on multi-file changes.
- The user owns commits — don't commit unless asked. Branch: `feat/00N_<slug>`.
- `pytest` must stay green from a clean checkout; heavy/LLM deps are optional extras
  (`[agents]`, `[mcp]`, `[semantic]`) and their tests `importorskip`.
- **When building or modifying a LangGraph graph, produce/update a mermaid diagram
  beside it** (`client_agent/graph.md`; `ghostc-agent print-graph` regenerates it).
