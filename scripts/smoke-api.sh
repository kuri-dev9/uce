#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${UCE_BASE_URL:-http://localhost:8100}"

echo "== GET /health =="
curl -sS "${BASE_URL}/health"
echo
echo

echo "== GET /status =="
curl -sS "${BASE_URL}/status"
echo
echo

echo "== POST /build-context =="
curl -sS -X POST "${BASE_URL}/build-context" \
  -H "Content-Type: application/json" \
  --data-binary @examples/build-context.sample.json
echo
echo

echo "== POST /analyze-response =="
curl -sS -X POST "${BASE_URL}/analyze-response" \
  -H "Content-Type: application/json" \
  --data-binary @examples/analyze-response.sample.json
echo
echo

echo "== POST /build-context topic shift sample =="
curl -sS -X POST "${BASE_URL}/build-context" \
  -H "Content-Type: application/json" \
  --data-binary @examples/topic-shift.sample.json
echo
