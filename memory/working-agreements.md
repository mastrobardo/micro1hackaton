---
name: working-agreements
description: How the user wants work done on this project
metadata:
  type: feedback
---

- **Plan before acting.** Output a numbered action plan and wait for explicit confirmation
  before creating or changing files. Re-confirm if the plan shifts mid-execution.
  **Why:** the user's global workflow rule, and this project moves in deliberate iterations.
  **How to apply:** propose, wait, then execute.

- **Never commit.** The user commits each iteration himself, framed as a changelog entry.
  **Why:** the hackathon is scored on an evidence-linked Improvement Changelog; he controls the
  iteration boundaries. **How to apply:** leave the working tree ready; do not run `git commit`
  or `git push`. `git init` / staging is fine only if asked.

- **Readable markdown trackers over the CLI todo list.** Keep `PROGRESS.md` and
  `SESSION_TODO.md` current; the user reads those, not the tool's todo panel.
  **How to apply:** update them as work progresses; put the next action + open questions in
  `SESSION_TODO.md`.

- **Private parallel repos.** The user tests the compiler against his own undisclosed
  TS/Terraform repos. Those and anything derived from them **must never enter the micro1
  submission**. **How to apply:** the public path uses only the MIT fixture + the fictional
  entity layer; keep private-repo paths out of committed files, configs, and docs.

- **Memory lives in-project** at `learn/hackaton/memory/` (not `~/.claude/...`). Index is
  `memory/MEMORY.md`.
