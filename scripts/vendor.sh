#!/usr/bin/env bash
# Clone/update OSS reference repositories into third_party/ (study only).
# Idempotent: pulls if present, shallow-clones if not. See third_party/CATALOG.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/third_party"
mkdir -p "$DEST"

# name|url|ref   (ref optional). Kept minimal & OSS-only.
CORE=(
  "kuzu|https://github.com/kuzudb/kuzu|"
  "langgraph|https://github.com/langchain-ai/langgraph|"
  "llm-graph-builder|https://github.com/neo4j-labs/llm-graph-builder|"
  "GLiNER|https://github.com/urchade/GLiNER|"
  "graphrag|https://github.com/microsoft/graphrag|"
  "reagraph|https://github.com/reaviz/reagraph|"
)
REFERENCE=(
  "docling|https://github.com/docling-project/docling|"
  "llama_index|https://github.com/run-llama/llama_index|"
  "splink|https://github.com/moj-analytical-services/splink|"
  "linkml|https://github.com/linkml/linkml|"
  "pymatgen|https://github.com/materialsproject/pymatgen|"
)

clone_one() {
  local name url ref
  IFS='|' read -r name url ref <<< "$1"
  local dir="$DEST/$name"
  if [ -d "$dir/.git" ]; then
    echo ">> update $name"; git -C "$dir" pull --ff-only --depth 1 || true
  else
    echo ">> clone  $name"; git clone --depth 1 ${ref:+--branch "$ref"} "$url" "$dir"
  fi
}

group="${1:-core}"
case "$group" in
  core)      for r in "${CORE[@]}"; do clone_one "$r"; done ;;
  reference) for r in "${REFERENCE[@]}"; do clone_one "$r"; done ;;
  all)       for r in "${CORE[@]}" "${REFERENCE[@]}"; do clone_one "$r"; done ;;
  *) echo "usage: vendor.sh [core|reference|all]"; exit 1 ;;
esac
echo "done."
