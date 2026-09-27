---
name: skill-tidy
description: "Fix skills that compete for the same prompts and cut the tokens the skill catalog costs every session. Lints SKILL.md descriptions against the Agent Skills spec and host limits, explains why two skills clash, checks a rewritten description keeps every trigger before writing it, finds skills never used and hides them to save tokens, and audits the always-loaded instruction files and MCP settings. Use when the user asks why the wrong skill fired, to clean up or shorten skill descriptions, to fix a skill conflict or overlap, how many tokens skills cost, to trim the startup context, or when a context-health selection line reports similar skills. Also for 'refresh skill-tidy' and 'is skill-tidy stale'. Measuring session size is context-health; per-skill cost and usage alone is Claude Code's /skill-doctor."
metadata:
  version: "0.1.1"
---

# skill-tidy

A skill catalog costs tokens every session and, past about 20-30 skills, costs selection accuracy; overlapping descriptions cost more than raw count (RESEARCH.md). This skill finds the problems with a script and fixes them with judgment, one rewrite per skill.

`TIDY` below means `python "<this folder>/scripts/tidy.py"` (`python3` on macOS and Linux). Every command takes `--agent claude|codex|copilot|cursor|all` (default claude), `--project PATH` (default cwd) and `--json`. Rules and their evidence: [references/rules.md](references/rules.md).

## Step 0: freshness

Read [evergreen.json](evergreen.json). If `contradiction` is set or today is on or after `next_due`, say so in one line, do the task, then refresh (MAINTENANCE.md). Host limits and settings change monthly.

## Step 1: measure

Run what the request needs, not everything:

- `TIDY conflicts`: pairs at TF-IDF cosine 0.45+ (0.65+ near-duplicate), the words both share, trigger phrases both claim, and a starting boundary sentence for each side.
- `TIDY lint [SKILL_DIR ...]`: rules ST001-ST019; errors are spec or host limits, warnings are research-backed style. Exit code 1 when an error exists.
- `TIDY budget --window <model window>`: listing size against Claude Code's 1% budget (over it, least-used descriptions are dropped), Codex's 2% / 8,000 chars, the 1,536 cut and the spec's 1,024.
- `TIDY usage --days 30`, `TIDY startup`: invocations from transcripts; the instruction chain, memory and MCP settings.

## Step 2: fix a conflict (no functionality lost)

1. Decide the split in one sentence per skill: what each one's job is and which user phrasing belongs to which. If the jobs genuinely overlap (the same request should reach both), recommend merging instead of rewording, and stop for the user.
2. `TIDY triggers <skill>` for both. Every trigger's meaning must survive; a phrase may move to the skill that owns it.
3. Optional evidence: `TIDY harvest <skill>` writes a brief with prompts that matched but did not invoke it and invocations that look unrelated. Use it as the false-positive and false-negative input.
4. Write ONE rewrite of the weaker or longer description (editing both sides adds under 0.5% in the research; edit both only when both break a limit). Key use case and its trigger words first; what it does plus "Use when"; third person or imperative; at most 1,024 chars, about 100-200 words; no steering text; end with one short boundary sentence naming the sibling. Keep triggers in `description`, not `when_to_use` (only Claude Code reads that).
5. `TIDY check <skill> --new <file>` must print `OK`: no errors, no lost trigger, closest similarity lower than before. Then `TIDY apply <skill> --new <file>` (keeps a backup under `~/.skill-tidy/backups/`). Installed plugin copies are refused: edit the plugin's source repository and reinstall.
6. Confirm with `TIDY conflicts` and report the before and after scores.

## Step 3: save tokens

- Never-used skills: `TIDY offload --days 30` prints `skillOverrides` "name-only" entries for Claude Code (the name stays invocable, the description stops loading), plugin skills to disable per project in `/plugin`, and Codex `[[skills.config]] enabled = false` lines. `--write` merges the Claude Code entries into `~/.claude/settings.json` with a backup. Ask the user before `--write`; a skill used monthly may look unused over 30 days.
- Long descriptions: shorten the ones `lint` flags ST005/ST006/ST007 with the Step 2 loop.
- Rarely wanted, manual-only skills: suggest `disable-model-invocation: true` in their front matter (no listing cost; `/name` still works). Skills tied to file types: suggest `paths:` globs.
- Startup: `TIDY startup` shows the biggest instruction files and imports, `alwaysLoad` MCP servers and whether tool search is off. Suggest moving rarely needed detail from CLAUDE.md or AGENTS.md into files loaded on demand.

## Step 4: report

One short list: what was changed (file, before and after chars and similarity), what was only suggested, estimated tokens saved per session, anything left for the user to decide. Record a learning in [LEARNINGS.md](LEARNINGS.md) when a host behaved differently from the rules.

## Maintenance

Evergreen unit: [RESEARCH.md](RESEARCH.md), [CHANGELOG.md](CHANGELOG.md), [LEARNINGS.md](LEARNINGS.md), [TESTS.md](TESTS.md), state in [evergreen.json](evergreen.json), protocol in [MAINTENANCE.md](MAINTENANCE.md).
