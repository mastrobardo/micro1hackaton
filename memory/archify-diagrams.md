# Archify diagrams (`docs/diagrams/`)

Session 11 (2026-09-01). The user asked for a diagram of the whole solution and named the
tool: **[archify](https://github.com/tt-a1i/archify)** (MIT, v2.17.0-dev.0, tt-a1i).

## What it is

A Node.js Agent Skill. The agent authors a **typed JSON IR**; `bin/archify.mjs`
deterministically compiles it into a self-contained interactive HTML/SVG artifact
(~710 KB, theme switching, pan/zoom, search, guided "views", PNG/SVG/WebM export).
Five diagram types: `architecture`, `workflow`, `sequence`, `dataflow`, `lifecycle`.

**Installed at `~/.claude/skills/archify/`** (copied from a shallow clone, not
`npx skills add`, so the contents were inspectable first). Needs Node ≥18 (have v22)
and **no `npm install`** — the `devDependencies` are for the project's own tests, not
for rendering. `node bin/archify.mjs doctor` verifies.

## The three-command contract

```
validate <type> <spec.json> --quality showcase --json   # repair loop; 9/9 checks, 0 errors, 0 warnings
deliver  <type> <spec.json> <out.html> --quality showcase --json  # final acceptance, freezes + hashes
visual-check <out.html> --json                          # real Chrome, 1440x900 → 2048x1320, light+dark
```

`deliver` and `visual-check` are **separate claims**: `deliver` proves deterministic artifact
checks, `visual-check` proves browser containment/readability, and perceptual review is a
third thing (read the emitted PNGs). A 4-check receipt is basic validation, not showcase.

## What we generated

| file | type | what it shows |
|---|---|---|
| `docs/diagrams/ghostc.architecture.json` → `ghostc-architecture.html` | architecture | 12 components across the company trust boundary / the `bridge.forge` wire / the external side; `tag` on each node names the owning **package** (`ghostc/`, `bridge/`, `client_agent/`, `consultancy_agent/`) |
| `docs/diagrams/ghostc.workflow.json` → `ghostc-workflow.html` | workflow (schema v2) | the LangGraph `run-task` round trip as a serpentine: outbound lane `plan → compile_spec → screen → handoff`, an **exception lane** for fail-closed, the external lane, then the return lane `await_ghost_pr → … → emit_metrics` |

`*.visual-check.*` PNG/JSON/HTML beside them are browser evidence sidecars — regenerable,
reasonable candidates for `.gitignore`.

## Lessons that cost real iterations

- **The gutter between two adjacent columns is a scarce resource.** Any long orthogonal edge
  that has to change rows fights every short edge crossing the same gutter. Put the loop-closing
  node (`real_repo`) and the node that returns to it (`verify`) in the **same column**, so the
  return edge is a clean vertical through an empty grid slot. That one change removed every
  `composition/proper-crossing` error.
- **Labels are geometry.** ~135px of label text does not fit an 80px column gap. The validator
  emits the exact fix (`labelDy +56`, `labelAt [x,y]`) — apply it verbatim rather than guessing.
- **`composition/desktop-readability` vs `viewer/viewport-overflow` pull in opposite
  directions.** Readability wants a *narrow* viewBox (node text projects at `sourceFontPx ×
  930/viewBoxWidth`, min 6px, and `sourceFontPx` caps at 8). Containment wants a *wide* one
  (rendered height = `viewBoxHeight × 930/viewBoxWidth`). The move that satisfies both is to
  **shorten copy and compress the Y layout**, not to widen the box.
- Workflow **lane count sets the height** and node `height` barely matters
  (`52 + lanes×104 + (lanes−1)×20 + 124`). To fit 900px with 4 lanes, the page chrome had to
  shrink instead — tightening card copy did it.
- `col` is capped at **0..5**, so a 10-node round-trip pipeline does not fit one lane. The
  serpentine (outbound L→R on top, return R→L at the bottom) is the right shape; set
  `mainPath` over the outbound half only, since it lints for left-to-right movement.
- `semanticChecks` (`allowedRoots` / `allowedTerminals` / `requiredEdges` / `requiredPaths`)
  encodes domain truth the layout checker cannot infer. We pinned `plan` as the only root and
  `compile_spec → screen → handoff` as required edges — the two-gates claim is now
  machine-checked in the spec, not just asserted in a card.

## Regenerating

```bash
cd ~/.claude/skills/archify
node bin/archify.mjs deliver architecture <repo>/docs/diagrams/ghostc.architecture.json \
     <repo>/docs/diagrams/ghostc-architecture.html --quality showcase --json
node bin/archify.mjs deliver workflow     <repo>/docs/diagrams/ghostc.workflow.json \
     <repo>/docs/diagrams/ghostc-workflow.html --quality showcase --json
```

Edit the **JSON**, never the HTML. See [[working-preferences]] — this sits alongside the
mermaid rule for LangGraph graphs (`client_agent/graph.md` stays the generated source of
truth for the graph topology; these diagrams are the presentation layer over it).
