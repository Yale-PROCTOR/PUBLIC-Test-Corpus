#!/bin/bash

# © 2026 Massachusetts Institute of Technology
# MIT License

# Get the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Add the directory containing 'runtests' to PYTHONPATH
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH}"

# Run the module
exec python3 -m runtests.rust "$@"