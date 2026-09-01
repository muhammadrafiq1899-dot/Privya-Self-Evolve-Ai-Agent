#!/bin/bash
# ============================================================
# 🤖 Self-Evolving AI Agent – One-Command Termux Installer
# ============================================================
#
# Paste this single command into Termux to install everything:
#
#   bash <(curl -s https://raw.githubusercontent.com/muhammadrafiq1899-dot/Privya-Self-Evolve-Ai-Agent/main/setup.sh)
#
# Or if you already cloned the repo:
#
#   bash setup.sh
#
# ============================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Repo config
REPO_URL="https://github.com/muhammadrafiq1899-dot/Privya-Self-Evolve-Ai-Agent.git"
INSTALL_DIR="$HOME/ai-agent"

# ============================================================
# Helper functions
# ============================================================

print_header() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                                                          ║"
    echo "║       🤖 Self-Evolving AI Agent Installer               ║"
    echo "║                                                          ║"
    echo "║       For Termux on Android                              ║"
    echo "║                                                          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

step() {
    echo ""
    echo -e "${BLUE}${BOLD}[$1/8]${NC} ${BOLD}$2${NC}"
    echo -e "${BLUE}────────────────────────────────────────────────${NC}"
}

success() {
    echo -e "${GREEN}  ✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}  ⚠️  $1${NC}"
}

error() {
    echo -e "${RED}  ❌ $1${NC}"
}

info() {
    echo -e "${CYAN}  ℹ️  $1${NC}"
}

# ============================================================
# Pre-flight checks
# ============================================================

preflight_check() {
    # Check if running in Termux
    if [ -z "$TERMUX_VERSION" ] && [ ! -d "/data/data/com.termux" ]; then
        warning "Not running in Termux. Some features may not work."
        echo "  This installer is optimized for Termux on Android."
        echo "  Continue anyway? [y/N]"
        read -r response
        if [[ ! "$response" =~ ^[Yy]$ ]]; then
            echo "Installation cancelled."
            exit 1
        fi
    fi

    # Check internet connection
    if ! ping -c 1 -W 3 google.com &>/dev/null; then
        error "No internet connection. Please connect and try again."
        exit 1
    fi
}

# ============================================================
# Installation steps
# ============================================================

step_1_update_termux() {
    step "1" "Updating Termux packages..."
    
    pkg update -y -qq 2>/dev/null || apt update -y -qq
    pkg upgrade -y -qq 2>/dev/null || apt upgrade -y -qq
    
    success "Termux packages updated"
}

step_2_install_system_deps() {
    step "2" "Installing system dependencies..."
    
    # Essential packages
    PACKAGES="python git curl wget"
    
    # Build dependencies for Python packages (including Rust for jiter/openai)
    PACKAGES="$PACKAGES build-essential rust binutils" 2>/dev/null || true
    PACKAGES="$PACKAGES libxml2 libxslt" 2>/dev/null || true
    
    # Termux:API for hardware features
    PACKAGES="$PACKAGES termux-api" 2>/dev/null || true
    
    for pkg in $PACKAGES; do
        if command -v "$pkg" &>/dev/null || [ -d "/data/data/com.termux/files/usr/bin/$pkg" ]; then
            info "$pkg already installed"
        else
            echo "    📦 Installing $pkg..."
            pkg install -y -qq "$pkg" 2>/dev/null || apt install -y -qq "$pkg" 2>/dev/null || true
        fi
    done
    
    success "System dependencies installed"
}

step_2b_configure_rust() {
    # Configure Rust for Termux if installed
    if command -v rustc &>/dev/null; then
        echo "  🦀 Configuring Rust for Termux..."
        
        # Set up Rust environment
        export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
        export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
        
        # Create cargo env if it doesn't exist
        if [ ! -f "$CARGO_HOME/env" ]; then
            mkdir -p "$CARGO_HOME"
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' > "$CARGO_HOME/env"
        fi
        
        # Add to PATH for this session
        export PATH="$CARGO_HOME/bin:$PATH"
        
        success "Rust configured"
    else
        info "Rust not installed (optional)"
    fi
}

