#!/usr/bin/env bash
set -euo pipefail

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
}

require_env MODEL_PATH
require_env SERVED_MODEL_NAME
require_env VLLM_API_KEY

if ! command -v vllm >/dev/null 2>&1; then
  echo "vllm is not installed in the active environment." >&2
  echo "Create a venv and install the vLLM version compatible with your CUDA stack." >&2
  exit 2
fi

if [[ ! -d "$MODEL_PATH" ]]; then
  echo "MODEL_PATH is not a directory: $MODEL_PATH" >&2
  exit 2
fi

args=(
  serve "$MODEL_PATH"
  --host "${VLLM_HOST:-0.0.0.0}"
  --port "${VLLM_PORT:-8000}"
  --served-model-name "$SERVED_MODEL_NAME"
  --tensor-parallel-size "${TENSOR_PARALLEL_SIZE:-1}"
  --api-key "$VLLM_API_KEY"
)

if [[ "${TRUST_REMOTE_CODE:-0}" == "1" ]]; then
  args+=(--trust-remote-code)
fi

if [[ "${ENABLE_EXPERT_PARALLEL:-0}" == "1" ]]; then
  args+=(--enable-expert-parallel)
fi

if [[ -n "${TOOL_CALL_PARSER:-}" ]]; then
  args+=(--enable-auto-tool-choice --tool-call-parser "$TOOL_CALL_PARSER")
fi

if [[ -n "${REASONING_PARSER:-}" ]]; then
  args+=(--reasoning-parser "$REASONING_PARSER")
fi

if [[ -n "${VLLM_EXTRA_ARGS:-}" ]]; then
  read -r -a extra_args <<< "$VLLM_EXTRA_ARGS"
  args+=("${extra_args[@]}")
fi

echo "Starting vLLM model '$SERVED_MODEL_NAME' on ${VLLM_HOST:-0.0.0.0}:${VLLM_PORT:-8000}"
echo "Model directory: $MODEL_PATH"
echo "Tensor parallel size: ${TENSOR_PARALLEL_SIZE:-1}"

exec env SAFETENSORS_FAST_GPU="${SAFETENSORS_FAST_GPU:-1}" vllm "${args[@]}"

