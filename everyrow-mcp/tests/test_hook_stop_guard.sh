#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)/scripts"
TASK_FILE="$HOME/.everyrow/task.json"

# Setup: ensure clean state
mkdir -p "$HOME/.everyrow"
rm -f "$TASK_FILE"

# Test 1: Blocks when task is running (recently started)
NOW=$(date +%s)
echo "{\"task_id\":\"abc-123\",\"status\":\"running\",\"total\":50,\"completed\":10,\"started_at\":$NOW}" > "$TASK_FILE"
RESULT=$(echo '{"stop_hook_active": false}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
echo "$RESULT" | jq -e '.decision == "block"' || { echo "FAIL: should block"; exit 1; }
echo "$RESULT" | jq -e '.reason | contains("abc-123")' || { echo "FAIL: reason should contain task_id"; exit 1; }
echo "PASS: blocks when running"

# Test 2: Allows when stop_hook_active (prevent infinite loop)
RESULT=$(echo '{"stop_hook_active": true}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
[ -z "$RESULT" ] || { echo "FAIL: should produce no output when allowing"; exit 1; }
echo "PASS: allows when stop_hook_active"

# Test 3: Allows when no task file
rm -f "$TASK_FILE"
RESULT=$(echo '{"stop_hook_active": false}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
[ -z "$RESULT" ] || { echo "FAIL: should allow when no task"; exit 1; }
echo "PASS: allows when no task"

# Test 4: Allows when task is completed
echo '{"task_id":"abc-123","status":"completed","total":50,"completed":50}' > "$TASK_FILE"
RESULT=$(echo '{"stop_hook_active": false}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
[ -z "$RESULT" ] || { echo "FAIL: should allow when completed"; exit 1; }
echo "PASS: allows when completed"

# Test 5: Allows when task file is stale (mtime > 30 min ago)
echo "{\"task_id\":\"abc-123\",\"status\":\"running\",\"total\":50,\"completed\":10,\"started_at\":$NOW}" > "$TASK_FILE"
# Set file mtime to 2 hours ago
touch -t "$(date -v-2H '+%Y%m%d%H%M.%S' 2>/dev/null || date -d '2 hours ago' '+%Y%m%d%H%M.%S')" "$TASK_FILE"
RESULT=$(echo '{"stop_hook_active": false}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
[ -z "$RESULT" ] || { echo "FAIL: should allow when stale"; exit 1; }
[ ! -f "$TASK_FILE" ] || { echo "FAIL: should remove stale task file"; exit 1; }
echo "PASS: allows and cleans up stale task (mtime-based)"

# Test 6: Blocks when task file is recent (mtime < 30 min ago, i.e. just written)
echo "{\"task_id\":\"abc-123\",\"status\":\"running\",\"total\":50,\"completed\":10,\"started_at\":$NOW}" > "$TASK_FILE"
RESULT=$(echo '{"stop_hook_active": false}' | bash "$SCRIPT_DIR/everyrow-stop-guard.sh")
echo "$RESULT" | jq -e '.decision == "block"' || { echo "FAIL: should block recent task"; exit 1; }
echo "PASS: blocks recent running task"

# Cleanup
rm -f "$TASK_FILE"
echo "ALL PASS: stop guard"