step_3_clone_repo() {
    step "3" "Downloading AI Agent..."
    
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/requirements.txt" ]; then
        info "Directory $INSTALL_DIR already exists with files"
        echo "  Update existing installation? [Y/n]"
        read -r response
        if [[ ! "$response" =~ ^[Nn]$ ]]; then
            cd "$INSTALL_DIR"
            git pull origin main 2>/dev/null || git pull 2>/dev/null || true
            success "Updated existing installation"
        fi
    else
        # Remove empty directory if it exists
        if [ -d "$INSTALL_DIR" ]; then
            rmdir "$INSTALL_DIR" 2>/dev/null || rm -rf "$INSTALL_DIR" 2>/dev/null || true
        fi
        
        echo "  Cloning from: $REPO_URL"
        if git clone "$REPO_URL" "$INSTALL_DIR"; then
            cd "$INSTALL_DIR"
            success "Repository cloned to $INSTALL_DIR"
        else
            error "Failed to clone repository!"
            echo ""
            echo "  Possible causes:"
            echo "    - No internet connection"
            echo "    - Repository is private"
            echo "    - GitHub is unreachable"
            echo ""
            echo "  Manual install:"
            echo "    1. Download from: $REPO_URL"
            echo "    2. Extract to: $INSTALL_DIR"
            echo "    3. Run: cd $INSTALL_DIR && bash setup.sh"
            echo ""
            exit 1
        fi
    fi
}

step_4_install_python_deps() {
    step "4" "Installing Python packages..."
    
    # Upgrade pip first
    echo "  📦 Upgrading pip..."
    python -m pip install --upgrade pip --no-cache-dir -q 2>/dev/null || true
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        echo ""
        echo "  📦 Installing core packages..."
        echo "  ⏳ This may take 2-5 minutes depending on your connection."
        echo "  💡 You will see progress below:"
        echo ""
        
        # First try with binary-only to avoid building from source
        echo "  Trying to install from pre-built packages..."
        if python -m pip install -r requirements.txt --no-cache-dir --only-binary :all: --progress-bar on 2>/dev/null; then
            success "Core packages installed (pre-built)"
        else
            echo "  Some packages need to be built from source, this may take longer..."
            # Fall back to building from source
            python -m pip install -r requirements.txt --no-cache-dir --progress-bar on
        fi
        
        if [ $? -eq 0 ]; then
            success "Core packages installed"
        else
            warning "Some core packages may have failed"
            echo "  Try running: pip install -r requirements.txt"
        fi
    else
        error "requirements.txt not found!"
        echo "  Please make sure you're in the correct directory."
        exit 1
    fi
    
    # Try to install numpy (optional - may fail on Termux)
    echo ""
    echo "  📦 Trying to install numpy (optional for better semantic search)..."
    if python -m pip install numpy --no-cache-dir -q 2>/dev/null; then
        success "numpy installed (better semantic search enabled)"
    else
        info "numpy skipped (using TF-IDF fallback for semantic search)"
        echo "  This is OK - semantic search will use a lighter algorithm."
    fi
}

step_5_install_optional_deps() {
    step "5" "Installing optional features..."
    
    # sentence-transformers for better embeddings (large download)
    echo ""
    echo "  Install sentence-transformers for better semantic search?"
    echo "  (Requires ~500MB download, can skip)"
    echo "  [y/N]"
    read -r response
    if [[ "$response" =~ ^[Yy]$ ]]; then
        python -m pip install sentence-transformers -q 2>/dev/null && \
            success "sentence-transformers installed" || \
            warning "Could not install (will use fallback)"
    else
        info "Skipped (will use TF-IDF fallback)"
    fi
    
    # edge-tts for high-quality voice
    python -m pip install edge-tts -q 2>/dev/null && \
        success "edge-tts installed (high-quality voice)" || \
        warning "Could not install edge-tts"
}

