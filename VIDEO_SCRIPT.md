# Solution video — script

Target length **≤ 5:00**. The brief wants: problem + baseline → one realistic execution
start-to-finish → the final comparison → the changelog in brief → the change that contributed
most + one experiment removed → hot take.

Two columns: **screen** = what's visible / what you do, **narration** = read aloud (or feed to
a voiceover). Times are cumulative targets.

---

## Record these before you hit record

1. A terminal with the venv active, `pytest -q` already green (paste the summary line on
   screen when you mention it).
2. `./scripts/demo-webapp.sh` already run once so `../ghostc-demo/{real,ghost}` exist and both
   servers are up — have **:3000** and **:3001** open in two browser windows.
3. A completed `client-agent start 001-add-companyx-integration --consultancy-backend claude`
   **and** `client-agent open-real-pr 001-add-companyx-integration` run, so you can show:
   - `git -C ../ghostc-demo/ghost log --stat ghostc/task/001-add-second-provider`
   - `git -C ../ghostc-demo/real log --stat ghostc/real/001-add-companyx-integration`
   - `cat workspace/eval-report.md`
   - `cat metrics/agent-runs.jsonl | tail -3`
4. `CHANGELOG.md` open in the editor, scrolled to the progression table.

Do the live typing for the *reverse-compile* step only (it's fast and deterministic);
everything slow is pre-run and you just scroll the output.

---

## 0:00 – 0:45 · The problem and the baseline

| Screen | Narration |
|---|---|
| Title card: "ghostc — a privacy-safe bridge for external AI coding agents". Cut to `workspace/real/` open in the editor, `src/integrations/skyRouteClient.js` visible. | "Consultancies work on client-owned code. They'd like to use external AI coding agents on it — but they can't let the client's name, their partners, internal service names, or secrets leave the building. So today they just don't. Our goal: shrink the surface where an *accidental* leak can happen, and prove a third-party model can still do the work." |
| Run `ghostc baseline --repo workspace/real --config privacy.yaml`, then open `workspace/baseline-ghost/src/integrations/skyRouteClient.js` — highlight `initvendor-c`, a broken import, a leftover `SKYROUTE_API_KEY`. | "The obvious fix is find-and-replace to REDACTED. That's our baseline. It breaks identifiers, it breaks imports, and it still leaks — it only catches the spellings you literally listed. `SKYROUTE_API_KEY` is right there." |

## 0:45 – 1:30 · Compile the ghost

| Screen | Narration |
|---|---|
| Run `ghostc compile --repo workspace/real --config privacy.yaml`. Then `git -C workspace/ghost diff HEAD~1` or open the same file in `workspace/ghost/`. Show `SkyRoute Data Ltd → Vendor A`, `skyRouteClient.js → vendorAClient.js`, `SKYROUTE_API_KEY → VENDOR_A_API_KEY`. | "The compiler is different. It parses the code with tree-sitter and replaces only real identifiers, strings and comments — one stable alias per entity, re-cased for every place it appears. `SkyRoute Data Ltd` becomes `Vendor A`, the file is renamed, the env var follows. The code still parses." |
| Run `ghostc verify --ghost workspace/ghost --mapping workspace/private/mapping.json` → **PASS**. | "Then a fail-closed check: if any real value is still in the ghost, verify blocks and nothing ships." |
| Switch to the two browser windows, :3000 and :3001 side by side. Same page, "Northwind Airlines" vs "Client A", "SkyRoute Data Ltd" vs "Vendor A". | "Same app, same endpoints, same passing tests — just the safe names. This is all an external agent ever sees." |

## 1:30 – 3:15 · One realistic execution

| Screen | Narration |
|---|---|
| Open `specs/001-add-companyx-integration.md` — a ticket: "add a CompanyX flight-status integration", names Northwind, SkyRoute, booking-core, CompanyX. | "Here's a real ticket. Add a second flight-data provider. It names the client, the existing vendor, an internal service, and the new partner." |
| Scroll the (pre-run) output of `client-agent start 001-add-companyx-integration --consultancy-backend claude`. Then `cat ../ghostc-demo/ghost/TASK.md` on the branch — highlight that CompanyX/Northwind/SkyRoute are **gone**, replaced by aliases. | "`client-agent start` compiles the ticket the same way it compiles code, commits it as `TASK.md` on a ghost branch, and a git hook kicks off the external agent — a real Claude agent — against its own clone of the ghost repo. The task it reads has no real names in it." |
| `git -C ../ghostc-demo/ghost log --stat ghostc/task/001-add-second-provider` — point at the two author identities and the files the agent added; mention "ghost npm test + build green". | "The agent implements the ticket on the ghost, runs the tests and the build until they're green, and pushes. Two identities on the branch: the company opened the task, an outside developer did the work." |
| Live-type `client-agent open-real-pr 001-add-companyx-integration`. Let it finish (seconds). | "Now the return leg. This simulates a forge webhook: take the agent's ghost diff, reverse-compile it through the mapping, and open a branch on the *real* repo." |
| `git -C ../ghostc-demo/real log --stat ghostc/real/001-add-companyx-integration` then open `companyXClient.js` on that branch — real names are back: `CompanyX`, `SkyRoute Data Ltd`, `booking-core`. | "Real names restored, leak-scan clean, and the real repo's tests and build still pass. That branch is what a human reviews and merges." |

## 3:15 – 4:00 · The comparison

| Screen | Narration |
|---|---|
| `cat workspace/eval-report.md` — the table: baseline **28**, compile **0**. | "The metric is leak count — real sensitive values an external agent could see. Keyword redaction leaves 28. The compiler leaves zero, and unlike redaction it round-trips and it doesn't break the code." |
| `cat metrics/agent-runs.jsonl | tail -3` — point at `ghost_tests.ok`, `fallbacks: 0`, leak fields. | "Every agent run writes a metrics row — tests, build, fallbacks, leaks — the same shape you'd publish from CI." |

## 4:00 – 4:40 · Changelog — where the improvement came from

| Screen | Narration |
|---|---|
| `CHANGELOG.md` progression table on screen, scrolling slowly. | "The changelog walks from that 28 to 0. The single biggest contributor is the **segment-casing engine**: one canonical alias, spliced and re-cased per occurrence, so `bookingCore`, `BOOKING_CORE_URL` and `booking-core.internal` all get rewritten from one rule. That's what closes the gap redaction can't." |
| Briefly highlight a "removed" row. | "One thing we removed: an in-process boundary self-check in the external agent — 'am I isolated?'. It's theatre; a real external agent doesn't audit its own sandbox. We deleted it and moved the boundary to infrastructure and a static import rule that a test enforces." |

## 4:40 – 5:00 · Hot take

| Screen | Narration |
|---|---|
| Back to the title card, or the two browser windows. | "The lesson: for a privacy boundary, don't ask the model to be careful — make an accidental leak *structurally hard* and *cheap to verify*. A deterministic compiler plus a fail-closed scan plus an import rule beats any amount of prompt discipline. That's what we'd build on next: same pipeline, wired to real pull requests and CI, and a review board where the human sign-off itself becomes data that tunes the detector." |

---

## If you're over time

Cut **1:30–3:15** down to just: show the sanitized `TASK.md`, then jump straight to the real
branch diff. The compile step (0:45–1:30) and the comparison (3:15–4:00) are the load-bearing
parts.
