#!/usr/bin/env bash
set -euo pipefail

if ! command -v modelops-sentinel >/dev/null 2>&1; then
  echo "modelops-sentinel is not installed in the active environment." >&2
  echo "Run: python -m pip install -e ." >&2
  exit 2
fi

args=(
  --vllm-url "${VLLM_BASE_URL:-http://127.0.0.1:8000}"
  --timeout "${AUDIT_TIMEOUT:-10}"
  --format "${AUDIT_FORMAT:-table}"
)

if [[ -n "${VLLM_MODEL:-${SERVED_MODEL_NAME:-}}" ]]; then
  args+=(--model "${VLLM_MODEL:-$SERVED_MODEL_NAME}")
fi

if [[ -n "${VLLM_API_KEY:-}" ]]; then
  args+=(--api-key "$VLLM_API_KEY")
fi

if [[ -n "${PROMETHEUS_URL:-}" ]]; then
  args+=(--prometheus-url "$PROMETHEUS_URL")
fi

if [[ -n "${AUDIT_OUTPUT:-}" ]]; then
  args+=(--output "$AUDIT_OUTPUT")
fi

exec modelops-sentinel "${args[@]}"

