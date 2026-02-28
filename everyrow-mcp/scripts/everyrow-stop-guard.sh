#!/bin/bash
set -e

# Check for jq dependency
command -v jq >/dev/null 2>&1 || { echo "jq required" >&2; exit 1; }

INPUT=$(cat)
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false')

# Don't block if already in a stop-hook continuation (prevent infinite loop)
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  exit 0
fi

TASK_FILE="$HOME/.everyrow/task.json"
STALE_SECONDS=3600  # 60 minutes

if [ -f "$TASK_FILE" ]; then
  STATUS=$(jq -r '.status' "$TASK_FILE")
  TASK_ID=$(jq -r '.task_id' "$TASK_FILE")

  if [ "$STATUS" = "running" ]; then
    # Check staleness using file mtime (updated on every everyrow_progress poll).
    # If no poll has happened in STALE_SECONDS, the session that started this
    # task is likely dead — clean up rather than blocking all future sessions.
    if [[ "$(uname)" == "Darwin" ]]; then
      FILE_MTIME=$(stat -f %m "$TASK_FILE")
    else
      FILE_MTIME=$(stat -c %Y "$TASK_FILE")
    fi
    NOW=$(date +%s)
    ELAPSED=$(( NOW - FILE_MTIME ))

    if [ "$ELAPSED" -gt "$STALE_SECONDS" ]; then
      rm -f "$TASK_FILE"
      exit 0
    fi

    jq -n \
      --arg reason "[everyrow] Task $TASK_ID still running. Call everyrow_progress(task_id=\"$TASK_ID\") to check status." \
      '{decision: "block", reason: $reason}'
    exit 0
  fi
fi

exit 0
