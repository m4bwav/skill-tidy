# Lint rules

`tidy.py lint` applies these to every listed skill (or the folders given). Errors are spec or host limits: a host truncates, drops or rejects the skill. Warnings are research-backed style. Info is advice. Evidence ids point at [../RESEARCH.md](../RESEARCH.md).

| Rule | Severity | Check | Evidence |
|---|---|---|---|
| ST001 | error | name is 1-64 chars of `a-z0-9` with single hyphens | Agent Skills spec (R-20260926-1) |
| ST002 | warn | name matches the folder name | spec |
| ST003 | error | name contains `anthropic` or `claude` | Anthropic best practices |
| ST004 | error | description missing or empty | spec; hosts fall back to the first body line |
| ST005 | error | description over 1,024 chars | spec; Copilot reported to drop longer ones |
| ST006 | error | description + `when_to_use` over 1,536 chars | Claude Code cuts the listing there |
| ST007 | warn | over 200 words | skill-creator rewriter: about 100-200 words |
| ST008 | warn | 40 chars or fewer, or under 8 words | Anthropic: "Helps with documents" is too vague |
| ST009 | warn | no "Use when / Use for / Use whenever" clause | spec, Anthropic, Copilot: say what and when |
| ST010 | warn | first or second person in the prose ("I can", "you can"; quoted user phrases are ignored) | Anthropic: third person; the imperative "Use when" is fine |
| ST011 | info | vague words ("helps with", "various", "stuff", "etc") | Anthropic best practices |
| ST012 | error | XML-like tag | Anthropic skill rules |
| ST013 | warn | more than 12 quoted trigger phrases | skill-creator (no ever-expanding query lists), skillscheck keyword stuffing |
| ST014 | info | first sentence opens generically ("This skill", "Helps") | Claude Code and Codex: key use case first |
| ST015 | warn | steering phrases ("always use this", "prefer this skill") | arXiv 2609.02035: shaping moves selection 15% to 64% |
| ST016 | warn | body over 500 lines or about 5K tokens | spec guidance; move detail to references/ |
| ST017 | error | `compatibility` over 500 chars | spec |
| ST018 | info | triggers kept in `when_to_use` | only Claude Code reads it |
| ST019 | warn | similarity 0.45+ to another listed skill and no boundary sentence | 2601.04748, 2605.24050, 2606.10388; the threshold is inference (R-20260926-1) |

## Similarity

TF-IDF cosine over description words (plus `when_to_use`), smoothed IDF over the listed catalog, stop words and every skill and plugin name word removed, light suffix stripping. 0.45 = possibly confusable, 0.65 = near-duplicate. Siblings are scored because same-family siblings are the documented risk. The numbers are uncalibrated: treat a pair as something to look at, not a verdict.

## Rewrite check (`check`, `apply`)

A proposed description passes when it has no lint error, every quoted trigger of the old text is still carried (all its distinctive words appear in the new text, quoted or not), and its closest similarity is reported before and after. `apply` refuses a failing check (unless `--force`), refuses installed plugin copies under `plugins/cache`, keeps the file's other front matter and line endings, and backs the file up under `~/.skill-tidy/backups/`.
