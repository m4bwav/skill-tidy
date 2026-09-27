# Log

Append-only. One line per operation: `## [YYYY-MM-DD] op | title` where op is one of add, update, supersede, verify, verify-failed, prune, handoff, index. Newest at the bottom. Never edited, only appended; this is the history the entries themselves do not carry.

## [2026-09-26] init | scaffolded
## [2026-09-26] add | decision: skill-tidy as its own plugin: script checks, model rewrites once
## [2026-09-26] handoff | 16 lines
## [2026-09-26] add | skill-tidy 0.1.0 created: tidy.py (lint ST001-ST019, conflicts, check, apply, budget, usage, offload, startup, harvest), evergreen unit tier fast, research R-20260926-1/-2, 11 tests
## [2026-09-26] verify | eval suite converted to claude plugin eval format in evals/ and run: 6/6 (T-20260926-2); trigger and decoy on native Windows, Bash cases in WSL2; found tidy.py ignores CLAUDE_CONFIG_DIR
## [2026-09-26] update | 0.1.1: CLAUDE_CONFIG_DIR honoured for every Claude Code path (found by eval T-20260926-2); released and installed
## [2026-09-26] update | 0.2.0: body offload (sections, split, ST020-ST023), parking lot (park/unpark/parked, inline grouped index in always-read instruction files), gap fixes from the description clean-up (apostrophes, similarity rule enforced, body rules out of check, lint on repo roots); research R-20260926-3/-4; 20 tests
