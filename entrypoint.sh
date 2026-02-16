#!/bin/bash

set -eo pipefail

if [ -f "/workspace/bub_hooks.py" ]; then
    cp /workspace/bub_hooks.py /app/.venv/lib/python3.12/site-packages/
    echo "Hooks module bub_hooks.py copied to site-packages."
    export BUB_HOOKS_MODULE="bub_hooks"
fi

if [ -f "/workspace/startup.sh" ]; then
    # Start the idle process in the background
    nohup /app/.venv/bin/bub idle </dev/null >>/proc/1/fd/1 2>>/proc/1/fd/2 &
    exec bash /workspace/startup.sh
else
    exec /app/.venv/bin/bub message
fi
