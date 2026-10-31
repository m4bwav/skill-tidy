# MCP servers and "parking" (2026-10-11)

Related: [ai-docs index](../INDEX.md)

Question: skills have a parking lot; can MCP servers get one, loaded on demand, instead of toggling them by hand?

## Finding: Claude Code already parks MCP tools

Source: https://code.claude.com/docs/en/mcp, sections "Scale with MCP tool search" and "Configure tool search" (read 2026-10-11).

- Tool search is on by default. Only tool **names** and each server's **instructions** load at session start; full schemas load when the agent calls `ToolSearch`. Seen in a live session: about 190 MCP tools from claude.ai connectors and plugins listed by name only.
- `ENABLE_TOOL_SEARCH`: unset/`true` defers everything; `auto` / `auto:N` loads upfront below N% of context (default 10); `false` loads everything.
- Per server: `"alwaysLoad": true` loads that server's tools upfront; `"alwaysLoad": false` (v2.1.287+) keeps even author-marked tools deferred.
- Server instructions and tool descriptions are cut at 2,048 characters each (`CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH` changes it).
- `MCP_DISCOVERY_CACHE=1` (v2.1.221+): remote HTTP/SSE servers use cached tool lists and connect on first use, so they cost no startup connection.

## What still costs something

1. The name list: roughly 10 to 15 tokens per tool, so a few thousand tokens for 190 tools.
2. Server instructions: up to 2,048 characters per server (some connectors send long ones).
3. Local stdio servers still start a process each session.

## Levers for the remainder

- Servers never used from Claude Code: turn off per project in `/mcp` (stored as `disabledMcpServers` in `~/.claude.json`), or block by name with `deniedMcpServers` (for example `"claude.ai Slack"`); `disableClaudeAiConnectors: true` drops every claude.ai connector.
- A single proxy MCP server that fronts parked servers would only save the name list, and tool search already removed the big cost, so it was judged not worth building.
- Possible skill-tidy feature: report per-server name-list and instruction size so the user can see which servers are worth disabling.
