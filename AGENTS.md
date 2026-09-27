# AGENTS.md

Rules for any AI agent (Claude Code, Copilot, Cursor, Codex, Gemini CLI) working in this repository. `CLAUDE.md` and `.github/copilot-instructions.md` only point here.

## What this is

A cross-agent plugin with one skill, `skills/skill-tidy/`: SKILL.md, the single-file CLI `scripts/tidy.py`, the lint rules with their evidence in `references/rules.md`, and the evergreen companions (RESEARCH, CHANGELOG, LEARNINGS, TESTS, MAINTENANCE, `evergreen.json`, `evals/`). Tests are in `tests/`. [README.md](README.md) has the commands. Handoff notes, decisions and the log are under `ai-docs/` (start with `ai-docs/HANDOFF.md`).

## Rules

- `tidy.py` stays one standard-library Python file (3.8 or newer) that runs on Windows, macOS and Linux. Parsers of transcripts and settings are small and defensive: vendor formats are not stable APIs, so a miss is skipped, never a crash.
- Every change to the script has a test in `tests/test_tidy.py`; run `python tests/test_tidy.py` from the repository root before committing. CI runs it on Windows, macOS and Linux. The skill's own description must pass `python skills/skill-tidy/scripts/tidy.py lint skills/skill-tidy --min info` with no findings.
- Every lint rule cites its evidence in `references/rules.md`, and every number (limits, budgets, thresholds) has an `R-` entry in RESEARCH.md. Research beats recall: host limits and settings change monthly. Never change a limit from memory.
- The skill is an evergreen unit. Before editing it read `skills/skill-tidy/evergreen.json`; if `next_due` has passed or `contradiction` is set, say so and refresh after the task (the evergreen plugin's `evergreen-refresh` when installed, otherwise `skills/skill-tidy/MAINTENANCE.md`).
- Every change is logged in `skills/skill-tidy/CHANGELOG.md` with its reason. When a packaged file changes, bump the version in `.claude-plugin/plugin.json`, `plugin.json`, `VERSION` in `tidy.py`, `metadata.version` in SKILL.md and `evergreen.json` together, then tag `vX.Y.Z` and publish a GitHub Release for the tag.
- The tool writes user files only on an explicit flag (`apply`, `offload --write`), always with a backup under `~/.skill-tidy/backups/`, and never into an installed plugin copy.
- This is a public repository. Nothing in it names a person other than the author credit, a machine, an absolute path on someone's machine, a private project, or a credential. Test fixtures use invented skill names.
- No AI attribution anywhere: no Co-Authored-By trailers, no "generated with" lines in commits, pull requests or files.

## everlast (session knowledge, load on demand)

- `ai-docs/INDEX.md` lists what past sessions learned here (solutions with verified commands, decisions with reasons, plans). At the start of a task, scan it and open only the entries whose title or tags match; read `ai-docs/HANDOFF.md` when continuing unfinished work (everlast-resume skill).
- Before finishing a task that hit a dead end, verified a non-obvious command, made a design choice, or taught you something about the user, record it (everlast-capture skill, or `everlast.py note` / `handoff`); rewrite `HANDOFF.md` when work is left unfinished. Say "nothing to record" when that is true.
- Anything naming a person, an internal host or name, a credential, or an opinion about people goes to the private sidecar (`--private`), never here. Lessons about the user or this machine go to the user tier (`--user`).
- Link documents together with relative markdown links: every markdown folder has an index that links its files, every entry links its index and the entries it builds on (a `Related:` line). No wikilinks in the repo.
