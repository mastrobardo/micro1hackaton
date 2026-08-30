# Working preferences (this project)

Durable how-to-work notes for `learn/hackaton/`. Corrections the user has given.

## Memory lives in the repo

Project memory is **`learn/hackaton/memory/*.md`** (index: `MEMORY.md`), not
`~/.agent/memory.md` or any home-folder store. "This is a personal project." Also
stated in `learn/hackaton/CLAUDE.md`.
**Why:** the repo is the single source of truth; home-folder notes drift and
aren't versioned with the code.

## Diagram every graph

When building or modifying a LangGraph (or any node/edge) graph, produce/update a
**mermaid diagram beside it** in the same change. For the client agent that's
`client_agent/graph.md`; `ghostc-agent print-graph` regenerates the auto version
from `client_agent/graph.py::_wire`.
**Why:** the user asked for it explicitly (2026-08-31); a graph's control flow
isn't reviewable from the node code alone.

## Package boundary is structural, not conventional

Agent code is split into top-level packages `client_agent/` (imports `ghostc`),
`consultancy_agent/` (**must not** import `ghostc`/`client_agent`), `bridge/`
(neither). The consultancy side's isolation is enforced by
`tests/test_boundary.py`, mirroring the eventual container split.
**Why:** the whole premise is that the external agent can't reach the mapping /
real repo — making that a module-import rule catches regressions early.

Related: [[agent-harness]], [[project-goal-and-status]].
