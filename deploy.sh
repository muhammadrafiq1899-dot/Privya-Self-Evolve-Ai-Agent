#!/bin/bash
# deploy.sh – Quick deployment script for the AI Agent

set -e

echo "🤖 AI Agent Deployment"
echo "======================"
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✅ Python: $python_version"

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found"
    echo "   Copying .env.example to .env..."
    cp .env.example .env 2>/dev/null || echo "   Please create .env manually"
fi

# Install dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt -q

# Check for optional dependencies
echo ""
echo "🔍 Checking optional features..."

python3 -c "import numpy; print('✅ numpy (semantic search)')" 2>/dev/null || echo "⚠️  numpy not installed (semantic search will use fallback)"
python3 -c "import sentence_transformers; print('✅ sentence-transformers (embeddings)')" 2>/dev/null || echo "ℹ️  sentence-transformers not installed (using TF-IDF fallback)"
python3 -c "import edge_tts; print('✅ edge-tts (voice)')" 2>/dev/null || echo "ℹ️  edge-tts not installed (voice will use termux-tts)"

# Check Termux:API
if command -v termux-battery-status &> /dev/null; then
    echo "✅ Termux:API (hardware access)"
else
    echo "ℹ️  Termux:API not available (hardware features disabled)"
fi

# Verify LLM provider
echo ""
echo "🔑 Checking LLM provider..."
python3 -c "
from llm import get_client
try:
    _, provider, model = get_client()
    print(f'✅ LLM: {provider}/{model}')
except Exception as e:
    print(f'❌ {e}')
    print('   Add at least one API key to .env')
    exit(1)
"

# Count tools
echo ""
echo "🔧 Tool count:"
python3 -c "
from tools import get_tools
from termux_hardware import HARDWARE_TOOL_SCHEMAS
from vision import VISION_TOOL_SCHEMAS
from voice import VOICE_TOOL_SCHEMAS
from reflection import REFLECTION_TOOL_SCHEMAS
from subagents import SUBAGENT_TOOL_SCHEMAS
from events import EVENT_TOOL_SCHEMAS
from git_integration import GIT_TOOL_SCHEMAS
from semantic import SEMANTIC_TOOL_SCHEMAS

total = (len(get_tools()) + len(HARDWARE_TOOL_SCHEMAS) + len(VISION_TOOL_SCHEMAS) +
         len(VOICE_TOOL_SCHEMAS) + len(REFLECTION_TOOL_SCHEMAS) + len(SUBAGENT_TOOL_SCHEMAS) +
         len(EVENT_TOOL_SCHEMAS) + len(GIT_TOOL_SCHEMAS) + len(SEMANTIC_TOOL_SCHEMAS))
print(f'✅ Total: {total} tools')
" 2>/dev/null || echo "⚠️  Could not count tools"

echo ""
echo "======================"
echo "🚀 Ready to launch!"
echo ""
echo "Commands:"
echo "  python server.py          # Run unified system (web + all services)"
echo "  python agent.py           # Run TUI only"
echo "  python telegram_bot.py    # Run Telegram bot only"
echo "  python consolidator.py    # Run memory consolidation"
echo ""
echo "Web Dashboard: http://localhost:8000"
echo "API: http://localhost:8000/api"
echo "======================"
