# Changelog: skill-tidy

Every change to [SKILL.md](SKILL.md) and its companions, newest first, each with the reason. Reasons cite findings in [RESEARCH.md](RESEARCH.md) (`R-`), lessons in [LEARNINGS.md](LEARNINGS.md) (`L-`), and test runs in [TESTS.md](TESTS.md) (`T-`). State in `evergreen.json`. Protocol: MAINTENANCE.md.

Entry shape: `### C-YYYYMMDD-n · date · one-line summary`, then `because:` (IDs or "user request"), `files:` (file and section), and a sentence on what changed. Cite section headings, not line numbers.

### C-20260926-3 · 2026-09-26 · Body offload (sections, split), parking lot (park, unpark, parked), gap fixes (v0.2.0)
- because: user request (move main-file content to sub-files loaded on demand; a skill parking lot the agent can still find from user or project files; research first); R-20260926-3, R-20260926-4; gaps reported by the description clean-up run on the development machine
- files: scripts/tidy.py (sections, offload_candidates, reference_problems, split_section, ST020-ST023; park, unpark, render_index, write_block, link_targets, reindex, parked_doctor; triggers ignore apostrophes inside words; check enforces similarity and drops body rules; lint expands a repo root), SKILL.md (description; Step 3), references/rules.md (ST020-ST023, body sections), new references/parking.md, RESEARCH.md (R-20260926-3, -4), ../../tests/test_tidy.py (TestBody, TestParking, TestGaps), versions, ../../README.md
- The body of a skill loads in full every use; `sections` and `split` move supplementary sections to reference files with a 'Read X when Y.' pointer. Parked skills leave every scanned folder and are listed in a grouped index written inline into the always-read instruction files (a pointer is optional reading; an inline index is not). Plugin skills are never moved: the plugin is disabled and indexed. `check` now fails a rewrite whose closest similarity rises past 0.45.

### C-20260926-2 · 2026-09-26 · Honour CLAUDE_CONFIG_DIR (v0.1.1)
- because: T-20260926-2 (action-1 found 0 skills: the eval harness moves Claude Code's config with CLAUDE_CONFIG_DIR)
- files: scripts/tidy.py (claude_dir, claude_json; every Claude Code path), ../../tests/test_tidy.py (TestConfigDir), versions
- Users with a custom Claude Code config folder saw an empty catalog, no usage and no settings; every Claude Code path now follows the variable, as Claude Code does.

### C-20260926-1 · 2026-09-26 · Created as an evergreen unit
- because: user request
- files: SKILL.md, RESEARCH.md, LEARNINGS.md, evergreen.json (skills: also TESTS.md and evals/evals.json)
- files: also scripts/tidy.py, references/rules.md, ../../tests/test_tidy.py
- Initial version 0.1.0: lint (ST001-ST019), conflicts, check, apply, budget, usage, offload, startup, harvest. Tier `fast`, interval 14d. Research basis R-20260926-1 and R-20260926-2; 11 unit tests pass; the eval suite is written and not yet run (TESTS.md).
