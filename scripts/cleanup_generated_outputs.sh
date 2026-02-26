#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

for dir in runs console; do
  if [[ -d "${dir}" ]]; then
    rm -rf "${dir}"
    echo "Removed ${dir}/"
  fi
done

# Clean generated ablation files
if [[ -d "prompts/ablations" ]]; then
  rm -rf "prompts/ablations"
  echo "Removed prompts/ablations/"
fi

echo "Generated artifacts cleaned."
