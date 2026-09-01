# 🤖 Self-Evolving AI Agent for Termux

A complete, self-evolving AI agent optimized for **Termux on Android** with **8 advanced features**: hardware access, vision, voice, semantic search, reflection, event-driven proactivity, git self-versioning, and sub-agent delegation.

## ⚡ One-Command Install

**Paste this single command into Termux to install everything:**

```bash
bash <(curl -s https://raw.githubusercontent.com/muhammadrafiq1899-dot/Privya-Self-Evolve-Ai-Agent/main/setup.sh)
```

Or if you already have the repo:

```bash
cd ~/self-evolving-agent && bash setup.sh
```

## ✨ Features

### Core Features
| Feature | Description |
|---------|-------------|
| **Multi-Provider LLM** | Groq, OpenRouter, Gemini, Together – automatic selection |
| **AsyncIO Throughout** | Non-blocking operations via AsyncOpenAI |
| **Three-Tier Memory** | Short-term (working), Long-term (file-backed), Procedural (learned) |
| **Sandboxed Execution** | Python/shell code runs in isolated subprocesses |
| **Natural Language Cron** | Schedule tasks with "every Monday at 9am" |
| **TUI Interface** | Rich terminal UI with Textual |
| **Telegram Bot** | Chat with your agent from Telegram |

### 🆕 Advanced Features
| # | Feature | Description | Difficulty |
|---|---------|-------------|------------|
| 1 | **📱 Hardware Access** | Termux:API for battery, GPS, SMS, camera, sensors | Easy |
| 2 | **👁️ Vision & Multimodal** | Image analysis via Gemini/Claude vision models | Easy |
| 3 | **🎤 Voice I/O** | STT (Groq Whisper) + TTS (edge-tts/termux-tts) | Medium |
| 4 | **🧠 Semantic Search (RAG)** | Vector embeddings for conceptual memory search | Medium |
| 5 | **🔍 Reflection Loop** | Self-critique before responding to reduce hallucinations | Medium |
| 6 | **⚡ Event-Driven Proactivity** | React to battery, SMS, location changes automatically | High |
| 7 | **📦 Git Self-Versioning** | Auto-commit code and learned skills for backup | Easy |
| 8 | **🔀 Sub-Agent Delegation** | Parallel worker agents for heavy research tasks | High |

## 📦 Project Structure

```
self-evolving-agent/
├── agent.py              # Main TUI (python agent.py)
├── telegram_bot.py       # Telegram bot (python telegram_bot.py)
├── consolidator.py       # Memory consolidation (python consolidator.py)
│
├── # Core modules
├── llm.py                # Multi-provider LLM abstraction
├── memory.py             # Three-tier memory system
├── tools.py              # Tool definitions & implementations
├── security.py           # Sandboxed execution layer
├── nl_cron.py            # Natural language to cron converter
│
├── # Feature modules
├── termux_hardware.py    # 📱 Termux:API hardware access
├── vision.py             # 👁️ Vision & multimodal support
├── voice.py              # 🎤 Voice I/O (STT + TTS)
├── semantic.py           # 🧠 Semantic vector search (RAG)
├── reflection.py         # 🔍 Reflection & self-correction
├── events.py             # ⚡ Event-driven proactivity
├── git_integration.py    # 📦 Git self-versioning
├── subagents.py          # 🔀 Sub-agent delegation
│
├── requirements.txt      # Python dependencies
└── .env.example          # Environment variable template
```

## 🚀 Quick Start

### Option A: One-Command Install (Recommended)

```bash
bash <(curl -s https://raw.githubusercontent.com/muhammadrafiq1899-dot/Privya-Self-Evolve-Ai-Agent/main/setup.sh)
```

This will:
- ✅ Update Termux packages
- ✅ Install Python, git, and dependencies
- ✅ Clone the repository
- ✅ Install all Python packages
- ✅ Set up configuration
- ✅ Create shortcuts

### Option B: Manual Install

```bash
# Update Termux
pkg update && pkg upgrade

# Install Python and git
pkg install python git

# Clone and setup
cd ~
git clone https://github.com/muhammadrafiq1899-dot/Privya-Self-Evolve-Ai-Agent.git ai-agent
cd self-evolving-agent

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Add at least one LLM API key

# Optional: Install Termux:API for hardware features
pkg install termux-api
```

