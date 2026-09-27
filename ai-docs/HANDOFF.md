# Handoff

## Current state
skill-tidy 0.1.0: one evergreen skill (`skills/skill-tidy/`, tier fast, next due 2026-10-10) and the stdlib CLI `scripts/tidy.py` with lint (ST001-ST019), conflicts, check, apply, budget, usage, offload, startup, harvest. 11 unit tests pass (`python tests/test_tidy.py`); the skill's own description lints clean. Research basis in RESEARCH.md (R-20260926-1, -2), rules with evidence in `references/rules.md`.

## In progress
The eval suite (`evals/evals.json`, evergreen format) is written but not run. `claude plugin eval` cannot read that format; the chartwright repo converted its cases into `evals/<case>/prompt.md` plus graders (see its HANDOFF), which is the route to copy. The outcome case needs a fixture folder with feed-scan and radar-sweep skills.

## Decisions made this session
See [INDEX.md](INDEX.md): skill-tidy is its own plugin; the script checks and the model rewrites once.

## Next single action
Convert the eval cases to `claude plugin eval` format and run them (trigger, decoy, action), log T- in TESTS.md.

## Gotchas
Claude Code's listing budget unit is unsettled (characters per the skills docs, tokens per everlast's skill-budget); see RESEARCH.md Open questions. Copilot and Cursor skill roots in `roots_for` are the least certain part. `apply` refuses installed plugin copies by design: edit the source repo and reinstall.
