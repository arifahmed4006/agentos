#!/usr/bin/env bash
# Strips embedded credentials from n8n workflow exports before committing.
# Usage: ./scripts/sanitize-workflow.sh agents/document-chaser/workflow.json

set -e

FILE="$1"

if [ -z "$FILE" ]; then
  echo "Usage: $0 path/to/workflow.json"
  exit 1
fi

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE"
  exit 1
fi

if ! command -v jq &> /dev/null; then
  echo "jq is required. Install: sudo apt install jq"
  exit 1
fi

cp "$FILE" "$FILE.bak"
jq '(.nodes[]?.credentials) |= {}' "$FILE.bak" > "$FILE"

echo "Sanitized $FILE — credential blocks cleared."
echo "Backup saved at $FILE.bak — delete once verified."

grep -in -E "api[_-]?key|token|password|secret|bearer" "$FILE" && \
  echo "WARNING: Possible sensitive strings found above — review before committing." || \
  echo "No obvious secrets found."
