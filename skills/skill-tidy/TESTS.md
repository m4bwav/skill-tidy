# Tests: skill-tidy

Test runs for [SKILL.md](SKILL.md). Cases live in `evals/evals.json`. A failure that taught something is a lesson in [LEARNINGS.md](LEARNINGS.md); a fix it caused is logged in [CHANGELOG.md](CHANGELOG.md) with `because: T-...`; research it triggered is in [RESEARCH.md](RESEARCH.md); counts and the failing list are in `evergreen.json` under `tests`. Rules: MAINTENANCE.md (testing section) and the plugin's `protocol/TESTING.md`.

A test passes on evidence (a tool call in the trace, a file, a marker, a log line), never on the transcript's claim that something was done.

Entry shape: `### T-YYYYMMDD-n · date · harness · env · passed/total`, then one line per failing case (`id · kind · class · what the evidence showed`), then `led to:` (L-, C-, R- ids or none). Newest first. Budget 150 lines; archive older runs to `TESTS-ARCHIVE.md`.

## Runs

### T-20260926-2 · 2026-09-26 · claude plugin eval 2.1.281 (default model, 1 run per case, --ablation none) · Windows 11 native for trigger and decoy, WSL2 Ubuntu (bwrap, socat) for the Bash cases · 6/6
- Suite: the root `evals/` folder, cases converted from `evals/evals.json`. Trigger and decoy graders are `tool_used` on Skill with a regex on the skill name (max 0 for a decoy). Native: `claude plugin eval . --ablation none --no-publish -j 4 --tag trigger --trust-plugin`, 4/4, 0.78 USD, 72 s. WSL2: `--tag bash --scaffold --allow-tools Bash Write Edit`, 2/2, 0.36 USD, 31 s.
- trigger-1, trigger-2 · trigger · pass · `Skill(skill-tidy:skill-tidy)` called once each (both then hit the 3-turn cap, which is the case's limit, not a failure).
- decoy-1 (session size), decoy-2 (new git-log skill) · trigger · pass · skill-tidy not called.
- action-1 · action · pass · Skill first, then `tidy.py conflicts` in the trace. Finding: it reported 0 listed skills, because the run keeps its config in `CLAUDE_CONFIG_DIR` and `tidy.py` only scans `~/.claude`; the model noticed and worked around it.
- outcome-1 · outcome · pass · fixture `fixture/.claude/skills/feed-scan` and `radar-sweep` (cosine 0.60). Trace: `tidy.py check` printed OK twice, then `tidy.py apply` wrote the file with a backup under the run's `~/.skill-tidy/backups/`; similarity 0.60 to 0.30; new description 409 chars, keeps 'scan the feeds' and 'what is new in databases', ends with one sentence pointing the daily digest to radar-sweep (judge expectation checked by reading the trace, not graded).
- Not runnable on native Windows: action-1 and outcome-1 need a Bash grant, and the run is refused there ("Windows sandbox is not active on this session (feature gate off)"). They run under WSL2.
- Caveats: the eval config is throwaway, so the catalog held only this plugin and built-ins; decoy-1 proves skill-tidy does not take session-size prompts, not that context-health wins them. An earlier WSL attempt failed only the two Bash graders because their regex required `tidy.py apply` literally and the model called it through `$T apply`; the graders (and the evidence regex in `evals.json`) now allow text between `tidy.py` and the subcommand.
- led to: none (the CLAUDE_CONFIG_DIR gap is in ai-docs/HANDOFF.md as the next action)

### T-20260926-1 · 2026-09-26 · not yet run · skill · 0/0
- Suite scaffolded; no run recorded. Write the cases in `evals/evals.json` (at least two trigger prompts, two decoys, one action case with evidence, one outcome case), run the baseline without the skill, then run with it (`evergreen-test`).
- led to: none
