#!/bin/bash

# © 2026 Massachusetts Institute of Technology
# MIT License

find . -type f -name "*.json" -exec sh -c 'jq "." "$0" > "$0.tmp" && mv "$0.tmp" "$0"' {} \;