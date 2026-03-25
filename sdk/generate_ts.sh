#!/usr/bin/env bash
# Generate TypeScript client from OpenAPI spec.
# Requires: @openapitools/openapi-generator-cli (npm) or Docker.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SPEC="${SCRIPT_DIR}/../docs/specs/consumer_facing_v1_openapi.json"
OUT="${SCRIPT_DIR}/typescript"

echo "[sdk] Generating TypeScript client from ${SPEC}"

if command -v openapi-generator-cli &>/dev/null; then
  openapi-generator-cli generate \
    -i "${SPEC}" \
    -g typescript-fetch \
    -o "${OUT}" \
    --additional-properties=npmName=@agent-skills/client,npmVersion=0.1.0,supportsES6=true,typescriptThreePlus=true
elif command -v docker &>/dev/null; then
  docker run --rm \
    -v "${SCRIPT_DIR}/..:/local" \
    openapitools/openapi-generator-cli generate \
    -i /local/docs/specs/consumer_facing_v1_openapi.json \
    -g typescript-fetch \
    -o /local/sdk/typescript \
    --additional-properties=npmName=@agent-skills/client,npmVersion=0.1.0,supportsES6=true,typescriptThreePlus=true
else
  echo "ERROR: openapi-generator-cli or docker required. Install with:"
  echo "  npm install -g @openapitools/openapi-generator-cli"
  exit 1
fi

echo "[sdk] TypeScript client generated in ${OUT}"
echo "[sdk] To publish: cd ${OUT} && npm publish --access public"
