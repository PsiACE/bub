#!/bin/bash

set -eo pipefail

if [ -f "/workspace/startup.sh" ]; then
    # Start the idle process in the background
    nohup /app/.venv/bin/bub idle </dev/null >>/proc/1/fd/1 2>>/proc/1/fd/2 &
    exec bash /workspace/startup.sh
else
    exec /app/.venv/bin/bub telegram
fi
