#!/usr/bin/env bash
# Run every automated gate of the G3 Research EA repository.
#   1. static pre-compile check of the MQL5 sources
#   2. host unit tests over the pure MQL5 logic
#   3. regression tests for the offline G3 research instruments
# MetaEditor compilation and the MT5 integration plan are NOT covered here.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"

echo "== static check =="
python3 "$root/tools/mql5_static_check.py"

echo
echo "== host unit tests (MQL5 pure logic) =="
bash "$here/run_unit_tests.sh"

echo
echo "== research instrument tests (offline, Python) =="
bash "$here/run_python_tests.sh" 2>&1 | tail -4
