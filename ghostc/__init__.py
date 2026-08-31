"""ghostc — privacy compiler + agent workflow.

Compiles a real repository into a privacy-safe *ghost* repository, lets an external
coding agent work on the ghost, and translates the resulting ghost PR back into a
real PR — with a structured audit log behind every step.

All eight subcommands are implemented: `validate-config`, `discover`, `compile`,
`compile-spec`, `verify`, `baseline`, `apply-patch`, `eval`. Status and decision log:
`docs/PROGRESS.md`.
"""

__version__ = "0.1.0"