### 2. Configure API Keys

Edit `.env` and add **at least one** LLM provider:

```bash
# Free options (recommended):
GROQ_API_KEY=gsk_...        # Free tier: groq.com
TOGETHER_API_KEY=...        # Free tier: together.ai

# Paid options:
OPENROUTER_API_KEY=...      # openrouter.ai
GEMINI_API_KEY=...          # Google AI Studio
```

### 3. Run

```bash
# Launch TUI (recommended for Termux)
python agent.py

# Or launch Telegram bot
python telegram_bot.py

# Or run memory consolidation
python consolidator.py
```

## 📱 Feature 1: Hardware Access (Termux:API)

Give your agent access to Android hardware:

```bash
# Install Termux:API
pkg install termux-api
```

### Available Hardware Tools

| Tool | Description |
|------|-------------|
| `battery_status` | Get battery level, charging status, temperature |
| `get_location` | Get GPS coordinates (requires location permission) |
| `send_sms` | Send SMS messages |
| `read_sms` | Read recent SMS messages |
| `take_photo` | Take photos with front/back camera |
| `vibrate` | Vibrate the device |
| `get_clipboard` | Read clipboard content |
| `set_clipboard` | Set clipboard content |
| `get_wifi_info` | Get WiFi connection info |
| `notification` | Show system notifications |
| `toast` | Show brief toast messages |

### Example Usage

```
You: What's my battery level?
Agent: [calls battery_status] Your battery is at 73% and charging.

You: Take a photo and tell me what you see
Agent: [calls take_photo, then analyze_image] I see a desk with a laptop and coffee cup.

You: Text Mom that I'll be late
Agent: [calls send_sms] SMS sent to Mom: "I'll be late"
```

## 👁️ Feature 2: Vision & Multimodal

Analyze images using vision-capable models (Gemini, Claude, GPT-4o):

### Available Vision Tools

| Tool | Description |
|------|-------------|
| `analyze_image` | Analyze any image file |
| `analyze_image_url` | Analyze image from URL |
| `take_and_analyze` | Take photo + analyze (combines Termux + vision) |
| `ocr_image` | Extract text from images (OCR) |
| `read_handwriting` | Transcribe handwritten notes |
| `analyze_chart` | Analyze charts/graphs |

### Example Usage

```
You: [upload photo] What error is on my laptop screen?
Agent: [calls ocr_image] The error says "ModuleNotFoundError: No module named 'requests'"

You: [upload chart] Analyze this sales chart
Agent: [calls analyze_chart] The chart shows Q3 revenue up 23% with...

You: Take a selfie and describe it
Agent: [calls take_photo_front, then analyze_image] I see a person with...
```

## 🎤 Feature 3: Voice I/O

Hands-free interaction via speech:

### Voice Tools

| Tool | Description | Requirement |
|------|-------------|-------------|
| `speech_to_text` | Transcribe audio files | Groq API key |
| `listen` | Record + transcribe (hands-free) | Termux:API |
| `text_to_speech` | Speak text aloud | edge-tts (free) |
| `voice_chat` | Speak agent responses | Any TTS backend |

### Setup

```bash
# For Groq Whisper STT (fastest):
# Add GROQ_API_KEY to .env

# For termux-tts (native):
pkg install termux-api

# For edge-tts (high quality, free):
pip install edge-tts
```

### Example Usage

```
You: /voice (toggle voice mode ON)
You: What's the weather like?
Agent: [speaks] The weather is currently 72°F and sunny...
```

## 🧠 Feature 4: Semantic Vector Search (RAG)

Upgrade from keyword search to conceptual meaning:

### Semantic Tools

| Tool | Description |
|------|-------------|
| `semantic_search` | Search knowledge base by meaning |
| `index_obsidian_vault` | Index Obsidian notes for semantic search |
| `search_obsidian` | Search Obsidian notes conceptually |
| `add_to_knowledge` | Add text to semantic KB |

### How It Works

- Uses sentence-transformers for local embeddings (or TF-IDF fallback)
- Stores vectors in SQLite for fast similarity search
- Enables queries like "What was that book I liked?" even if you never used the word "book"