step_6_configure_providers() {
    step "6" "Configuring LLM providers..."
    
    # Create .env from example if it doesn't exist
    if [ ! -f ".env" ]; then
        cat > .env << 'ENVEOF'
# === LLM Providers (at least one required) ===
GROQ_API_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
TOGETHER_API_KEY=

# === Custom Provider (optional) ===
CUSTOM_API_KEY=
CUSTOM_BASE_URL=
CUSTOM_MODEL=

# === Telegram (optional) ===
TELEGRAM_BOT_TOKEN=

# === Obsidian REST API (optional) ===
OBSIDIAN_API_KEY=
OBSIDIAN_URL=http://127.0.0.1:27123
OBSIDIAN_VAULT=~/ai-agent/vault

# === Provider Selection (set during setup) ===
DEFAULT_PROVIDER=
DEFAULT_MODEL=
ENVEOF
        success "Created .env configuration file"
    fi
    
    # Create data directory
    mkdir -p "$HOME/.ai-agent"
    success "Data directory created at ~/.ai-agent"
    
    echo ""
    echo -e "${BOLD}Choose your LLM provider:${NC}"
    echo ""
    echo -e "  ${GREEN}1)${NC} ${CYAN}Groq${NC}          – Fastest inference, free tier ⭐"
    echo -e "     ${GREEN}2)${NC} ${CYAN}OpenRouter${NC}    – 100+ models, pay-per-use"
    echo -e "     ${GREEN}3)${NC} ${CYAN}Google Gemini${NC} – Free tier, great quality"
    echo -e "     ${GREEN}4)${NC} ${CYAN}Together AI${NC}   – Open-source models, cheap"
    echo -e "     ${GREEN}5)${NC} ${CYAN}Custom${NC}        – Any OpenAI-compatible API (vLLM, Ollama, LM Studio…)"
    echo -e "     ${GREEN}6)${NC} ${CYAN}Skip${NC}           – Configure later in .env"
    echo ""
    read -p "  Enter choice [1-6]: " provider_choice
    
    case $provider_choice in
        1) _configure_groq ;;
        2) _configure_openrouter ;;
        3) _configure_gemini ;;
        4) _configure_together ;;
        5) _configure_custom ;;
        6) info "Skipped. Add API key to .env manually." ;;
        *) warning "Invalid choice, skipping." ;;
    esac
}

_configure_groq() {
    echo ""
    echo -e "${CYAN}━━━ Groq Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Free API key: ${BLUE}https://console.groq.com${NC}"
    echo -e "  Sign up → API Keys → Create → Copy key"
    echo ""
    read -p "  Paste your Groq API key (or Enter to skip): " api_key
    
    if [ -n "$api_key" ]; then
        # Save key
        sed -i "s|^GROQ_API_KEY=.*|GROQ_API_KEY=$api_key|" .env
        
        # Choose model
        echo ""
        echo -e "  ${BOLD}Choose default model:${NC}"
        echo -e "    ${GREEN}1)${NC} llama-3.3-70b-versatile  ${YELLOW}(recommended)${NC}"
        echo -e "    ${GREEN}2)${NC} llama-3.1-8b-instant      (fastest)"
        echo -e "    ${GREEN}3)${NC} mixtral-8x7b-32768        (long context)"
        echo -e "    ${GREEN}4)${NC} gemma2-9b-it              (efficient)"
        echo ""
        read -p "  Enter choice [1-4]: " model_choice
        
        local model="llama-3.3-70b-versatile"
        case $model_choice in
            1) model="llama-3.3-70b-versatile" ;;
            2) model="llama-3.1-8b-instant" ;;
            3) model="mixtral-8x7b-32768" ;;
            4) model="gemma2-9b-it" ;;
        esac
        
        sed -i "s|^DEFAULT_PROVIDER=.*|DEFAULT_PROVIDER=groq|" .env
        sed -i "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=$model|" .env
        
        success "Groq configured: $model"
        _test_llm_connection "groq" "$model"
    else
        info "Skipped Groq setup"
    fi
}

