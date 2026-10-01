# Learnings: skill-tidy

Procedural lessons for [SKILL.md](SKILL.md). Research findings live in [RESEARCH.md](RESEARCH.md); every change is logged in [CHANGELOG.md](CHANGELOG.md); test runs in [TESTS.md](TESTS.md); state in `evergreen.json`. Format and write-time gate: MAINTENANCE.md (LEARNINGS-FORMAT). Retired entries go to LEARNINGS-ARCHIVE.md with a reason.

Write an entry the moment a real signal happens: a user correction, the same error twice, a discovered workaround, an environment fact, a stated preference, a failed test or a failure in use. Check existing entries first, by meaning (`evergreen.py search "<the lesson>" --kinds learnings` finds near-duplicates in every registered unit): add / update / retire / none. Trigger and Hypothesis are required. Promote after three confirmations; retire when harmful > helpful.

## Active

### L-002 · 2026-09-30 · Test runs count as skill use unless headless sessions are left out (`headless-runs-are-not-use`)
- Trigger: `tidy.py usage --days 60` gave wikiwright 66 and everwrite 35 invocations; 61 and 29 of them came from eval suites run with `claude -p` in temp folders, logged with `entrypoint: claude-vscode` because the child inherits it from the VS Code session that started it (the owner's skill worth study, 2026-09-30)
- Hypothesis: the entrypoint names the launcher's environment, not how the session is driven; the working folder is what separates a test from a person's work
- Rule: classify a session as headless when its entrypoint starts with `sdk` or its cwd is under the temp directory, and keep headless sessions out of every usage-driven decision (offload, parking, harvest)
- Evidence: the counts before and after on the owner's machine (wikiwright 8 real + 62 headless); test `test_headless_sessions_are_not_uses`; evergreen-protocol L-026 found the same in its `worth` usage
- Scope: skill (scripts/tidy.py usage)
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-30

<!-- Example (delete once you have a real entry):
### L-001 · 2026-09-26 · One-line lesson in plain words
- Trigger: what happened, with dates or counts
- Hypothesis: why
- Rule: the shortest instruction that prevents the trigger
- Evidence: C-20260926-1, T-20260926-1, confirmed 2026-09-26
- Scope: skill | repo:<slug> | env:<name> | global
- Status: active · helpful 1 · harmful 0 · last_confirmed 2026-09-26
-->
