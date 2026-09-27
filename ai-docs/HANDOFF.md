# Handoff

## Current state
skill-tidy 0.1.0: one evergreen skill (`skills/skill-tidy/`, tier fast, next due 2026-10-10) and the stdlib CLI `scripts/tidy.py` with lint (ST001-ST019), conflicts, check, apply, budget, usage, offload, startup, harvest. 11 unit tests pass (`python tests/test_tidy.py`); the skill's own description lints clean. Research basis in RESEARCH.md (R-20260926-1, -2), rules with evidence in `references/rules.md`.

## In progress
Eval suite run and recorded (T-20260926-2, 6/6): cases in the root `evals/` folder in `claude plugin eval` format. Trigger and decoy cases run on native Windows (`claude plugin eval . --ablation none --no-publish -j 4 --tag trigger --trust-plugin`); the Bash cases (action-1, outcome-1) are refused there (no Windows sandbox) and run in WSL2 Ubuntu from a copy of the repo in the Linux home with `--tag bash --scaffold --allow-tools Bash Write Edit --trust-plugin`. The run found one gap: `tidy.py` scans `~/.claude` only and ignores `CLAUDE_CONFIG_DIR`, so action-1 reported 0 skills.

## Decisions made this session
See [INDEX.md](INDEX.md): skill-tidy is its own plugin; the script checks and the model rewrites once.

## Next single action
CLAUDE_CONFIG_DIR is honoured since 0.1.1 (TestConfigDir). Re-run action-1 under WSL2 to confirm it now lists the plugin skills; then decide with the user whether the repo goes public (privacy scan first, as context-health did).

## Gotchas
Claude Code's listing budget unit is unsettled (characters per the skills docs, tokens per everlast's skill-budget); see RESEARCH.md Open questions. Copilot and Cursor skill roots in `roots_for` are the least certain part. `apply` refuses installed plugin copies by design: edit the source repo and reinstall.
Evals: `evals/results/` is gitignored. Graders on a Bash command must allow text between `tidy.py` and the subcommand (the model often runs it as `T="python3 .../tidy.py"; $T apply`).
