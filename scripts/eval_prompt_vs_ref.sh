#!/usr/bin/env bash
set -euo pipefail

# One-command custom prompt evaluation against a reference version.
#
# Usage:
#   scripts/eval_prompt_vs_ref.sh prompts/my_prompt.md
#   scripts/eval_prompt_vs_ref.sh prompts/my_prompt.md --ref v10_2025
#   scripts/eval_prompt_vs_ref.sh prompts/my_prompt.md --knowledge prompts/logic_rules.md
#   scripts/eval_prompt_vs_ref.sh prompts/my_prompt.md --id my_custom_id --type-filter argumentative_deductive

usage() {
  cat <<'EOF'
Usage:
  scripts/eval_prompt_vs_ref.sh <prompt_file> [options]

Evaluates a prompt against a reference version (default: v3_2026).

Steps:
  1. Registers the prompt in prompt_versions.json (or updates with --update-existing)
  2. Runs collect + grade + compare + aggregate
  3. Runs stratify_run.py for granular ranking
  4. Prints results

Arguments:
  <prompt_file>               Path to the prompt markdown file

Options:
  --ref <version_id>          Reference version (default: v3_2026)
  --id <version_id>           Version ID for the prompt (default: from filename)
  --name <display_name>       Display name (default: from filename)
  --knowledge <file,...>      Comma-separated knowledge files to concatenate
  --update-existing           Update existing version entry if id already exists
  --corpus <file>             Test corpus file (default: from config.json)
  --type-filter <csv>         Comma-separated reasoning type IDs
  --config <path>             Config file (default: config.json)
  --dry-run                   Skip claude calls, use placeholders
  --run-id <id>               Explicit run ID
  -h, --help                  Show this help
EOF
}

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

# --- Defaults ---
PROMPT_FILE=""
REF_VERSION="v3_2026"
VERSION_ID=""
VERSION_NAME=""
KNOWLEDGE_FILES=""
CORPUS=""
TYPE_FILTER=""
CONFIG_PATH="config.json"
DRY_RUN=0
RUN_ID=""
VERSIONS_FILE="prompt_versions.json"
UPDATE_EXISTING=0

# --- Parse args ---
if [[ $# -lt 1 ]]; then
  usage
  exit 2
fi

case "$1" in
  -h|--help)
    usage
    exit 0
    ;;
esac

PROMPT_FILE="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref)            REF_VERSION="${2:-}"; shift 2 ;;
    --id)             VERSION_ID="${2:-}"; shift 2 ;;
    --name)           VERSION_NAME="${2:-}"; shift 2 ;;
    --knowledge)      KNOWLEDGE_FILES="${2:-}"; shift 2 ;;
    --update-existing) UPDATE_EXISTING=1; shift ;;
    --corpus)         CORPUS="${2:-}"; shift 2 ;;
    --type-filter)    TYPE_FILTER="${2:-}"; shift 2 ;;
    --config)         CONFIG_PATH="${2:-}"; shift 2 ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --run-id)         RUN_ID="${2:-}"; shift 2 ;;
    -h|--help)        usage; exit 0 ;;
    *)                echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

# --- Validate ---
if [[ ! -f "${PROMPT_FILE}" ]]; then
  echo "Error: Prompt file not found: ${PROMPT_FILE}" >&2
  exit 1
fi

if [[ ! -f "${CONFIG_PATH}" ]]; then
  echo "Error: Config file not found: ${CONFIG_PATH}" >&2
  exit 1
fi

if [[ ! -f "${VERSIONS_FILE}" ]]; then
  echo "Error: Versions file not found: ${VERSIONS_FILE}" >&2
  exit 1
fi

if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found." >&2
  exit 1
fi

if [[ "${DRY_RUN}" -eq 0 ]] && ! command -v claude &>/dev/null; then
  echo "Error: claude CLI not found. Install Claude Code first (or use --dry-run)." >&2
  exit 1
fi

if [[ -n "${KNOWLEDGE_FILES}" ]]; then
  python3 - "${KNOWLEDGE_FILES}" <<'PY'
import pathlib
import sys

