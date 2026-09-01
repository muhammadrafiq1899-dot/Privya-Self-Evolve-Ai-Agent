#!/bin/bash
# start.sh – Quick start for the AI Agent

echo "🤖 Starting Self-Evolving AI Agent..."
echo ""

# Check if server.py exists
if [ ! -f server.py ]; then
    echo "❌ server.py not found. Please run from the project root."
    exit 1
fi

# Run the unified server
python server.py
