---
title: "skill-tidy as its own plugin: script checks, model rewrites once"
kind: decision
status: active
date: 2026-09-26
verified: 2026-09-26
stale_after: 2027-03-25
tags: [design, skills, selection, tokens]
summary: read before adding a command or moving work between skill-tidy and context-health
---

# skill-tidy as its own plugin: script checks, model rewrites once

## Context

The user wanted the two remaining skill conflicts on the development machine fixed without losing functionality, description clean-up based on current research, and token-saving scripts, as an evergreen plugin. context-health already detects selection noise; fixing it is a different job.

## Decision

- A separate plugin, skill-tidy, with one skill and one stdlib CLI (`tidy.py`): lint (ST001-ST019), conflicts, check, apply, budget, usage, offload, startup, harvest. context-health keeps detecting.
- One skill, not several: the plugin that fixes catalog noise should not add to it.
- The rewrite itself is the model's judgment. The script checks it (lint, triggers kept, similarity before and after) and writes it only when the check passes, with a backup, never into an installed plugin copy.
- Token saving writes `skillOverrides` "name-only" (still invocable, no description cost) only with `--write`; plugin skills are pointed at `/plugin`, Codex gets `enabled = false` lines.

## Reasons

- 2606.30775: one rewrite fed with false-positive and false-negative cases gets most of the gain, so `harvest` builds that brief instead of an optimisation loop.
- `/skill-doctor` already reports cost and use; skill-tidy covers description quality, conflicts and other hosts rather than repeating it.
- Rules each cite evidence (references/rules.md), so a refresh can move them when hosts change.

## Rejected

- Extending context-health: its description is already over the spec limit, and measuring and fixing are different jobs.
- An LLM-in-the-loop optimiser like skill-creator's `run_loop`: costly per run and already exists.

Related: [INDEX.md](../INDEX.md)
