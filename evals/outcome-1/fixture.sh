#!/usr/bin/env bash
# Seeds the outcome-1 workspace: two project skills whose descriptions overlap heavily.
set -e
mkdir -p fixture/.claude/skills/feed-scan fixture/.claude/skills/radar-sweep
cat > fixture/.claude/skills/feed-scan/SKILL.md <<'MD'
---
name: feed-scan
description: Collect articles from news feeds about databases and storage engines, summarise each article into notes, tag topics and track trends. Use when the user says 'scan the feeds' or 'what is new in databases'.
---

# feed-scan

Read each configured news feed, summarise new articles into notes/, tag each note with its topics, and update trends.md.
MD
cat > fixture/.claude/skills/radar-sweep/SKILL.md <<'MD'
---
name: radar-sweep
description: Sweep news feeds every morning for articles about databases and storage engines, summarise each article into notes, tag topics and track trends in a daily radar digest. Use when the user says 'run the radar' or 'daily sweep'.
---

# radar-sweep

Once a day, read the same feeds, keep only articles from the last 24 hours, and write a short digest to radar/YYYY-MM-DD.md.
MD
