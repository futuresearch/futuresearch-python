#!/bin/bash
set -e

# Check for jq dependency (exit silently to avoid breaking Claude Code UI)
command -v jq >/dev/null 2>&1 || exit 0

GREEN='\033[32m'
YELLOW='\033[33m'
CYAN='\033[36m'
DIM='\033[2m'
RESET='\033[0m'

TASK_FILE="$HOME/.everyrow/task.json"

if [ -f "$TASK_FILE" ]; then
  TASK=$(cat "$TASK_FILE")
  TASK_TYPE=$(echo "$TASK" | jq -r '.task_type // empty')
  STATUS=$(echo "$TASK" | jq -r '.status')
  COMPLETED=$(echo "$TASK" | jq -r '.completed // 0')
  TOTAL=$(echo "$TASK" | jq -r '.total // 0')
  FAILED=$(echo "$TASK" | jq -r '.failed // 0')
  URL=$(echo "$TASK" | jq -r '.session_url // empty')
  STARTED=$(echo "$TASK" | jq -r '.started_at // 0' | cut -d. -f1)
  ELAPSED=$(( $(date +%s) - STARTED ))

  if [ "$STATUS" = "running" ] && [ "$TASK_TYPE" = "screen" ]; then
    LINK=""
    if [ -n "$URL" ]; then
      LINK=" $(printf '%b' "\e]8;;${URL}\a⬡ view\e]8;;\a")"
    fi

    echo -e "${GREEN}everyrow${RESET} running ${DIM}${ELAPSED}s${RESET}${LINK}"
  elif [ "$STATUS" = "completed" ] && [ "$TASK_TYPE" = "screen" ]; then
    LINK=""
    if [ -n "$URL" ]; then
      LINK=" $(printf '%b' "\e]8;;${URL}\a⬡ view\e]8;;\a")"
    fi

    echo -e "${GREEN}everyrow${RESET} ✓ done${LINK}"
  elif [ "$STATUS" = "running" ] && [ "$TOTAL" -gt 0 ]; then
    TASK_PCT=$((COMPLETED * 100 / TOTAL))
    BAR_WIDTH=15
    FILLED=$((TASK_PCT * BAR_WIDTH / 100))
    EMPTY=$((BAR_WIDTH - FILLED))
    BAR=$(printf "%${FILLED}s" | tr ' ' '█')$(printf "%${EMPTY}s" | tr ' ' '░')

    FAIL_STR=""
    [ "$FAILED" -gt 0 ] && FAIL_STR=" ${YELLOW}${FAILED} failed${RESET}"

    LINK=""
    if [ -n "$URL" ]; then
      LINK=" $(printf '%b' "\e]8;;${URL}\a⬡ view\e]8;;\a")"
    fi

    echo -e "${GREEN}everyrow${RESET} ${BAR} ${COMPLETED}/${TOTAL} ${DIM}${ELAPSED}s${RESET}${FAIL_STR}${LINK}"
  elif [ "$STATUS" = "completed" ]; then
    echo -e "${GREEN}everyrow${RESET} ✓ done (${COMPLETED}/${TOTAL})"
  fi
fi
