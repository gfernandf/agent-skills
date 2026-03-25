#!/usr/bin/env bash
# Generate Go client from OpenAPI spec.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPEC="${SCRIPT_DIR}/../docs/specs/consumer_facing_v1_openapi.json"
OUT="${SCRIPT_DIR}/go"

echo "[sdk] Generating Go client from ${SPEC}"

if command -v openapi-generator-cli &>/dev/null; then
  openapi-generator-cli generate \
    -i "${SPEC}" \
    -g go \
    -o "${OUT}" \
    --additional-properties=packageName=agentskills,isGoSubmodule=true
elif command -v docker &>/dev/null; then
  docker run --rm \
    -v "${SCRIPT_DIR}/..:/local" \
    openapitools/openapi-generator-cli generate \
    -i /local/docs/specs/consumer_facing_v1_openapi.json \
    -g go \
    -o /local/sdk/go \
    --additional-properties=packageName=agentskills,isGoSubmodule=true
else
  echo "ERROR: openapi-generator-cli or docker required."
  exit 1
fi

echo "[sdk] Go client generated in ${OUT}"
