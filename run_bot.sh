#!/bin/bash

while true; do
    echo "Starting bot..."
    ./Uptime/bin/python ./main.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Bot exited normally, not restarting."
        break
    else
        echo "Bot crashed with exit code $EXIT_CODE. Restarting in 5 seconds..."
        sleep 5
    fi
done
