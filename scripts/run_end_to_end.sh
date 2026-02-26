#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_end_to_end.sh [options]

Runs the full Clear Reason evaluation pipeline:
  1) collect — formalize test texts under each prompt version
  2) grade  — Socratic evaluation of formalizations
  3) compare — pairwise blinded comparison
  4) aggregate — leaderboard and ablation impact

Options:
  --config <path>         Config file (default: config.json)
  --output-dir <dir>      Output base dir (default: runs)
  --run-id <id>           Explicit run id (default: auto timestamp)
  --version-filter <csv>  Comma-separated version IDs to include
  --type-filter <csv>     Comma-separated reasoning type IDs to include
  --dry-run               Skip claude calls, use placeholders
  --collect-only          Stop after collect phase
  --grade-only            Run grade on existing formalizations (requires --run-id)
  -h, --help              Show this help
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

CONFIG_PATH="config.json"
OUTPUT_DIR="runs"
RUN_ID=""
VERSION_FILTER=""
TYPE_FILTER=""
DRY_RUN=0
COLLECT_ONLY=0
GRADE_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)       CONFIG_PATH="${2:-}"; shift 2 ;;
    --output-dir)   OUTPUT_DIR="${2:-}"; shift 2 ;;
    --run-id)       RUN_ID="${2:-}"; shift 2 ;;
    --version-filter) VERSION_FILTER="${2:-}"; shift 2 ;;
    --type-filter)  TYPE_FILTER="${2:-}"; shift 2 ;;
    --dry-run)      DRY_RUN=1; shift ;;
    --collect-only) COLLECT_ONLY=1; shift ;;
    --grade-only)   GRADE_ONLY=1; shift ;;
    -h|--help)      usage; exit 0 ;;
    *)              echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Config file not found: ${CONFIG_PATH}" >&2
  exit 1
fi

# Verify claude CLI is available
if ! command -v claude &>/dev/null; then
  echo "claude CLI not found. Install Claude Code first." >&2
  exit 1
fi

if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="run_$(date -u +%Y%m%d_%H%M%S)"
fi

RUN_DIR="${OUTPUT_DIR}/${RUN_ID}"
RESPONSES_FILE="${RUN_DIR}/formalizations.jsonl"

# Build common flags
COMMON_FLAGS=(--config "${CONFIG_PATH}")
if [[ "${DRY_RUN}" -eq 1 ]]; then
  COMMON_FLAGS+=(--dry-run)
fi

# --- Phase 1: Collect ---
if [[ "${GRADE_ONLY}" -eq 0 ]]; then
  echo "==> Phase 1: Collect (run_id=${RUN_ID})"
  collect_cmd=(
    python3 scripts/clear_reason_eval.py collect
    "${COMMON_FLAGS[@]}"
    --output-dir "${OUTPUT_DIR}"
    --run-id "${RUN_ID}"
  )
  if [[ -n "${VERSION_FILTER}" ]]; then
    collect_cmd+=(--version-filter "${VERSION_FILTER}")
  fi
  if [[ -n "${TYPE_FILTER}" ]]; then
    collect_cmd+=(--type-filter "${TYPE_FILTER}")
  fi
  "${collect_cmd[@]}"
fi

if [[ "${COLLECT_ONLY}" -eq 1 ]]; then
  echo ""
  echo "Collect-only complete. Run ID: ${RUN_ID}"
  exit 0
fi

# --- Phase 2: Grade ---
echo ""
echo "==> Phase 2: Grade (Socratic evaluation)"
python3 scripts/clear_reason_eval.py grade \
  "${COMMON_FLAGS[@]}" \
  --responses-file "${RESPONSES_FILE}"

# --- Phase 3: Compare ---
echo ""
echo "==> Phase 3: Compare (pairwise blinded)"
python3 scripts/clear_reason_eval.py compare \
  "${COMMON_FLAGS[@]}" \
  --responses-file "${RESPONSES_FILE}"

# --- Phase 4: Aggregate ---
echo ""
echo "==> Phase 4: Aggregate"
python3 scripts/clear_reason_eval.py aggregate \
  --config "${CONFIG_PATH}" \
  --run-dir "${RUN_DIR}"

echo ""
echo "Pipeline complete."
echo "Run ID: ${RUN_ID}"
echo "Run dir: ${RUN_DIR}"