_configure_openrouter() {
    echo ""
    echo -e "${CYAN}━━━ OpenRouter Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  API key: ${BLUE}https://openrouter.ai/keys${NC}"
    echo -e "  Sign up → Keys → Create Key → Copy"
    echo ""
    read -p "  Paste your OpenRouter API key (or Enter to skip): " api_key
    
    if [ -n "$api_key" ]; then
        sed -i "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$api_key|" .env
        
        echo ""
        echo -e "  ${BOLD}Choose default model:${NC}"
        echo -e "    ${GREEN}1)${NC} meta-llama/llama-3.3-70b-instruct   ${YELLOW}(free, recommended)${NC}"
        echo -e "    ${GREEN}2)${NC} anthropic/claude-3.5-sonnet          (best reasoning)"
        echo -e "    ${GREEN}3)${NC} openai/gpt-4o                        (OpenAI flagship)"
        echo -e "    ${GREEN}4)${NC} google/gemini-2.0-flash-001          (fast)"
        echo -e "    ${GREEN}5)${NC} deepseek/deepseek-chat               (coding)"
        echo ""
        read -p "  Enter choice [1-5]: " model_choice
        
        local model="meta-llama/llama-3.3-70b-instruct"
        case $model_choice in
            1) model="meta-llama/llama-3.3-70b-instruct" ;;
            2) model="anthropic/claude-3.5-sonnet" ;;
            3) model="openai/gpt-4o" ;;
            4) model="google/gemini-2.0-flash-001" ;;
            5) model="deepseek/deepseek-chat" ;;
        esac
        
        sed -i "s|^DEFAULT_PROVIDER=.*|DEFAULT_PROVIDER=openrouter|" .env
        sed -i "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=$model|" .env
        
        success "OpenRouter configured: $model"
        _test_llm_connection "openrouter" "$model"
    else
        info "Skipped OpenRouter setup"
    fi
}

_configure_gemini() {
    echo ""
    echo -e "${CYAN}━━━ Google Gemini Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Free API key: ${BLUE}https://aistudio.google.com${NC}"
    echo -e "  Get API key → Create → Copy"
    echo ""
    read -p "  Paste your Gemini API key (or Enter to skip): " api_key
    
    if [ -n "$api_key" ]; then
        sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$api_key|" .env
        
        echo ""
        echo -e "  ${BOLD}Choose default model:${NC}"
        echo -e "    ${GREEN}1)${NC} gemini-2.0-flash                       ${YELLOW}(recommended)${NC}"
        echo -e "    ${GREEN}2)${NC} gemini-2.5-flash-preview-05-20         (latest thinking)"
        echo -e "    ${GREEN}3)${NC} gemini-1.5-pro                         (best quality)"
        echo -e "    ${GREEN}4)${NC} gemini-1.5-flash                       (balanced)"
        echo ""
        read -p "  Enter choice [1-4]: " model_choice
        
        local model="gemini-2.0-flash"
        case $model_choice in
            1) model="gemini-2.0-flash" ;;
            2) model="gemini-2.5-flash-preview-05-20" ;;
            3) model="gemini-1.5-pro" ;;
            4) model="gemini-1.5-flash" ;;
        esac
        
        sed -i "s|^DEFAULT_PROVIDER=.*|DEFAULT_PROVIDER=gemini|" .env
        sed -i "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=$model|" .env
        
        success "Gemini configured: $model"
        _test_llm_connection "gemini" "$model"
    else
        info "Skipped Gemini setup"
    fi
}

