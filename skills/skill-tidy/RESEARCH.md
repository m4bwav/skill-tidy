# Research: skill-tidy

Findings that back [SKILL.md](SKILL.md) and [references/rules.md](references/rules.md). Changes they caused are logged in [CHANGELOG.md](CHANGELOG.md); procedural lessons live in [LEARNINGS.md](LEARNINGS.md); test runs and their evidence in [TESTS.md](TESTS.md); schedule and state in `evergreen.json`. Protocol: [MAINTENANCE.md](MAINTENANCE.md).

Topic: Agent Skills description quality and selection conflicts, skill catalog listing budgets and token cost per host (Claude Code, Codex, Copilot, Cursor), and startup-context trimming. Tier `fast`. Last refresh 2026-10-23.

## Current understanding

- **Overlap costs more than count.** Selection accuracy stays above 90% up to about 20 skills and degrades beyond 30 (arXiv 2601.04748, GPT-4o-class models, synthetic skills). At a fixed catalog size, hand-written competitor skills cost 7-63 points. As libraries grow to 202 skills, skill shadowing (wrong or abandoned selection) is the main cause of a pass-rate drop of up to 21%, while the larger context costs about nothing (2605.24050). Same-family siblings are the documented risk: retrievers with Recall@3 0.85-0.89 still expose a harmful sibling 35-37% of the time (2606.10388). At about 1,000 skills, irrelevant descriptions alone cause routing collapse (runs loading no skill rose from 9% to 52%), and hiding those descriptions largely undid it (2610.18522), so count matters too at that scale. Confident.
- **One rewrite is enough.** A single LLM rewrite fed with false-positive and false-negative cases reached 79.2% F1 against 79.4% for hand tuning, in 3.8 minutes instead of 120. Editing both sides of a confused pair changed F1 by under 0.5%. A large train-validation gap means the scopes really overlap and need an architectural fix (merge), not new wording (2606.30775). Confident.
- **Description rules (vendor docs).** The Agent Skills spec: name 1-64 chars of `a-z0-9-`, matching the folder; description 1-1,024 chars saying what the skill does and when to use it, with specific keywords; `compatibility` at most 500. Anthropic: third person, no "I can" or "you can", no XML tags, reserved words `anthropic` and `claude` barred from names, avoid vague text like "Helps with documents". skill-creator's rewriter aims for about 100-200 words, uses the imperative "Use this skill for", and warns against ever-growing lists of example queries. Claude Code: put the key use case first; description plus `when_to_use` is cut at 1,536 chars. Codex: front-load the key use case and trigger words, state scope and boundaries. Confident; the third-person vs imperative split between Anthropic's guide and its own rewriter is reconciled by allowing both and flagging only first and second person.
- **Listing budgets.** Claude Code: `skillListingBudgetFraction` 0.01 of the window; over it, names stay and the least-used skills lose their descriptions; `skillListingMaxDescChars` 1,536. `skillOverrides` takes `on`, `name-only`, `user-invocable-only`, `off`, matches skill names, and does not affect plugin skills (use `/plugin`). `disable-model-invocation: true` removes a skill from the listing; `paths` limits auto-loading to matching files. Codex: 2% of the window, or 8,000 chars when unknown, overridable with `skills.max_context_tokens` up to 10,000 tokens; descriptions are shortened first, then skills omitted; `[[skills.config]] path enabled=false` in `~/.codex/config.toml`. Copilot: description 1,024, and descriptions longer than that are reported dropped (Copilot CLI issue 3494). Cursor documents no numbers; it reads `.agents`, `.cursor`, `.claude` and `.codex` skill roots, user and project (fixed in tidy.py 2026-10-23). Claude Code re-sends the skill list after compaction since v2.1.304. Confident for Claude Code and Codex; Copilot and Cursor skill roots in `tidy.py` are the least certain part (re-check each refresh).
- **Steering is a risk.** Semantic shaping of a description raised a target skill's selection from 15.2% to 63.5%, and people spotted it 2.9% of the time (2609.02035); the linter flags steering phrases.
- **Lexical similarity is a proxy.** No study validates TF-IDF or Jaccard on descriptions against model confusion. ToolScope uses embedding cosine 0.77-0.82 for merge candidates (2510.20036); lexical cosine runs lower, so 0.45 / 0.65 are inference, checked on one real 41-skill catalog (2 pairs over 0.45).
- **Existing tools** (checked 2026-09-26, updated 2026-10-11): Claude Code's `/skill-doctor` (v2.1.252) shows per-skill cost and use and flags never-invoked skills and unused plugins; it does not judge description quality or overlap. `/doctor` estimates the listing's cost and biggest contributors, and `/doctor prompt-audit` (v2.1.283) leads with stale paths, stale commands and contradicting instruction files across CLAUDE.md, skills, agents and commands, proposing diffs; neither judges description overlap. `claude plugin validate` (v2.1.233+) finds SKILL.md frontmatter that does not parse. claude-skills-doctor (PyPI 0.7.0, 2026-07-31) checks budget, the 1,536 cap, thin descriptions and near-duplicates deterministically (R-20261011-2). skills-lint (GitHub Action; spec fields, bigram near-duplicates at 0.7), skillscheck (spec, token counts, "use when" and keyword-stuffing warnings), MindiveLabs/skill-doctor (LLM conflict typing), skillprune (transcripts plus Jaccard 0.35), paultaki/claude-skill-usage (cost dashboard), skill-creator `run_loop` (model-driven trigger optimisation). google/skill-reach (2026-10, no release) is the closest: BM25 overlap, live routing probes through Claude Code and others, a recall-ranked optimiser and a lint with budget overflow (R-20261023-1); it lacks parking and host config output. skill-tidy adds what none of them combines: cross-host rules with cited evidence, per-host budgets, a trigger-preserving check before any rewrite is written, `skillOverrides` and Codex config output, and a one-rewrite brief from transcripts.

