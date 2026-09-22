#!/usr/bin/env bash
# Run the Patch-2 regression tests for the offline G3 research instruments.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m unittest discover -s "$here/python" -p "test_*.py" -v
