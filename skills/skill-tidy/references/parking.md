# Parking lot

Rarely used skills leave every folder a host scans, so their descriptions cost no listing tokens and stop competing for selection, and stay findable through a short index written into the instruction files the agent always reads. Evidence: [../RESEARCH.md](../RESEARCH.md) R-20260926-4.

## Where things live

- User lot: `~/.agents/parked-skills/<name>/`; project lot: `<project>/.agents/parked-skills/<name>/` (`--scope project`). No host scans these folders; never put a lot under a `skills/` folder, `.claude/` or `.cursor/`.
- `parked.json` in the lot records each skill's origin, mode, group, index line and the skill features a plain read loses.
- `PARKED.md` in the lot is the full index. The marked block `<!-- skill-tidy:parked:start -->` ... `end` is written into `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` (user scope, when Codex is set up) or the project's `AGENTS.md`, plus `CLAUDE.md` when it does not import AGENTS.md (project scope). Up to 40 lines the block is the whole index; past that it lists groups and points at `PARKED.md`.

## Modes

| Mode | What `park` does | What `unpark` does |
|---|---|---|
| move | moves the real folder into the lot | moves it back |
| link | removes only the symlink or junction; the target (often a repo) is untouched and indexed in place | recreates the link (a junction on Windows) |
| soft (`--soft`) | Claude Code only: `skillOverrides` "off"; the folder stays | removes the override |
| plugin (`--plugin NAME`) | sets `enabledPlugins` false (backup kept) and indexes the plugin's skills at their cache path | re-enables the plugin |

Plugin skills are never moved or edited: the cache is overwritten on update and its path changes with the version. `parked doctor` reports paths that moved.

## How the agent uses a parked skill

The index header tells it: when a line matches, read that SKILL.md in full, treat its folder as the skill's base directory (`${CLAUDE_SKILL_DIR}`, relative `scripts/`), run scripts by absolute path. A plain read gets no `${CLAUDE_SKILL_DIR}` substitution, no `!` injection, no `allowed-tools` pre-approval, no hooks and no forked context; skills that use them are marked `(unpark)` and must be unparked first. Claude Code picks an unparked folder up live; Codex needs a restart.

## Choosing what to park

`parked suggest --days 30` lists listed skills with no invocation in the transcripts, largest listing cost first. A skill used monthly looks unused over 30 days: ask the user before parking. Keep groups at 8 or fewer (`--group`); `park` warns when a group grows past that. Check with `parked doctor` after any plugin update.