## Open questions

- A validated cheap similarity measure (would let 0.45 / 0.65 be calibrated).
- (resolved 2026-10-23, R-20261023-3) Cursor's roots; tidy.py fixed. Earlier, 2026-10-11 (R-20261011-1): Copilot's roots match tidy.py and Copilot CLI silently drops (not truncates) a description over 1,024 (issue 3494 open). Codex reads `.agents/skills` in every parent up to the repo root plus `~/.agents/skills` and `/etc/codex/skills`, does not document `~/.codex/skills`, and honours `agents/openai.yaml` `policy.allow_implicit_invocation: false`; tidy.py scans only `<project>/.agents/skills`, includes `~/.codex/skills` and ignores openai.yaml: fix `roots_for` and `scan`.
- Should `lint` flag an unknown frontmatter key as an error for claude.ai uploads and the Skills API, which reject it, while Claude Code ignores it (R-20261011-1)?
- Should `budget` read `SLASH_COMMAND_TOOL_CHAR_BUDGET` when it is set?
- (resolved 2026-10-11) Claude Code's listing budget unit is characters (the skills docs; `SLASH_COMMAND_TOOL_CHAR_BUDGET` sets it), so `tidy.py budget` is right and the everlast plugin's token-based `skill-budget` is about 4x lenient. Was: confirm on the next refresh (`/context` Skills row).
- Does routing collapse (2610.18522) appear at catalogs of about 40 skills, or only near 1,000? Its repository may have the curve.
- Whether a boundary sentence naming the sibling ("To X, use Y") helps or hurts selection: no paper tests it directly; vendor examples use it.

## Search plan

- arXiv API sorted by date with abstract phrases (`search_query=abs:%22skill+selection%22+OR+abs:%22skill+routing%22&sortBy=submittedDate`); `all:skill AND all:agent` is now robotics noise. The Claude Code changelog is newest first and long: fetch offsets 0-100000; the skills page's budget section is past offset 100000. Cursor and Codex skills pages are undated: diff them against Current understanding every refresh. Reddit: use fetchwright (WebSearch found nothing).

