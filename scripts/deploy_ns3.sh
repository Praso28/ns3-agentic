#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NS3_DIR="${REPO_ROOT}/tools/ns-3-dev"

sudo apt-get update
sudo apt-get install -y \
  git \
  g++ \
  python3 \
  python3-dev \
  cmake \
  ninja-build \
  pkg-config \
  sqlite3 \
  libsqlite3-dev

mkdir -p "${REPO_ROOT}/tools"
if [[ ! -d "${NS3_DIR}/.git" ]]; then
  git clone --depth 1 https://gitlab.com/nsnam/ns-3-dev.git "${NS3_DIR}"
fi

cd "${NS3_DIR}"
./ns3 configure --disable-examples --disable-tests
./ns3 build

./ns3 --help >/dev/null
./ns3 run "scratch-simulator" >/dev/null

echo "ns-3 deployed successfully at ${NS3_DIR}"
