# Research: skill-tidy

Findings that back [SKILL.md](SKILL.md) and [references/rules.md](references/rules.md). Changes they caused are logged in [CHANGELOG.md](CHANGELOG.md); procedural lessons live in [LEARNINGS.md](LEARNINGS.md); test runs and their evidence in [TESTS.md](TESTS.md); schedule and state in `evergreen.json`. Protocol: [MAINTENANCE.md](MAINTENANCE.md).

Topic: Agent Skills description quality and selection conflicts, skill catalog listing budgets and token cost per host (Claude Code, Codex, Copilot, Cursor), and startup-context trimming. Tier `fast`. Last refresh 2026-09-26; next due 2026-10-10.

## Current understanding

- **Overlap costs more than count.** Selection accuracy stays above 90% up to about 20 skills and degrades beyond 30 (arXiv 2601.04748, GPT-4o-class models, synthetic skills). At a fixed catalog size, hand-written competitor skills cost 7-63 points. As libraries grow to 202 skills, skill shadowing (wrong or abandoned selection) is the main cause of a pass-rate drop of up to 21%, while the larger context costs about nothing (2605.24050). Same-family siblings are the documented risk: retrievers with Recall@3 0.85-0.89 still expose a harmful sibling 35-37% of the time (2606.10388). Confident.
- **One rewrite is enough.** A single LLM rewrite fed with false-positive and false-negative cases reached 79.2% F1 against 79.4% for hand tuning, in 3.8 minutes instead of 120. Editing both sides of a confused pair changed F1 by under 0.5%. A large train-validation gap means the scopes really overlap and need an architectural fix (merge), not new wording (2606.30775). Confident.
- **Description rules (vendor docs).** The Agent Skills spec: name 1-64 chars of `a-z0-9-`, matching the folder; description 1-1,024 chars saying what the skill does and when to use it, with specific keywords; `compatibility` at most 500. Anthropic: third person, no "I can" or "you can", no XML tags, reserved words `anthropic` and `claude` barred from names, avoid vague text like "Helps with documents". skill-creator's rewriter aims for about 100-200 words, uses the imperative "Use this skill for", and warns against ever-growing lists of example queries. Claude Code: put the key use case first; description plus `when_to_use` is cut at 1,536 chars. Codex: front-load the key use case and trigger words, state scope and boundaries. Confident; the third-person vs imperative split between Anthropic's guide and its own rewriter is reconciled by allowing both and flagging only first and second person.
- **Listing budgets.** Claude Code: `skillListingBudgetFraction` 0.01 of the window; over it, names stay and the least-used skills lose their descriptions; `skillListingMaxDescChars` 1,536. `skillOverrides` takes `on`, `name-only`, `user-invocable-only`, `off`, matches skill names, and does not affect plugin skills (use `/plugin`). `disable-model-invocation: true` removes a skill from the listing; `paths` limits auto-loading to matching files. Codex: 2% of the window, or 8,000 chars when unknown; descriptions are shortened first, then skills omitted; `[[skills.config]] path enabled=false` in `~/.codex/config.toml`. Copilot: description 1,024, and descriptions longer than that are reported dropped (Copilot CLI issue 3494). Cursor documents no numbers. Confident for Claude Code and Codex; Copilot and Cursor skill roots in `tidy.py` are the least certain part (re-check each refresh).
- **Steering is a risk.** Semantic shaping of a description raised a target skill's selection from 15.2% to 63.5%, and people spotted it 2.9% of the time (2609.02035); the linter flags steering phrases.
- **Lexical similarity is a proxy.** No study validates TF-IDF or Jaccard on descriptions against model confusion. ToolScope uses embedding cosine 0.77-0.82 for merge candidates (2510.20036); lexical cosine runs lower, so 0.45 / 0.65 are inference, checked on one real 41-skill catalog (2 pairs over 0.45).
- **Existing tools** (checked 2026-09-26): Claude Code's `/skill-doctor` (v2.1.252) shows per-skill cost and use and flags never-invoked skills and unused plugins; it does not judge description quality or overlap. skills-lint (GitHub Action; spec fields, bigram near-duplicates at 0.7), skillscheck (spec, token counts, "use when" and keyword-stuffing warnings), MindiveLabs/skill-doctor (LLM conflict typing), skillprune (transcripts plus Jaccard 0.35), paultaki/claude-skill-usage (cost dashboard), skill-creator `run_loop` (model-driven trigger optimisation). skill-tidy adds what none of them combines: cross-host rules with cited evidence, per-host budgets, a trigger-preserving check before any rewrite is written, `skillOverrides` and Codex config output, and a one-rewrite brief from transcripts.