Four tracks; every refresh runs at least one query on each (scope each to the period since the last refresh; add the year).

Subject:

- `site:arxiv.org skill selection description agent skills library <year>`; `"skill shadowing" OR "skill description" optimization <year>`
- code.claude.com/docs/en/skills, /settings, /context-window, /whats-new (listing budget, skillOverrides, /skill-doctor); learn.chatgpt.com/docs/build-skills; code.visualstudio.com/docs/copilot/customization/agent-skills; cursor.com/docs/skills; agentskills.io/specification

Tooling:

- `path:SKILL.md "description" lint OR overlap OR conflict` on GitHub code search, recently updated; `npx skills@1.7.0 find "skill lint"`; skills.sh for install counts
- `"skill description" linter OR optimizer OR conflict "claude code" OR codex <year> site:github.com`
- Supersession sweep: `/skill-doctor` release notes (does it start judging descriptions?), google/skill-reach (first release, installs), skills-lint, skillscheck

Practice:

- `"too many skills" OR "wrong skill" "claude code" <month> <year>` on r/ClaudeAI, r/ClaudeCode, hn.algolia.com
- `site:anthropic.com/engineering skills <year>`; `site:simonwillison.net skills <year>`

Testing:

- `claude plugin eval` docs (trigger graders, `disallowed_tools`); skill-creator `run_eval` / `run_loop`; `reach eval` (google/skill-reach)
- `site:arxiv.org skill routing benchmark OR "skill retrieval" evaluation <year>`

Best sources (primary first): the vendor docs above, the Agent Skills spec, arXiv (2601.04748, 2605.24050, 2606.10388, 2606.30775, 2609.02035, 2510.20036, 2603.22455, 2603.29919), anthropics/skills (skill-creator), google/skill-reach. Noisy: SEO "best skills" listicles, scraped skill directories.

## Findings log

Newest first. `Track` is subject, tooling, practice, or testing.

### R-20261030-1 · 2026-10-30 · Quiet: Claude Code 2.1.309 namespaces --add-dir name clashes
- Summary: Claude Code 2.1.309 offers a skill in an `--add-dir` folder whose name is already taken as `<folder>:<name>` instead of making it unreachable; 2.1.312 fixed per-directory and `paths:` skills not found after a `cd`; 2.1.314 caps `~/.claude/skills/.trash`. No change to the listing budget or description limits in 2.1.282 to 2.1.314. Community posts on `skillListingBudgetFraction` repeat known facts. Tooling, practice, testing: nothing new.
- Track: subject (tooling, practice, testing quiet)
- Sources: https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md (checked 2026-10-30)
- Magnitude: 0.15
- Applied: none (RESEARCH.md only)

### R-20261023-1 · 2026-10-23 · Tooling and testing: google/skill-reach, a routing, collision and description-optimisation suite
- Summary: google/skill-reach (Apache-2.0, "not an officially supported Google product", 290 commits, active 2026-10-10 to 10-18, 12 stars, no release, installed with uv): `reach overlap` (BM25 competition with `--suggest` rewrites), `reach eval` (live routing probes through claude-code, antigravity, goose and pi, or an offline keyword baseline), `reach optimize` (synthesised candidates ranked by recall gain, written only with `--auto-apply`), `reach lint` (frontmatter, 1,024 overflow, catalog-budget-overflow, duplicate-capability above 92% semantic overlap, missing-mutual-handoff, unbounded-attractor phrasing); static discovery for Claude Code, Codex, Cursor and Copilot. Its docs say overlap must be confirmed by probes, matching "lexical similarity is a proxy". No parking, `skillOverrides` or Codex config output. Also: `claude plugin eval` 2.1.299 adds `--disallow-tools` / `disallowed_tools` (keep Agent out so a subagent cannot hide the skill choice) and scores API-error runs 0 with exit 1. skill-guard (PyPI, embedding or LLM `conflict`) and erphq/skillcheck (Jaccard collisions) seen, undated. claude-skills-doctor still 0.7.0. Practice: no October threads; Gauge CLI (HN 2026-10-20) lists "a Skill goes unused even when it should help" as common.
- Track: tooling, testing, practice
- Sources: https://github.com/google/skill-reach, https://google.github.io/skill-reach/cli/lint/, https://google.github.io/skill-reach/cli/overlap/, https://code.claude.com/docs/en/plugin-evals, https://pypi.org/pypi/claude-skills-doctor/json, https://github.com/gauge-sh/gauge-cli
- Magnitude: 0.45 (a comparable maintained tool; point)
- Applied: C-20261023-1 (SKILL.md Step 2 item 6; Current understanding: Existing tools)

