#!/bin/bash
# start_tui.sh – Launch Privya AI Agent with Hermes-style Ink TUI
#
# Usage:
#   bash start_tui.sh          # Start both API server and TUI
#   bash start_tui.sh --api    # Start API server only
#   bash start_tui.sh --tui    # Start TUI only (assumes API is running)

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}✦ Privya AI Agent – Starting...${NC}"

# ── Start API server ──
start_api() {
    echo -e "${YELLOW}  Starting API server on port 8000...${NC}"
    python3 -c "
import uvicorn
import sys
sys.path.insert(0, '.')
from api.server import app
uvicorn.run(app, host='0.0.0.0', port=8000, log_level='warning')
" &
    API_PID=$!
    echo -e "${GREEN}  ✅ API server started (PID: $API_PID)${NC}"

    # Wait for API to be ready
    for i in $(seq 1 10); do
        if curl -s http://127.0.0.1:8000/health > /dev/null 2>&1; then
            echo -e "${GREEN}  ✅ API ready${NC}"
            return 0
        fi
        sleep 1
    done
    echo -e "${RED}  ❌ API failed to start${NC}"
    return 1
}

# ── Start TUI ──
start_tui() {
    echo -e "${GREEN}  Starting Hermes-style Ink TUI...${NC}"
    cd ui-tui
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}  Installing TUI dependencies...${NC}"
        npm install --silent 2>/dev/null
    fi
    npx tsx --tsconfig tsconfig.json src/entry.tsx
    cd ..
}

# ── Main ──
case "${1:-}" in
    --api)
        start_api
        wait $API_PID
        ;;
    --tui)
        start_tui
        ;;
    *)
        start_api
        echo ""
        start_tui
        # Cleanup on exit
        trap "kill $API_PID 2>/dev/null; exit" INT TERM
        wait $API_PID 2>/dev/null
        ;;
esac
