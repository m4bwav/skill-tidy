---
type: regex
target: { source: file, path: fixture/.claude/skills/feed-scan/SKILL.md }
flags: m
pattern: '^description: (?:"[^\r\n]{1,1024}"|[^"\r\n][^\r\n]{0,1023})\r?$'
---
