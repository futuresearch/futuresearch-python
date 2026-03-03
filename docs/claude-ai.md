---
title: Give claude.ai a Team of Researchers
description: Add everyrow as a connector in Claude.ai to deploy researchers to gather data, score, classify, or forecast.
---

# Use everyrow in Claude.ai

## Setup

1. Go to Settings → Connectors → Add custom connector
2. Enter the remote MCP URL: `https://mcp.everyrow.io/mcp`
3. Go to Settings → Capabilities → Code execution and file creation → Additional allowed domains and add `mcp.everyrow.io` — this lets Claude upload your CSVs for the researchers to process.

Sign in with Google to authenticate.

## Try it

Ask Claude:

> Which US companies are most pro-AI?

## Same setup for Claude Desktop

Claude Desktop (the native app) uses the same Connectors settings. Add the connector once and it works in both Chat and the Desktop app.

See also: [Use everyrow in Claude Cowork](/claude-cowork)