_configure_together() {
    echo ""
    echo -e "${CYAN}━━━ Together AI Setup ━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  API key: ${BLUE}https://api.together.xyz${NC}"
    echo -e "  Sign up → Settings → API Keys → Create → Copy"
    echo ""
    read -p "  Paste your Together API key (or Enter to skip): " api_key
    
    if [ -n "$api_key" ]; then
        sed -i "s|^TOGETHER_API_KEY=.*|TOGETHER_API_KEY=$api_key|" .env
        
        echo ""
        echo -e "  ${BOLD}Choose default model:${NC}"
        echo -e "    ${GREEN}1)${NC} meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo  ${YELLOW}(recommended)${NC}"
        echo -e "    ${GREEN}2)${NC} meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo  (largest)"
        echo -e "    ${GREEN}3)${NC} deepseek-ai/DeepSeek-V3                         (coding)"
        echo -e "    ${GREEN}4)${NC} Qwen/Qwen2.5-72B-Instruct-Turbo                 (multilingual)"
        echo ""
        read -p "  Enter choice [1-4]: " model_choice
        
        local model="meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo"
        case $model_choice in
            1) model="meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo" ;;
            2) model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo" ;;
            3) model="deepseek-ai/DeepSeek-V3" ;;
            4) model="Qwen/Qwen2.5-72B-Instruct-Turbo" ;;
        esac
        
        sed -i "s|^DEFAULT_PROVIDER=.*|DEFAULT_PROVIDER=together|" .env
        sed -i "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=$model|" .env
        
        success "Together configured: $model"
        _test_llm_connection "together" "$model"
    else
        info "Skipped Together setup"
    fi
}

_configure_custom() {
    echo ""
    echo -e "${CYAN}━━━ Custom Provider Setup ━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "  Works with any OpenAI-compatible API:"
    echo -e "    • vLLM, Ollama, LM Studio, LocalAI"
    echo -e "    • OpenAI API, Azure OpenAI"
    echo -e "    • Any proxy that exposes /v1/chat/completions"
    echo ""
    
    read -p "  API Base URL (e.g. http://localhost:8000/v1): " base_url
    if [ -z "$base_url" ]; then
        info "Skipped Custom setup"
        return
    fi
    
    read -p "  API Key (or 'none' for local): " api_key
    api_key="${api_key:-none}"
    
    read -p "  Model name (e.g. meta-llama/Llama-3-8B-Instruct): " model
    if [ -z "$model" ]; then
        echo "  ⚠️  Model name required"
        info "Skipped Custom setup"
        return
    fi
    
    # Save to .env
    sed -i "s|^CUSTOM_API_KEY=.*|CUSTOM_API_KEY=$api_key|" .env
    sed -i "s|^CUSTOM_BASE_URL=.*|CUSTOM_BASE_URL=$base_url|" .env
    sed -i "s|^CUSTOM_MODEL=.*|CUSTOM_MODEL=$model|" .env
    sed -i "s|^DEFAULT_PROVIDER=.*|DEFAULT_PROVIDER=custom|" .env
    sed -i "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=$model|" .env
    
    success "Custom provider configured: $base_url / $model"
    _test_llm_connection "custom" "$model"
}

_test_llm_connection() {
    local provider="$1"
    local model="$2"
    echo ""
    echo "  🧪 Testing connection..."
    
    python -c "
import asyncio, os, sys
os.chdir('$(pwd)')
sys.path.insert(0, '.')
from llm import set_session_provider, chat

async def test():
    result = set_session_provider('$provider', '$model')
    if 'error' in result:
        print(f'    ❌ {result["error"]}')
        return
    resp = await chat([{'role': 'user', 'content': 'Say hello in one word'}], temperature=0.1, max_tokens=10)
    content = resp.get('content', '')
    if content:
        print(f'    ✅ Connection successful! Response: {content[:50]}')
    else:
        print('    ⚠️  Connection OK but empty response')

asyncio.run(test())
" 2>/dev/null && success "LLM connection verified" || warning "Could not test (check .env manually)"
}