### Setup (Optional)

```bash
# For best embeddings (optional):
pip install sentence-transformers

# Without it, uses TF-IDF fallback (less accurate but no extra deps)
```

## 🔍 Feature 5: Reflection & Self-Correction

The agent critiques its own work before responding:

### How It Works

1. Generates initial response
2. **Critic** reviews for errors, hallucinations, logic flaws
3. **Reviser** fixes identified issues
4. Returns refined response (typically 1-2 rounds)

### Reflection Tools

| Tool | Description |
|------|-------------|
| `reflect_on_response` | Critique and improve any response |
| `review_code` | Dedicated code review for bugs/security |
| `verify_math` | Verify math by solving independently |

### Toggle

```
/reflect    # Toggle reflection on/off
```

## ⚡ Feature 6: Event-Driven Proactivity

React to system events automatically:

### Event Types

| Event | Triggers When |
|-------|---------------|
| `battery` | Battery level changes |
| `sms_received` | New SMS arrives |
| `location_change` | GPS location changes |
| `charging` | Device starts/stops charging |
| `time` | Specific time reached |
| `idle` | Agent idle for too long |

### Event Tools

| Tool | Description |
|------|-------------|
| `add_event_rule` | Create automation rule |
| `remove_event_rule` | Remove a rule |
| `list_event_rules` | View all rules |
| `list_recent_events` | View recent events |

### Example Rules

```
You: If battery drops below 15%, turn on battery saver and text my wife
Agent: [calls add_event_rule] Rule "low_battery" created.

You: When I receive an SMS with a 2FA code, read it to me
Agent: [calls add_event_rule] Rule "2fa_reader" created.
```

## 📦 Feature 7: Git Self-Versioning

Auto-commit code and learned skills:

### Git Tools

| Tool | Description |
|------|-------------|
| `git_commit` | Stage and commit changes |
| `git_push` | Push to remote repository |
| `git_save_state` | Save full agent state (code + memory + procedures) |
| `git_rollback_agent` | Rollback to previous version |
| `git_list_snapshots` | View evolution history |
| `git_diff_evolution` | Compare versions |

### Commands

```
/save       # Save current agent state to git
/snapshots  # View git evolution history
```

## 🔀 Feature 8: Sub-Agent Delegation

Parallel worker agents for heavy tasks:

### Sub-Agent Tools

| Tool | Description |
|------|-------------|
| `research_parallel` | Research multiple topics simultaneously |
| `delegate_task` | Delegate to a specialized worker |
| `code_review_parallel` | Review multiple code files in parallel |

### Agent Types

| Type | Use Case |
|------|----------|
| `research` | Web research and information gathering |
| `code` | Code analysis and generation |
| `analysis` | Data analysis and reasoning |
| `writing` | Content generation |
| `summary` | Summarization |
| `custom` | Custom tasks |

### Example Usage

```
You: Research React vs Vue vs Svelte, compare them
Agent: [spawns 3 sub-agents in parallel, each researching one framework]
       [synthesizes findings into comprehensive comparison]

You: Review these 3 Python files for security issues
Agent: [spawns 3 parallel code reviews, returns combined report]
```

## 🔧 All Tools Reference

| Category | Tools |
|----------|-------|
| **Web** | `web_search`, `web_fetch` |
| **Code** | `run_python`, `run_shell` |
| **Files** | `read_file`, `write_file` |
| **Memory** | `save_memory`, `recall_memory`, `semantic_search`, `add_to_knowledge` |
| **Obsidian** | `obsidian_write`, `obsidian_read`, `index_obsidian_vault`, `search_obsidian` |
| **Schedule** | `add_cron_job`, `remove_cron_job`, `list_cron_jobs` |
| **Hardware** | `battery_status`, `get_location`, `send_sms`, `read_sms`, `take_photo`, `vibrate`, `get_clipboard`, `set_clipboard`, `get_wifi_info`, `notification`, `toast` |
| **Vision** | `analyze_image`, `analyze_image_url`, `take_and_analyze`, `ocr_image`, `read_handwriting`, `analyze_chart` |
| **Voice** | `speech_to_text`, `listen`, `text_to_speech`, `voice_chat` |
| **Reflection** | `reflect_on_response`, `review_code`, `verify_math` |
| **Events** | `add_event_rule`, `remove_event_rule`, `list_event_rules`, `list_recent_events` |
| **Git** | `git_commit`, `git_push`, `git_save_state`, `git_rollback_agent`, `git_list_snapshots`, `git_status`, `git_diff_evolution` |
| **Sub-agents** | `research_parallel`, `delegate_task`, `code_review_parallel` |

