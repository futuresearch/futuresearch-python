---
title: Give Claude Cowork a Team of Researchers
description: Give Claude Cowork a research team that can gather data, forecast, score, classify, or rank entire datasets.
---

# Use everyrow in Claude Cowork

Cowork is a tab in the Claude Desktop app for multi-step autonomous tasks. With everyrow connected, Cowork can deploy a team of researchers to gather data, score, classify, and forecast entire datasets.

## Setup

1. Open Claude Desktop (download from [claude.ai/download](https://claude.ai/download) if needed)
2. Go to Settings → Connectors → Add custom connector
3. Enter the remote MCP URL: `https://mcp.everyrow.io/mcp`
4. Go to Settings → Capabilities → Code execution and file creation → Additional allowed domains and add `mcp.everyrow.io` (this lets Claude upload your CSVs for the researchers to process.)

Sign in with Google to authenticate. The connector is shared across Chat, Cowork, and Code tabs in Claude Desktop.

## Try it

Switch to the Cowork tab, and ask:

> Which S&P 500 companies are most exposed to China-Taiwan risk?

## Learn more

- [Get started with Cowork](https://support.claude.com/en/articles/13345190-get-started-with-cowork) (Claude Help Center)