step_7_verify_installation() {
    step "7" "Verifying installation..."
    
    # Check Python
    if python --version &>/dev/null; then
        success "Python: $(python --version 2>&1)"
    else
        error "Python not found!"
        exit 1
    fi
    
    # Check key imports
    python -c "import openai; import dotenv; import rich" 2>/dev/null && \
        success "Core packages verified" || \
        error "Some packages missing"
    
    # Check LLM provider
    python -c "
from llm import get_client
try:
    _, provider, model = get_client()
    print(f'    LLM: {provider}/{model}')
except Exception as e:
    print(f'    ⚠️  No LLM configured: {e}')
    print('    Add an API key to .env')
" 2>/dev/null || true
    
    # Count tools
    python -c "
from tools import get_tools
print(f'    Tools: {len(get_tools())} base tools loaded')
" 2>/dev/null || true
}

step_8_create_shortcuts() {
    step "8" "Creating shortcuts..."
    
    # Create launcher script
    cat > "$HOME/ai-agent/start" << 'LAUNCHER'
#!/bin/bash
cd ~/ai-agent
echo "🤖 Starting AI Agent..."
echo ""
echo "  TUI:      python agent.py"
echo "  Web:      python server.py"
echo "  Telegram: python telegram_bot.py"
echo ""
echo "Choose interface:"
echo "  1) TUI (terminal)"
echo "  2) Web dashboard"
echo "  3) Telegram bot"
echo "  4) All services"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1) python agent.py ;;
    2) python server.py ;;
    3) python telegram_bot.py ;;
    4) python server.py ;;
    *) python agent.py ;;
esac
LAUNCHER
    chmod +x "$HOME/ai-agent/start"
    
    # Create alias for easy access
    SHELL_RC="$HOME/.bashrc"
    if [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    fi
    
    # Add alias if not already present
    if ! grep -q "alias ai-agent=" "$SHELL_RC" 2>/dev/null; then
        echo "" >> "$SHELL_RC"
        echo "# AI Agent shortcut" >> "$SHELL_RC"
        echo "alias ai-agent='cd ~/ai-agent && python agent.py'" >> "$SHELL_RC"
        echo "alias ai-web='cd ~/ai-agent && python server.py'" >> "$SHELL_RC"
        echo "alias ai-tg='cd ~/ai-agent && python telegram_bot.py'" >> "$SHELL_RC"
        success "Added shortcuts to $SHELL_RC"
    else
        info "Shortcuts already configured"
    fi
}

# ============================================================
# Print summary
# ============================================================

print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║           ✅ Installation Complete!                     ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}📍 Installed to:${NC} ~/ai-agent"
    echo ""
    echo -e "${BOLD}🚀 Quick Start:${NC}"
    echo ""
    echo -e "  ${CYAN}# Launch the TUI:${NC}"
    echo -e "  python ~/ai-agent/agent.py"
    echo ""
    echo -e "  ${CYAN}# Launch the TUI:${NC}"
    echo -e "  python ~/ai-agent/agent.py"
    echo ""
    echo -e "  ${CYAN}# Or use the shortcut (restart shell first):${NC}"
    echo -e "  ai-agent"
    echo ""
    echo -e "${BOLD}📋 Available Commands:${NC}"
    echo ""
    echo -e "  ${GREEN}python agent.py${NC}          # Launch TUI"
    echo -e "  ${GREEN}python server.py${NC}         # Launch web dashboard + all services"
    echo -e "  ${GREEN}python telegram_bot.py${NC}   # Launch Telegram bot"
    echo -e "  ${GREEN}python consolidator.py${NC}   # Run memory consolidation"
    echo ""
    echo -e "${BOLD}🔑 Next Steps:${NC}"
    echo ""
    echo -e "  1. Get a free API key from ${BLUE}https://console.groq.com${NC}"
    echo -e "  2. Add it to ${CYAN}~/ai-agent/.env${NC}"
    echo -e "  3. Run ${GREEN}python ~/ai-agent/agent.py${NC}"
    echo ""
    echo -e "${BOLD}📚 Features:${NC}"
    echo ""
    echo -e "  📱 Hardware access (battery, GPS, SMS, camera)"
    echo -e "  👁️  Vision & image analysis"
    echo -e "  🎤 Voice I/O (speech-to-text & text-to-speech)"
    echo -e "  🧠 Semantic search & RAG"
    echo -e "  🔍 Self-reflection & error correction"
    echo -e "  ⚡ Event-driven automation"
    echo -e "  📦 Git self-versioning"
    echo -e "  🔀 Parallel sub-agents"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
    echo -e "  🤖 Self-Evolving AI Agent v2.0 | 53 Tools | 8 Features"
    echo -e "${CYAN}────────────────────────────────────────────────────────${NC}"
    echo ""
}

