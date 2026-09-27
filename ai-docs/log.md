# Log

Append-only. One line per operation: `## [YYYY-MM-DD] op | title` where op is one of add, update, supersede, verify, verify-failed, prune, handoff, index. Newest at the bottom. Never edited, only appended; this is the history the entries themselves do not carry.

## [2026-09-26] init | scaffolded
## [2026-09-26] add | decision: skill-tidy as its own plugin: script checks, model rewrites once
## [2026-09-26] handoff | 16 lines
## [2026-09-26] add | skill-tidy 0.1.0 created: tidy.py (lint ST001-ST019, conflicts, check, apply, budget, usage, offload, startup, harvest), evergreen unit tier fast, research R-20260926-1/-2, 11 tests
## [2026-09-26] verify | eval suite converted to claude plugin eval format in evals/ and run: 6/6 (T-20260926-2); trigger and decoy on native Windows, Bash cases in WSL2; found tidy.py ignores CLAUDE_CONFIG_DIR
## [2026-09-26] update | 0.1.1: CLAUDE_CONFIG_DIR honoured for every Claude Code path (found by eval T-20260926-2); released and installed
## [2026-09-26] update | 0.2.0: body offload (sections, split, ST020-ST023), parking lot (park/unpark/parked, inline grouped index in always-read instruction files), gap fixes from the description clean-up (apostrophes, similarity rule enforced, body rules out of check, lint on repo roots); research R-20260926-3/-4; 20 tests
## [2026-09-26] update | 0.2.1 released: is_link fix (macOS /var, Windows 8.3 names), ST011/ST009 false positives; handoff lists the open gaps from the clean-up runs
## [2026-09-26] run | first real parking run (user scope, 60-day usage): sf2e-miniature (link) and sprite-editor (move) in games, acestep-music (link) in music, ui (move) and ui-uitk (move, unpark) in unity; no plugin qualified (every eligible plugin had a used skill). Listing 42 skills 34.1K chars (~8.5K tokens) -> 37 skills 31.9K chars (~8.0K tokens) at window 1M. Gap: ~/.agents/skills held junctions to the moved ~/.claude/skills folders (sprite-editor, ui, ui-uitk); park left them dangling, they were removed by hand, and unpark will not recreate them. Also removed the stale project-scope evergreen@mark-local 0.5.0 entry (projectPath c:\Users\m4bwa) from installed_plugins.json by hand: claude plugin uninstall --scope project refuses it, saying the plugin is in user scope, because the home directory project is ~/.claude itself

## 2026-09-26 v0.2.2 alias links
Park (move and link) now records and removes other links to the parked folder in every host's skill roots (`aliases` in parked.json); unpark recreates them; `parked doctor` reports dangling links; `parked alias NAME PATH` backfills entries parked earlier. 24 tests pass.
