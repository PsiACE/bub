#!/bin/bash

set -eo pipefail

if [ -f "/workspace/bub-reqs.txt" ]; then
    echo "Installing additional requirements from /workspace/bub-reqs.txt"
    uv pip install -r /workspace/bub-reqs.txt -p /app/.venv/bin/python
fi

if [ -f "/workspace/startup.sh" ]; then
    # Start the idle process in the background
    nohup /app/.venv/bin/bub idle </dev/null >>/proc/1/fd/1 2>>/proc/1/fd/2 &
    exec bash /workspace/startup.sh
else
    exec /app/.venv/bin/bub message
fi
