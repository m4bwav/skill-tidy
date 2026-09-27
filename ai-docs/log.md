# Log

Append-only. One line per operation: `## [YYYY-MM-DD] op | title` where op is one of add, update, supersede, verify, verify-failed, prune, handoff, index. Newest at the bottom. Never edited, only appended; this is the history the entries themselves do not carry.

## [2026-09-26] init | scaffolded
## [2026-09-26] add | decision: skill-tidy as its own plugin: script checks, model rewrites once
## [2026-09-26] handoff | 16 lines
## [2026-09-26] add | skill-tidy 0.1.0 created: tidy.py (lint ST001-ST019, conflicts, check, apply, budget, usage, offload, startup, harvest), evergreen unit tier fast, research R-20260926-1/-2, 11 tests