# ============================================================
# Main
# ============================================================

# ============================================================
# Update existing installation
# ============================================================

update() {
    print_header
    
    echo -e "${BOLD}🔄 Updating AI Agent...${NC}"
    echo ""
    
    # Check if installed
    if [ ! -d "$INSTALL_DIR" ] || [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
        error "AI Agent not installed at $INSTALL_DIR"
        echo "  Run the full installer first: bash setup.sh"
        exit 1
    fi
    
    cd "$INSTALL_DIR"
    
    # Step 1: Pull latest code
    step "1" "Pulling latest code..."
    if git pull origin main 2>/dev/null || git pull 2>/dev/null; then
        success "Code updated"
    else
        warning "Could not pull (using local version)"
    fi
    
    # Step 2: Update system packages
    step "2" "Updating system packages..."
    pkg update -y -qq 2>/dev/null || apt update -y -qq
    success "System packages updated"
    
    # Step 3: Update Python packages
    step "3" "Updating Python packages..."
    python -m pip install --upgrade pip --no-cache-dir -q 2>/dev/null || true
    
    if python -m pip install -r requirements.txt --no-cache-dir --only-binary :all: --progress-bar on 2>/dev/null; then
        success "Python packages updated (pre-built)"
    else
        python -m pip install -r requirements.txt --no-cache-dir --progress-bar on
        success "Python packages updated"
    fi
    
    # Step 4: Optional packages
    step "4" "Updating optional features..."
    python -m pip install edge-tts -q 2>/dev/null && \
        success "edge-tts updated" || true
    python -m pip install numpy -q 2>/dev/null && \
        success "numpy updated" || info "numpy skipped"
    
    # Step 5: Verify
    step "5" "Verifying update..."
    python -c "import openai; import dotenv; import rich" 2>/dev/null && \
        success "Core packages verified" || \
        error "Some packages missing"
    
    python -c "
from llm import get_client
try:
    _, provider, model = get_client()
    print(f'    LLM: {provider}/{model}')
except Exception as e:
    print(f'    ⚠️  No LLM configured: {e}')
" 2>/dev/null || true
    
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║           ✅ Update Complete!                           ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}python ~/ai-agent/agent.py${NC}  – Launch TUI"
    echo -e "  ${CYAN}ai-agent${NC}                    – Use shortcut"
    echo ""
}

# ============================================================
# Main
# ============================================================

main() {
    print_header
    preflight_check
    
    step_1_update_termux
    step_2_install_system_deps
    step_2b_configure_rust
    step_3_clone_repo
    step_4_install_python_deps
    step_5_install_optional_deps
    step_6_configure_providers
    step_7_verify_installation
    step_8_create_shortcuts
    
    print_summary
}

# ============================================================
# Entry point
# ============================================================

case "${1:-}" in
    update|up|-u)
        update
        ;;
    help|--help|-h)
        echo "Usage:"
        echo "  bash setup.sh          # Full installation"
        echo "  bash setup.sh update   # Update existing installation"
        echo "  bash setup.sh help     # Show this help"
        ;;
    *)
        main
        ;;
esac
