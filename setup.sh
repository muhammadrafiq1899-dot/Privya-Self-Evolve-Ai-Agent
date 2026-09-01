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
    
    # Build dependencies for Python packages
    PACKAGES="$PACKAGES build-essential" 2>/dev/null || true
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
        
        # Install with visible progress
        python -m pip install -r requirements.txt --no-cache-dir --progress-bar on
        
        if [ $? -eq 0 ]; then
            success "Core packages installed"
        else
            warning "Some core packages may have failed"
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

step_6_setup_config() {
    step "6" "Setting up configuration..."
    
    # Create .env from example if it doesn't exist
    if [ ! -f ".env" ]; then
        if [ -f ".env.example" ]; then
            cp .env.example .env
            success "Created .env from .env.example"
        else
            # Create .env manually
            cat > .env << 'ENVEOF'
# === LLM Providers (at least one required) ===
# Get free API keys from:
#   Groq: https://console.groq.com (recommended - fastest)
#   Together: https://api.together.xyz
#   OpenRouter: https://openrouter.ai
#   Gemini: https://aistudio.google.com

GROQ_API_KEY=
OPENROUTER_API_KEY=
GEMINI_API_KEY=
TOGETHER_API_KEY=

# === Telegram (optional) ===
# Create bot: https://t.me/BotFather
TELEGRAM_BOT_TOKEN=

# === Obsidian REST API (optional) ===
OBSIDIAN_API_KEY=
OBSIDIAN_URL=http://127.0.0.1:27123
OBSIDIAN_VAULT=~/ai-agent/vault
ENVEOF
            success "Created .env configuration file"
        fi
    else
        info ".env already exists, skipping"
    fi
    
    # Create data directory
    mkdir -p "$HOME/.ai-agent"
    success "Data directory created at ~/.ai-agent"
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
    echo -e "  ${CYAN}# Edit .env to add your API key:${NC}"
    echo -e "  nano ~/ai-agent/.env"
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

main() {
    print_header
    preflight_check
    
    step_1_update_termux
    step_2_install_system_deps
    step_3_clone_repo
    step_4_install_python_deps
    step_5_install_optional_deps
    step_6_setup_config
    step_7_verify_installation
    step_8_create_shortcuts
    
    print_summary
}

# Run installer
main
