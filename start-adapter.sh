#!/bin/sh
# Start the sgpt -> OpenCode adapter (localhost:8642)
# Prereqs: opencode installed (~/.opencode/bin/opencode), python3
cd "$(dirname "$0")"
exec python3 adapter.py