### R-20261023-2 · 2026-10-23 · Subject: routing collapse from irrelevant descriptions (arXiv 2610.18522)
- Summary: "Lost in Implicit Routing" (2026-10-13) kept SkillsBench tasks and their right skills fixed and added 1,000 irrelevant skills: loaded-skill recall fell from 73.6% to 27.4% and runs loading no skill rose from 9.3% to 51.6%; wrong-skill loads were too rare to explain it (collapse, not shadowing). Hiding only the irrelevant skills' descriptions largely restored loading; choosing skills explicitly before the run kept recall at 73.9%. MetaCascade (2610.14836, 2026-10-10): poisoning metadata alone got malicious skills chosen, +35.5 points over baselines, supporting the steering rule.
- Track: subject
- Sources: https://arxiv.org/abs/2610.18522, https://github.com/jinlinll/lost-in-implicit-routing, https://arxiv.org/abs/2610.14836
- Magnitude: 0.4 (qualifies the opening claim; direct support for name-only offload and parking)
- Applied: C-20261023-1 (SKILL.md intro; Current understanding first bullet)

### R-20261023-3 · 2026-10-23 · Subject: host roots and budgets (Cursor roots, Codex override, Claude Code 2.1.299-2.1.310)
- Summary: cursor.com/docs/skills lists project `.agents/skills`, `.cursor/skills`, user `~/.agents/skills`, `~/.cursor/skills`, and for compatibility `.claude/skills`, `.codex/skills`, `~/.claude/skills`, `~/.codex/skills`; tidy.py scanned three of them. No Cursor description or budget numbers. Codex: `skills.max_context_tokens` overrides the 2% / 8,000-char budget up to 10,000 tokens (first skills list only). Claude Code 2.1.304 re-sends the skill list after compaction (`/reload-skills` sends only changes); 2.1.299 drops skills whose name has bidi, invisible or `<>` characters; 2.1.309 offers a name collision from `--add-dir` as `<folder>:<name>`; budget rules, `skillOverrides` values and the 1,536 cap re-checked unchanged; `/skill-doctor` and `/doctor prompt-audit` still do not judge overlap. Copilot unchanged (VS Code page 2026-10-21; issue 3494 open).
- Track: subject
- Sources: https://cursor.com/docs/skills, https://learn.chatgpt.com/docs/build-skills, https://code.claude.com/docs/en/changelog, https://code.claude.com/docs/en/skills, https://code.visualstudio.com/docs/copilot/customization/agent-skills, https://github.com/github/copilot-cli/issues/3494
- Magnitude: 0.35 (tidy.py undercounted Cursor's catalog)
- Applied: C-20261023-1 (scripts/tidy.py roots_for and parking-lot comment; SKILL.md Step 1 budget line; Current understanding: Listing budgets)

### R-20261011-1 · 2026-10-11 · Subject: co-installed similar skills conflict at the first read; budget is characters; host roots and limits
- Summary: arXiv 2610.11647 ("One Skill Too Many", 2026-10-08) mined 822,000 candidate pairs from about 21,000 repositories, confirmed 312 conflicting pairs and ran 6,368 trials: about one installed skill in four has a similar co-installed skill, a similar skill takes about one run in five, install location decides the winner more than listing order, the conflict is settled at the first skill read, and the final reply names the skill that actually ran in only 0.9% of substituted runs; the only mitigation tested is a pre-tool hook at the first skill read (description rewriting untested). The Claude Code skills docs confirm a character budget at 1% of the window, least-invoked skills losing descriptions first, a debug-log warning on overflow, `/doctor` estimates and `SLASH_COMMAND_TOOL_CHAR_BUDGET`; `/context` shows the size after the budget since v2.1.196. Unknown frontmatter keys: Claude Code ignores them, claude.ai uploads, the Skills API and `package_skill.py` reject them. Claude Code v2.1.290 finds a skill by its SKILL.md `name` when the folder differs (ST002 still required by the spec and VS Code); v2.1.295 caps subagent `skills:` preloads at 32; v2.1.296 raises MCP tool-description limits to 4,096 characters (16,384 through tool search); v2.1.286 gives a skill named `verify` pre-commit behaviour. Codex and Copilot roots: see Open questions. SkillSeek (arXiv 2609.38822): plain BM25 matched an LLM refinement loop for skill retrieval in 3 of 4 settings at about half the cost, indirect support for lexical measures.
- Track: subject
- Sources: https://arxiv.org/abs/2610.11647, https://code.claude.com/docs/en/skills, https://code.claude.com/docs/en/changelog, https://learn.chatgpt.com/docs/build-skills, https://code.visualstudio.com/docs/copilot/customization/agent-skills, https://github.com/github/copilot-cli/issues/3494, https://arxiv.org/abs/2609.38822
- Magnitude: 0.4 (a fix beyond rewording, and judging by transcripts, joins Step 2)
- Applied: C-20261011-1 (SKILL.md Step 1 budget line; Step 2 item 7)

### R-20261011-2 · 2026-10-11 · Tooling and testing: `/doctor prompt-audit`, claude-skills-doctor and other linters; decoy graders
- Summary: Claude Code v2.1.283 (2026-09-25) added `/doctor prompt-audit`, which audits CLAUDE.md, skills, agents and commands for outdated prompting patterns, leads with stale paths, stale commands and contradicting instruction files, and proposes diffs it applies only when asked; it does not judge description overlap or budgets, but it partly overlaps `TIDY startup`, so the description now names it as the owner of that job (point). claude-skills-doctor (PyPI 0.7.0, eight releases 07-23 to 07-31, none since) checks budget, the 1,536 cap, load failures, thin descriptions and near-duplicates (point). Smaller: skill-collision-guard (Jaccard plus regex policy conflicts, 1 star), swarmclawai/agent-skills-lint (exact-name collisions), skillmd-lint 1.4.0 (33 rules; anthropics/skills PR #1797 open, found claude-api's description at 1,068 characters). Testing: in `claude plugin eval`, `tool_used` with `min: 0, max: 0` asserts a tool was never called and `tool_used: Skill` does not count toward the score; 2610.11647 recommends scoring a skill's exclusive core functions, not completion alone. skill-creator unchanged since 2026-04-20. Practice: nothing new.
- Track: tooling, testing
- Sources: https://code.claude.com/docs/en/changelog, https://code.claude.com/docs/en/debug-your-config, https://pypi.org/pypi/claude-skills-doctor/json, https://github.com/Three-Liu/skill-collision-guard, https://github.com/swarmclawai/agent-skills-lint, https://github.com/anthropics/skills/pull/1797, https://code.claude.com/docs/en/plugin-evals
- Magnitude: 0.45 (an official audit now owns part of Step 3's startup job)
- Applied: C-20261011-1 (SKILL.md description boundary; Step 3 Startup; RESEARCH.md Existing tools)

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
