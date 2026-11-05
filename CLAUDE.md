@AGENTS.md

## Claude Code specifics

- Project skills are in `.claude/skills/`. Use them for the matching tasks:
  `add-component`, `add-abbreviation`, `generate-eval-cases`, `annotate-ravelry-pattern`,
  `run-eval`, `crisp-dm-checkpoint`.
- Start each working session by reading the last ~3 entries of `docs/crisp-dm-log.md` to recover context.
- Read only the files relevant to the current component; don't load the whole repo into context.
- Before writing parser, simulator or chart code, read `docs/CONVENTIONS.md` § Pattern IR.
