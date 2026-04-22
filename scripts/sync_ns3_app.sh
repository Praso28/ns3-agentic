#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_FILE="$ROOT_DIR/assets/ns3/ai5g-metrics.cc"
DST_FILE="$ROOT_DIR/tools/ns-3-dev/scratch/ai5g-metrics.cc"

if [[ ! -f "$SRC_FILE" ]]; then
  echo "Missing source file: $SRC_FILE" >&2
  exit 1
fi

if [[ ! -d "$ROOT_DIR/tools/ns-3-dev" ]]; then
  echo "Missing ns-3 workspace at tools/ns-3-dev" >&2
  exit 1
fi

mkdir -p "$(dirname "$DST_FILE")"
cp "$SRC_FILE" "$DST_FILE"
echo "Synced ns-3 app source -> $DST_FILE"
