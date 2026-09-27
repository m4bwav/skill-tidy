---
type: regex
target: { source: file, path: fixture/.claude/skills/feed-scan/SKILL.md }
flags: m
match: not_contains
pattern: '^description: Collect articles from news feeds about databases and storage engines, summarise each article into notes, tag topics and track trends\. Use when the user says .scan the feeds. or .what is new in databases.\.\r?$'
---