## Open questions

- A validated cheap similarity measure (would let 0.45 / 0.65 be calibrated).
- Exact skill roots for Copilot CLI and Cursor on each OS; whether Copilot drops or truncates descriptions over 1,024.
- Claude Code's listing budget unit: the skills docs call it a character budget at 1% of the window (`tidy.py budget` compares characters); the everlast plugin's `skill-budget` compares estimated tokens. Characters are 4x stricter; confirm on the next refresh (`/context` Skills row).
- Whether a boundary sentence naming the sibling ("To X, use Y") helps or hurts selection: no paper tests it directly; vendor examples use it.

## Search plan

Four tracks; every refresh runs at least one query on each (scope each to the period since the last refresh; add the year).

Subject:

- `site:arxiv.org skill selection description agent skills library <year>`; `"skill shadowing" OR "skill description" optimization <year>`
- code.claude.com/docs/en/skills, /settings, /context-window, /whats-new (listing budget, skillOverrides, /skill-doctor); learn.chatgpt.com/docs/build-skills; code.visualstudio.com/docs/copilot/customization/agent-skills; cursor.com/docs/skills; agentskills.io/specification

Tooling:

- `path:SKILL.md "description" lint OR overlap OR conflict` on GitHub code search, recently updated; `npx skills find "skill lint"`; skills.sh for install counts
- `"skill description" linter OR optimizer OR conflict "claude code" OR codex <year> site:github.com`
- Supersession sweep: `/skill-doctor` release notes (does it start judging descriptions?), skills-lint, skillscheck

Practice:

- `"too many skills" OR "wrong skill" "claude code" <month> <year>` on r/ClaudeAI, r/ClaudeCode, hn.algolia.com
- `site:anthropic.com/engineering skills <year>`; `site:simonwillison.net skills <year>`

Testing:

- `claude plugin eval` docs (trigger graders); skill-creator `run_eval` / `run_loop`
- `site:arxiv.org skill routing benchmark OR "skill retrieval" evaluation <year>`

Best sources (primary first): the vendor docs above, the Agent Skills spec, arXiv (2601.04748, 2605.24050, 2606.10388, 2606.30775, 2609.02035, 2510.20036, 2603.22455, 2603.29919), anthropics/skills (skill-creator). Noisy: SEO "best skills" listicles, scraped skill directories.

## Findings log

Newest first. `Track` is subject, tooling, practice, or testing.

### R-20260926-4 · 2026-09-26 · Subject and tooling: parking skills where the agent can still find them
- Summary: Claude Code: `skillOverrides` off/name-only (plugin skills unaffected; disable the plugin), `disable-model-invocation`, `paths`; skill folders added or removed under a skills root take effect live; `@import` always loads the whole file (no lazy import); Claude sees AGENTS.md only if it decides to open it; after compaction the project-root CLAUDE.md is re-injected but the skill listing is not; `${CLAUDE_SKILL_DIR}` and `!` injection apply only to skills invoked through the skill system; no documented way to register an unlisted skill for loading by path. Codex scans `.agents/skills` up the tree and `~/.agents/skills`; Cursor walks skill roots recursively (so a lot must not sit under one); Copilot reads `.github/.claude/.agents` skills and loads `*.instructions.md` on demand by description. Vercel's evals (2026-01-27): an 8 KB index inlined in AGENTS.md passed 100%, skills 53% by default and 79% with explicit instructions, never invoked in 56% of cases. Prior art: sorcerai/skill-router (MCP server with skill_search / skill_load over `~/.claude/skill-vault`), registry MCP servers with search then get; vercel-labs/skills issue 634 (disable/enable, open). Routing research: groups of 4-8 per level (2601.04748). Pitfalls: junctioned skills missing from the desktop `/` menu (claude-code 68318), plugin cache paths change per version.
- Track: subject, tooling, practice
- Sources: https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/memory, https://code.claude.com/docs/en/context-window, https://learn.chatgpt.com/docs/build-skills, https://code.visualstudio.com/docs/copilot/customization/agent-skills, https://cursor.com/docs/context/rules, https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals, https://github.com/sorcerai/skill-router, https://github.com/vercel-labs/skills/issues/634, https://arxiv.org/html/2601.04748v2
- Magnitude: 0.5
- Applied: C-20260926-3 (park, unpark, parked; references/parking.md)

