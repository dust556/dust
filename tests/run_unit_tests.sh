#!/usr/bin/env bash
# Build and run the G3 host unit tests (pure specification logic).
# Requires only a C++17 compiler; MetaTrader is not needed.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="${TMPDIR:-/tmp}/g3_host_tests"
g++ -std=c++17 -Wall -Wextra -Werror -O1 -o "$out" "$here/host/test_main.cpp"
"$out"