for raw in sys.argv[1].split(","):
    path = raw.strip()
    if not path:
        continue
    if not pathlib.Path(path).is_file():
        print(f"Error: Knowledge file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
PY
fi

# --- Derive defaults from filename ---
BASENAME="$(basename "${PROMPT_FILE}" .md)"

if [[ -z "${VERSION_ID}" ]]; then
  VERSION_ID="$(echo "${BASENAME}" | tr '[:upper:]' '[:lower:]' | tr ' -' '__' | tr -cd 'a-z0-9_')"
fi
if [[ -z "${VERSION_ID}" ]]; then
  echo "Error: Could not derive a non-empty version id. Pass --id explicitly." >&2
  exit 1
fi

if [[ -z "${VERSION_NAME}" ]]; then
  VERSION_NAME="${BASENAME}"
fi

if [[ -z "${RUN_ID}" ]]; then
  RUN_ID="eval_${VERSION_ID}_vs_${REF_VERSION}_$(date -u +%Y%m%d_%H%M%S)"
fi

RUN_DIR="runs/${RUN_ID}"
RESPONSES_FILE="${RUN_DIR}/formalizations.jsonl"

if [[ -e "${RUN_DIR}" ]]; then
  echo "Error: Run directory already exists: ${RUN_DIR}" >&2
  echo "Pass --run-id to pick a different run id." >&2
  exit 1
fi

# --- Verify reference version exists ---
if ! python3 - "${VERSIONS_FILE}" "${REF_VERSION}" <<'PY'
import json
import pathlib
import sys

versions_path = pathlib.Path(sys.argv[1])
ref_version = sys.argv[2]

with versions_path.open("r", encoding="utf-8") as handle:
    payload = json.load(handle)

versions = payload.get("versions", [])
ids = [str(v.get("id", "")) for v in versions if isinstance(v, dict)]
if ref_version in ids:
    raise SystemExit(0)
raise SystemExit(1)
PY
then
  echo "Error: Reference version '${REF_VERSION}' not found in ${VERSIONS_FILE}" >&2
  echo "Available versions:" >&2
  python3 - "${VERSIONS_FILE}" <<'PY' >&2
import json
import pathlib
import sys

versions_path = pathlib.Path(sys.argv[1])
with versions_path.open("r", encoding="utf-8") as handle:
    payload = json.load(handle)
for version in payload.get("versions", []):
    if not isinstance(version, dict):
        continue
    vid = str(version.get("id", ""))
    vtype = str(version.get("type", "version"))
    print(f"  {vid:<30} ({vtype})")
PY
  exit 1
fi

echo "=== Custom Prompt Evaluation ==="
echo "  Prompt:     ${PROMPT_FILE}"
echo "  Version ID: ${VERSION_ID}"
echo "  Reference:  ${REF_VERSION}"
echo "  Run ID:     ${RUN_ID}"
echo ""

# --- Step 1: Register/update prompt version ---
if ! python3 - "${VERSIONS_FILE}" "${VERSION_ID}" "${VERSION_NAME}" "${PROMPT_FILE}" "${KNOWLEDGE_FILES}" "${UPDATE_EXISTING}" <<'PY'
import json
import pathlib
import sys

versions_path = pathlib.Path(sys.argv[1])
version_id = sys.argv[2]
version_name = sys.argv[3]
prompt_file = sys.argv[4]
knowledge_csv = sys.argv[5]
update_existing = sys.argv[6] == "1"

knowledge_files = [item.strip() for item in knowledge_csv.split(",") if item.strip()]

with versions_path.open("r", encoding="utf-8") as handle:
    payload = json.load(handle)

versions = payload.get("versions")
if not isinstance(versions, list):
    print("Error: prompt_versions.json must contain a 'versions' list.", file=sys.stderr)
    raise SystemExit(2)

existing = None
for version in versions:
    if isinstance(version, dict) and str(version.get("id", "")) == version_id:
        existing = version
        break

if existing is None:
    versions.append(
        {
            "id": version_id,
            "name": version_name,
            "type": "version",
            "system_prompt_file": prompt_file,
            "knowledge_files": knowledge_files,
        }
    )
    with versions_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Registered '{version_id}' in {versions_path}.")
    raise SystemExit(0)

existing_prompt = str(existing.get("system_prompt_file") or "")
existing_name = str(existing.get("name") or "")
existing_knowledge = [str(item) for item in (existing.get("knowledge_files") or [])]

if (
    existing_prompt == prompt_file
    and existing_name == version_name
    and existing_knowledge == knowledge_files
):
    print(f"Version '{version_id}' already registered with matching configuration.")
    raise SystemExit(0)

if not update_existing:
    print(f"Error: Version '{version_id}' already exists with different configuration.", file=sys.stderr)
    print(f"  Existing prompt:     {existing_prompt}", file=sys.stderr)
    print(f"  Requested prompt:    {prompt_file}", file=sys.stderr)
    print(f"  Existing name:       {existing_name}", file=sys.stderr)
    print(f"  Requested name:      {version_name}", file=sys.stderr)
    print(f"  Existing knowledge:  {existing_knowledge}", file=sys.stderr)
    print(f"  Requested knowledge: {knowledge_files}", file=sys.stderr)
    print("Re-run with --update-existing to modify this entry, or pick a new --id.", file=sys.stderr)
    raise SystemExit(3)

existing["name"] = version_name
existing["system_prompt_file"] = prompt_file
existing["knowledge_files"] = knowledge_files
if not existing.get("type"):
    existing["type"] = "version"

with versions_path.open("w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
print(f"Updated existing version '{version_id}' in {versions_path}.")
PY
then
  exit 1
fi

# --- Step 2: Collect ---
echo ""
echo "==> Phase 1/5: Collect"
collect_cmd=(
  python3 scripts/clear_reason_eval.py collect
  --config "${CONFIG_PATH}"
  --output-dir runs
  --run-id "${RUN_ID}"
  --version-filter "${REF_VERSION},${VERSION_ID}"
)
if [[ -n "${TYPE_FILTER}" ]]; then
  collect_cmd+=(--type-filter "${TYPE_FILTER}")
fi
if [[ -n "${CORPUS}" ]]; then
  collect_cmd+=(--corpus "${CORPUS}")
fi
if [[ "${DRY_RUN}" -eq 1 ]]; then
  collect_cmd+=(--dry-run)
fi
"${collect_cmd[@]}"

# --- Step 3: Grade ---
echo ""
echo "==> Phase 2/5: Grade"
grade_cmd=(
  python3 scripts/clear_reason_eval.py grade
  --config "${CONFIG_PATH}"
  --responses-file "${RESPONSES_FILE}"
)
if [[ "${DRY_RUN}" -eq 1 ]]; then
  grade_cmd+=(--dry-run)
fi
"${grade_cmd[@]}"

# --- Step 4: Compare ---
echo ""
echo "==> Phase 3/5: Compare (${REF_VERSION} vs ${VERSION_ID})"
compare_cmd=(
  python3 scripts/clear_reason_eval.py compare
  --config "${CONFIG_PATH}"
  --responses-file "${RESPONSES_FILE}"
  --pair "${REF_VERSION},${VERSION_ID}"
)
if [[ "${DRY_RUN}" -eq 1 ]]; then
  compare_cmd+=(--dry-run)
fi
"${compare_cmd[@]}"

# --- Step 5: Aggregate ---
echo ""
echo "==> Phase 4/5: Aggregate"
python3 scripts/clear_reason_eval.py aggregate \
  --config "${CONFIG_PATH}" \
  --run-dir "${RUN_DIR}"

# --- Step 6: Stratify ---
echo ""
echo "==> Phase 5/5: Stratify"
python3 scripts/stratify_run.py \
  --run-dir "${RUN_DIR}" \
  --anchor "${REF_VERSION}"

echo ""
echo "=== Evaluation complete ==="
echo "  Run dir:    ${RUN_DIR}"
echo "  Aggregate:  ${RUN_DIR}/aggregate/aggregate_summary.json"
echo "  Stratified: ${RUN_DIR}/stratified/stratified_summary.json"