### R-20260926-3 · 2026-09-26 · Subject: progressive disclosure of skill bodies
- Summary: Anthropic's authoring guide: only name and description preload; SKILL.md is read when the skill is relevant and bundled files only when read ("no context penalty for large files" until accessed); SKILL.md is an overview pointing to reference files; body under 500 lines; references one level deep (nested files may be previewed with head -100); a table of contents in reference files over 100 lines; forward slashes. SkillReducer (arXiv 2603.29919, rev. 2026-06-24): over 60% of body content is non-actionable; taxonomy-driven classification plus progressive disclosure cut bodies 39% and descriptions 48% while functional quality rose 2.8%, retained across five models (0.965).
- Track: subject
- Sources: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices, https://arxiv.org/abs/2603.29919
- Magnitude: 0.4
- Applied: C-20260926-3 (sections, split, ST020-ST023)

### R-20260926-2 · 2026-09-26 · Tooling and testing: what exists, and the gap skill-tidy fills
- Summary: `/skill-doctor` covers per-skill cost, usage and never-invoked skills but not description quality or overlap; spec linters (skills-lint, skillscheck, skillmd-lint, agent-skill-linter) check fields and some similarity; skillprune and claude-skill-usage read transcripts for dead skills; skill-creator's `run_loop` optimises descriptions with a model and a 20-query eval set (60/40 split, 3 runs, 5 iterations). Claude Code transcripts record skill use as an assistant `tool_use` named `Skill` with `input.skill` (verified on the development machine); slash commands appear as `<command-name>` tags (format internal). Codex rollouts carry `<skill><name>` blocks (third-party parser). No tool combines cross-host rules, per-host budgets, a trigger-preserving rewrite check and multi-host config output.
- Track: tooling, testing
- Sources: https://code.claude.com/docs/en/whats-new, https://github.com/anthropics/skills, https://github.com/hyuga611/skills-lint, https://github.com/dahoai/skillprune, https://github.com/MindiveLabs/skill-doctor, https://code.claude.com/docs/en/plugin-evals
- Magnitude: n/a (initial)
- Applied: C-20260926-1

### R-20260926-1 · 2026-09-26 · Subject: selection research and vendor description rules
- Summary: see Current understanding, first five bullets. Key numbers verified against the abstracts or paper HTML on 2026-09-26: 2601.04748 (above 90% to 20 skills, degrades past 30, competitors 7-63 points, routing +37-40 at scale), 2605.24050 (up to 21% drop at 202 skills, shadowing the primary cause, context overhead indistinguishable from zero), 2606.10388 (Recall@3 0.848-0.888, harmful sibling rate 0.346-0.372, score-and-cluster 0.128-0.182), 2606.30775 (79.2% vs 79.4% F1, 3.8 vs 120 minutes, dual editing under 0.5%). Claude Code skills page read directly for skillOverrides values, the 1,536 cut, "key use case first", `paths` and `disable-model-invocation`.
- Track: subject
- Sources: https://arxiv.org/html/2601.04748v2, https://arxiv.org/abs/2605.24050, https://arxiv.org/abs/2606.10388, https://arxiv.org/abs/2606.30775, https://arxiv.org/abs/2609.02035, https://arxiv.org/html/2510.20036, https://agentskills.io/specification, https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices, https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/settings, https://learn.chatgpt.com/docs/build-skills, https://code.visualstudio.com/docs/copilot/customization/agent-skills, https://cursor.com/docs/skills
- Magnitude: n/a (initial)
- Applied: C-20260926-1
