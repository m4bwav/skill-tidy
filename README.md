# skill-tidy

![A neat craftsman's cabinet of many small labelled wooden drawers holding tools, a robot hand sorting tools into the right drawers, tidy and orderly](https://raw.githubusercontent.com/m4bwav/skill-tidy/master/.github/images/banner.jpg)

Keep an AI agent's skill catalog cheap and unambiguous. Works with Agent Skills (`SKILL.md`) in Claude Code, Codex, GitHub Copilot and Cursor.

Every installed skill puts its name and description in front of the model at the start of every session. That costs tokens, and past about 20-30 skills it costs accuracy: the model picks the wrong skill or none. Research in 2026 found that overlapping descriptions, more than the raw count, cause those misses, and that one careful rewrite of a description fixes most of them. skill-tidy finds the problems with a script and helps fix them without losing what each skill is triggered by.

## What it does

- **lint**: 19 rules for descriptions, each with its evidence: the Agent Skills spec limits, Claude Code's 1,536-character cut, Codex's front-loading advice, third person, a "Use when" clause, no steering text, no keyword stuffing, and a boundary sentence when a sibling is close. See [references/rules.md](skills/skill-tidy/references/rules.md).
- **conflicts**: pairs of skills whose descriptions compete (TF-IDF cosine, 0.45 possibly confusable, 0.65 near-duplicate), the words and trigger phrases they share, and a starting boundary sentence for each side.
- **check / apply**: test a rewritten description before writing it: lint, every old trigger still carried, similarity before and after. `apply` backs up the file and refuses installed plugin copies.
- **budget**: the listing against each host's budget (Claude Code 1% of the window, Codex 2% or 8,000 characters).
- **usage / offload**: skill invocations from Claude Code and Codex transcripts; never-used skills turned into `skillOverrides` "name-only" entries (still invocable by name, no description cost), Codex `enabled = false` lines, and plugins to disable.
- **sections / split**: a SKILL.md body loads in full every time the skill runs, reference files only when read. `sections` sizes each section and marks supplementary ones (examples, tables, per-host notes, templates); `split` moves one to `references/` and leaves `Read <file> when <condition>.` Lint rules ST020-ST023 cover long bodies, nested references, missing contents lists and backslash paths.
- **park / unpark / parked**: a parking lot for rarely used skills. A parked skill leaves every folder any host scans (no listing cost, no competition for selection) and is listed in a grouped one-line index written into the instruction files every session reads (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`, or the project's AGENTS.md), so the agent still finds it and reads its SKILL.md on demand. Symlinked skills lose only the link; plugins are disabled, never moved. See [references/parking.md](skills/skill-tidy/references/parking.md).
- **startup**: the always-loaded instruction chain (CLAUDE.md files up the tree, `@imports`, auto-memory) and MCP settings that load schemas upfront.
- **harvest**: prompts that matched a skill but did not invoke it, and invocations that look unrelated, written as a one-rewrite brief.

Claude Code's `/skill-doctor` already shows per-skill cost and use; skill-tidy adds description quality, conflicts, trigger-safe rewrites and other hosts.

## Install

Clone it, then either install it as a Claude Code plugin from the folder (`/plugin marketplace add <path>` then `/plugin install skill-tidy@skill-tidy`) or link `skills/skill-tidy` into `~/.claude/skills/` or `~/.agents/skills/`. The CLI needs only Python 3.8+:

```
python skills/skill-tidy/scripts/tidy.py conflicts
python skills/skill-tidy/scripts/tidy.py lint --min warn
python skills/skill-tidy/scripts/tidy.py budget --window 1000000
python skills/skill-tidy/scripts/tidy.py offload --days 30
```

Every command takes `--agent claude|codex|copilot|cursor|all`, `--project PATH` and `--json`.

## Evergreen

The skill keeps its research current on a schedule (tier fast, every 14 days at most): host limits, settings and the selection research are re-checked from primary sources, and every change is logged with its reason in [CHANGELOG.md](skills/skill-tidy/CHANGELOG.md). The research basis is in [RESEARCH.md](skills/skill-tidy/RESEARCH.md).

## Privacy

skill-tidy collects nothing and makes no network calls. The CLI (`skills/skill-tidy/scripts/tidy.py`) is one standard-library Python file that runs on your machine. To do its job it reads local files only: skill folders, host settings and instruction files (CLAUDE.md, AGENTS.md, `~/.claude/settings.json`, `~/.claude.json`), and, for `usage`, `offload` and `harvest`, the session transcripts Claude Code and Codex already keep under `~/.claude/projects` and `~/.codex/sessions`. It counts skill names and matches prompts in memory and prints the result; it does not copy transcripts anywhere. It writes only when you pass an explicit flag (`apply`, `offload --write`, `split`, `park`, `unpark`), and then only to your own skill and settings files, with a backup and the parking lot kept under `~/.skill-tidy` on your machine. It reads no credentials and no API keys.

The one route that reaches the internet is the evergreen refresh described above. When the skill's research is due, the agent runs web searches and fetches public documentation pages with its own web tools. It may also run `npx skills@1.7.0 find` to look up install counts on skills.sh, which downloads that package from the npm registry. Those requests carry search terms about the skill's subject, not your files. Whatever your AI app does with the conversation is covered by that app's own privacy policy.

## Versioning

Semantic versions; tags `vX.Y.Z` with a GitHub Release each. MIT licence.
