#!/bin/sh
# Run the full test suite. No third-party test runner required.
set -e
cd "$(dirname "$0")"
PYTHONPATH=src python3 -m unittest discover -s tests "$@"
