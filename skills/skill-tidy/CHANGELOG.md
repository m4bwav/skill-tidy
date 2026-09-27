# Changelog: skill-tidy

Every change to [SKILL.md](SKILL.md) and its companions, newest first, each with the reason. Reasons cite findings in [RESEARCH.md](RESEARCH.md) (`R-`), lessons in [LEARNINGS.md](LEARNINGS.md) (`L-`), and test runs in [TESTS.md](TESTS.md) (`T-`). State in `evergreen.json`. Protocol: MAINTENANCE.md.

Entry shape: `### C-YYYYMMDD-n · date · one-line summary`, then `because:` (IDs or "user request"), `files:` (file and section), and a sentence on what changed. Cite section headings, not line numbers.

### C-20260926-2 · 2026-09-26 · Honour CLAUDE_CONFIG_DIR (v0.1.1)
- because: T-20260926-2 (action-1 found 0 skills: the eval harness moves Claude Code's config with CLAUDE_CONFIG_DIR)
- files: scripts/tidy.py (claude_dir, claude_json; every Claude Code path), ../../tests/test_tidy.py (TestConfigDir), versions
- Users with a custom Claude Code config folder saw an empty catalog, no usage and no settings; every Claude Code path now follows the variable, as Claude Code does.

### C-20260926-1 · 2026-09-26 · Created as an evergreen unit
- because: user request
- files: SKILL.md, RESEARCH.md, LEARNINGS.md, evergreen.json (skills: also TESTS.md and evals/evals.json)
- files: also scripts/tidy.py, references/rules.md, ../../tests/test_tidy.py
- Initial version 0.1.0: lint (ST001-ST019), conflicts, check, apply, budget, usage, offload, startup, harvest. Tier `fast`, interval 14d. Research basis R-20260926-1 and R-20260926-2; 11 unit tests pass; the eval suite is written and not yet run (TESTS.md).