## 🧠 Memory System

### Short-Term (Working Memory)
- Rolling buffer of recent conversation turns
- Cleared between sessions

### Long-Term (File-Backed)
- Stored in `~/.ai-agent/long_term.jsonl`
- Persists across sessions
- Keyword searchable

### Procedural (Learned Skills)
- Stored in `~/.ai-agent/procedural.jsonl`
- Learned from successful tool trajectories
- Enhanced by `consolidator.py`

### Semantic (Vector Search)
- SQLite-backed vector store
- Local embeddings via sentence-transformers
- Enables conceptual search beyond keywords

## 🔄 Memory Consolidation

Run `consolidator.py` periodically to:

1. **Consolidate memories** – Merge similar/duplicate memories
2. **Learn procedures** – Discover repeatable tool workflows
3. **Update index** – Keep procedures searchable

```bash
python consolidator.py              # Full consolidation
python consolidator.py --scan       # Scan memories only
python consolidator.py --procedures # Learn procedures only
```

## ⏰ Natural Language Scheduling

```bash
You: Schedule a backup every day at 3am
Agent: Cron job "backup" added: 0 3 * * * → backup_script.sh

You: Run consolidation every Monday at 9am
Agent: Cron job "consolidation" added: 0 9 * * 1 → consolidator.py
```

## 📱 Telegram Bot Setup

1. Create a bot with [@BotFather](https://t.me/BotFather)
2. Add token to `.env`:
   ```bash
   TELEGRAM_BOT_TOKEN=your_token_here
   ```
3. Run:
   ```bash
   python telegram_bot.py
   ```

### Telegram Features

- 📷 **Photo analysis** – Upload a photo, get instant analysis
- 🎤 **Voice messages** – Send voice, get transcription + response
- 🔘 **Inline buttons** – Quick access to memory, procedures, events
- ⚡ **Event notifications** – Get notified of system events

### Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome + quick action buttons |
| `/memory` | View long-term memories |
| `/procedures` | View learned procedures |
| `/cron` | View scheduled jobs |
| `/events` | View event rules |
| `/snapshots` | View git snapshots |
| `/save` | Save agent state |
| `/reflect` | Toggle reflection |
| `/voice` | Toggle voice mode |
| `/clear` | Clear conversation |

## 🌐 Obsidian Integration

1. Install [Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api)
2. Configure in `.env`:
   ```bash
   OBSIDIAN_API_KEY=your_api_key
   OBSIDIAN_URL=http://127.0.0.1:27123
   OBSIDIAN_VAULT=~/ai-agent/vault
   ```
3. Index for semantic search:
   ```
   Agent: index my Obsidian vault
   ```

## ⚠️ Troubleshooting

**No LLM provider**
→ Add at least one API key to `.env`

**Module not found**
→ Run `pip install -r requirements.txt`

**Termux:API not working**
→ Install: `pkg install termux-api`

**Vision not working**
→ Ensure Gemini/OpenRouter key is set (vision-capable model)

**Voice not working**
→ Install edge-tts: `pip install edge-tts`

**Embeddings slow**
→ Install sentence-transformers: `pip install sentence-transformers`

## 📊 Data Storage

```
~/.ai-agent/
├── long_term.jsonl       # Long-term memories
├── procedural.jsonl      # Learned procedures
├── procedures_index.json # Procedure lookup index
├── cron_jobs.json        # Scheduled tasks
├── event_rules.json      # Event automation rules
├── events.jsonl          # Event log
├── event_actions.jsonl   # Action execution log
├── evolution.jsonl       # Git evolution log
├── vectors.db            # Semantic vector store
├── sessions/             # Session transcripts
└── ...
```

## 📄 License

MIT License – Use freely in your projects.

---

**Made with ❤️ for the Termux community**
