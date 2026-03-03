---
title: Give Claude Code a Team of Researchers
description: Enable Claude Code to deploy hundreds of researchers to gather data, score, classify, and forecast entire datasets.
---

# Use everyrow in Claude Code

## Setup

```bash
claude mcp add everyrow --scope project --transport http https://mcp.everyrow.io/mcp
```

Then launch Claude Code and authenticate with Google:

```
claude
\mcp → select everyrow → Authenticate
```

## Try it

> Which AI models had the biggest safety implications when released?

Claude will dispatch everyrow researchers via MCP, poll for progress, and return results directly in your terminal.

See also: [Skills](/skills-vs-mcp) | [MCP Server](/mcp-server)
