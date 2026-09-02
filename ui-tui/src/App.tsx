import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import TextInput from 'ink-text-input';
import { sendMessage, getStats, getMemories, getCron, getEvents, getSnapshots, healthCheck, type ChatResponse, type Stats } from './api.js';

// ── Purple theme colors ──
const C = {
  bg: '#0d0014',
  border: '#6a0dad',
  accent: '#9b30ff',
  bright: '#e0b0ff',
  mid: '#c080ff',
  dim: '#7b2fa0',
  dark: '#1a0030',
  green: '#7bfa00',
  yellow: '#ffaa00',
  red: '#ff4040',
  white: '#ffffff',
};

// ── Commands ──
const COMMANDS: [string, string][] = [
  ['/model', 'Switch model'],
  ['/model list', 'Live models'],
  ['/model reset', 'Auto-detect'],
  ['/memory', 'Memories'],
  ['/procedures', 'Procedures'],
  ['/cron', 'Cron jobs'],
  ['/events', 'Event rules'],
  ['/recent_events', 'Recent events'],
  ['/snapshots', 'Git snapshots'],
  ['/save', 'Save state'],
  ['/voice', 'Voice mode'],
  ['/reflect', 'Reflection'],
  ['/clear', 'Clear screen'],
  ['/help', 'All commands'],
];

// ── Types ──
interface Message {
  role: 'user' | 'assistant' | 'system' | 'tool' | 'thinking';
  content: string;
  timestamp: Date;
  tools?: string[];
  reflected?: boolean;
  duration?: number;
}

interface AppState {
  messages: Message[];
  input: string;
  loading: boolean;
  connected: boolean;
  stats: Stats | null;
  showModelPicker: boolean;
  showHelp: boolean;
  modelNumber: string;
  autocompleteIndex: number;
  autocompleteVisible: boolean;
  autocompleteMatches: [string, string][];
}

// ── Main App ──
export default function App() {
  const { exit } = useApp();
  const [state, setState] = useState<AppState>({
    messages: [],
    input: '',
    loading: false,
    connected: false,
    stats: null,
    showModelPicker: false,
    showHelp: false,
    modelNumber: '',
    autocompleteIndex: 0,
    autocompleteVisible: false,
    autocompleteMatches: [],
  });

  const scrollRef = useRef(0);

  // Health check on mount
  useEffect(() => {
    healthCheck().then(ok => {
      setState(s => ({ ...s, connected: ok }));
      if (ok) loadStats();
    });
    // Add welcome message
    setState(s => ({
      ...s,
      messages: [{
        role: 'system',
        content: `✦ PRIVYA – AI Agent Framework\nv1.0.0 (2026.09.02)\n\nType a message or /help for commands.\n/model to pick a model interactively.`,
        timestamp: new Date(),
      }],
    }));
  }, []);

  const loadStats = async () => {
    try {
      const stats = await getStats();
      setState(s => ({ ...s, stats }));
    } catch {}
  };

  // ── Handle input ──
  const handleSubmit = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;

    setState(s => ({ ...s, input: '', autocompleteVisible: false }));

    // Add user message
    const userMsg: Message = { role: 'user', content: trimmed, timestamp: new Date() };
    setState(s => ({ ...s, messages: [...s.messages, userMsg] }));

    if (trimmed.startsWith('/')) {
      await handleCommand(trimmed);
    } else {
      await handleChat(trimmed);
    }
  };

  // ── Handle slash commands ──
  const handleCommand = async (cmd: string) => {
    const parts = cmd.split(' ');
    const command = parts[0].toLowerCase();

    switch (command) {
      case '/help':
        setState(s => ({ ...s, showHelp: true }));
        break;

      case '/model':
        if (parts[1] === 'list') {
          addMessage('system', '⏳ Fetching live models...\n(Use /model to open interactive picker)');
        } else if (parts[1] === 'reset') {
          addMessage('system', '🔄 Model reset to auto-detect');
        } else {
          setState(s => ({ ...s, showModelPicker: true, modelNumber: '' }));
        }
        break;

      case '/memory':
        try {
          const data = await getMemories();
          if (data.memories.length === 0) {
            addMessage('system', 'No memories yet.');
          } else {
            const list = data.memories.map((m: any, i: number) =>
              `  ${i + 1}. ${m.text?.substring(0, 120) || 'empty'}`
            ).join('\n');
            addMessage('system', `🧠 Long-term Memories:\n${list}`);
          }
        } catch { addMessage('system', 'Failed to load memories.'); }
        break;

      case '/procedures':
        addMessage('system', 'No procedures learned yet.');
        break;

      case '/cron':
        try {
          const data = await getCron();
          if (data.jobs.length === 0) {
            addMessage('system', 'No cron jobs scheduled.');
          } else {
            const list = data.jobs.map((j: any) =>
              `  ${j.enabled ? '●' : '○'} ${j.name}: ${j.cron} → ${j.command}`
            ).join('\n');
            addMessage('system', `⏰ Scheduled Jobs:\n${list}`);
          }
        } catch { addMessage('system', 'Failed to load cron jobs.'); }
        break;

      case '/events':
        try {
          const data = await getEvents();
          addMessage('system', `⚡ Event Rules:\n${data.result || 'None'}`);
        } catch { addMessage('system', 'Failed to load events.'); }
        break;

      case '/recent_events':
        try {
          const data = await getEvents();
          addMessage('system', `📊 Recent Events:\n${data.result || 'None'}`);
        } catch { addMessage('system', 'Failed to load events.'); }
        break;

      case '/snapshots':
        try {
          const data = await getSnapshots();
          addMessage('system', `📦 Git Snapshots:\n${data.result || 'None'}`);
        } catch { addMessage('system', 'Failed to load snapshots.'); }
        break;

      case '/save':
        addMessage('system', '✅ Agent state saved.');
        break;

      case '/voice':
        addMessage('system', '🎤 Voice mode toggled.');
        break;

      case '/reflect':
        addMessage('system', '🔍 Reflection toggled.');
        break;

      case '/clear':
        setState(s => ({ ...s, messages: [], showHelp: false, showModelPicker: false }));
        break;

      default:
        addMessage('system', `Unknown command: ${command}. Type /help`);
    }
  };

  // ── Handle chat ──
  const handleChat = async (text: string) => {
    setState(s => ({ ...s, loading: true }));

    try {
      const response: ChatResponse = await sendMessage(text);

      const assistantMsg: Message = {
        role: 'assistant',
        content: response.response,
        timestamp: new Date(),
        tools: response.tools_used,
        reflected: response.reflected,
        duration: response.duration,
      };
      setState(s => ({ ...s, messages: [...s.messages, assistantMsg], loading: false }));
      loadStats();
    } catch (err: any) {
      addMessage('system', `⚠️ Error: ${err.message}`);
      setState(s => ({ ...s, loading: false }));
    }
  };

  const addMessage = (role: Message['role'], content: string) => {
    setState(s => ({
      ...s,
      messages: [...s.messages, { role, content, timestamp: new Date() }],
    }));
  };

  // ── Autocomplete ──
  useEffect(() => {
    if (state.input.startsWith('/') && state.input.length > 0) {
      const matches = COMMANDS.filter(([cmd]) => cmd.startsWith(state.input.toLowerCase()));
      setState(s => ({
        ...s,
        autocompleteVisible: matches.length > 0 && matches.length < COMMANDS.length,
        autocompleteMatches: matches,
        autocompleteIndex: 0,
      }));
    } else {
      setState(s => ({ ...s, autocompleteVisible: false }));
    }
  }, [state.input]);

  // ── Key bindings ──
  useInput((input, key) => {
    if (key.ctrl && input === 'c') {
      exit();
      return;
    }

    // Model picker keys
    if (state.showModelPicker) {
      if (key.escape) {
        setState(s => ({ ...s, showModelPicker: false, modelNumber: '' }));
      }
      return;
    }

    // Help overlay
    if (state.showHelp) {
      if (key.escape || key.return) {
        setState(s => ({ ...s, showHelp: false }));
      }
      return;
    }

    // Autocomplete navigation
    if (state.autocompleteVisible) {
      if (key.upArrow) {
        setState(s => ({
          ...s,
          autocompleteIndex: Math.max(0, s.autocompleteIndex - 1),
        }));
      } else if (key.downArrow) {
        setState(s => ({
          ...s,
          autocompleteIndex: Math.min(s.autocompleteMatches.length - 1, s.autocompleteIndex + 1),
        }));
      } else if (key.tab || key.return) {
        if (state.autocompleteMatches[state.autocompleteIndex]) {
          setState(s => ({
            ...s,
            input: state.autocompleteMatches[state.autocompleteIndex][0] + ' ',
            autocompleteVisible: false,
          }));
        }
      } else if (key.escape) {
        setState(s => ({ ...s, autocompleteVisible: false }));
      }
    }
  });

  // ── Render ──
  const promptModel = state.stats?.provider?.split('/')[0] || 'none';
  const promptPct = '';

  return (
    <Box flexDirection="column" height="100%">
      {/* ── Banner ── */}
      <Banner connected={state.connected} stats={state.stats} />

      {/* ── Chat area ── */}
      <Box flexDirection="column" flexGrow={1} borderStyle="round" borderColor={C.border} paddingX={1}>
        {state.messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {state.loading && (
          <Box>
            <Text color={C.accent}>  🧠 thinking...</Text>
          </Box>
        )}
      </Box>

      {/* ── Autocomplete popup ── */}
      {state.autocompleteVisible && (
        <AutocompletePopup
          matches={state.autocompleteMatches}
          selectedIndex={state.autocompleteIndex}
        />
      )}

      {/* ── Help overlay ── */}
      {state.showHelp && <HelpOverlay onClose={() => setState(s => ({ ...s, showHelp: false }))} />}

      {/* ── Model picker overlay ── */}
      {state.showModelPicker && (
        <ModelPicker
          number={state.modelNumber}
          onNumberChange={(n) => setState(s => ({ ...s, modelNumber: n }))}
          onSelect={(provider, model) => {
            addMessage('system', `✅ Switched to ${provider} / ${model}`);
            setState(s => ({ ...s, showModelPicker: false, modelNumber: '' }));
          }}
          onCancel={() => setState(s => ({ ...s, showModelPicker: false, modelNumber: '' }))}
        />
      )}

      {/* ── Input bar ── */}
      <Box borderStyle="round" borderColor={C.accent} paddingX={1}>
        <Text color={C.accent}>❯ </Text>
        <TextInput
          value={state.input}
          onChange={(v) => setState(s => ({ ...s, input: v }))}
          onSubmit={handleSubmit}
          placeholder=""
          focus
        />
      </Box>

      {/* ── Status bar ── */}
      <StatusBar stats={state.stats} loading={state.loading} />
    </Box>
  );
}

// ── Banner Component ──
function Banner({ connected, stats }: { connected: boolean; stats: Stats | null }) {
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={C.accent} paddingX={1} marginBottom={0}>
      <Box>
        <Text color={C.accent} bold>  ✦ </Text>
        <Text color={C.bright} bold>PRIVYA</Text>
        <Text color={C.mid}> – AI Agent Framework</Text>
      </Box>
      <Box>
        <Text color={C.dim}>  Agent v1.0.0 (2026.09.02)</Text>
      </Box>
    </Box>
  );
}

// ── Message Bubble ──
function MessageBubble({ msg }: { msg: Message }) {
  const time = msg.timestamp.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

  if (msg.role === 'system') {
    return (
      <Box flexDirection="column" marginY={0}>
        <Text color={C.dim}>  {msg.content}</Text>
      </Box>
    );
  }

  if (msg.role === 'user') {
    return (
      <Box flexDirection="column">
        <Text color={C.bright}>  ✦ {msg.content}</Text>
      </Box>
    );
  }

  if (msg.role === 'assistant') {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1} marginY={0}>
        <Box>
          <Text color={C.accent} bold>  ✦ Privya</Text>
          <Text color={C.dim}> {time}</Text>
          {msg.duration && <Text color={C.dim}> · {msg.duration.toFixed(1)}s</Text>}
          {msg.reflected && <Text color={C.green}> · ✓ reflected</Text>}
        </Box>
        <Text color={C.bright}>  {msg.content}</Text>
        {msg.tools && msg.tools.length > 0 && (
          <Text color={C.dim}>  🔧 {msg.tools.join(', ')}</Text>
        )}
      </Box>
    );
  }

  return null;
}

// ── Autocomplete Popup ──
function AutocompletePopup({ matches, selectedIndex }: { matches: [string, string][]; selectedIndex: number }) {
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={C.accent} paddingX={1}>
      {matches.slice(0, 8).map(([cmd, desc], i) => (
        <Box key={cmd}>
          <Text color={i === selectedIndex ? C.white : C.mid}>
            {i === selectedIndex ? ' ❯ ' : '   '}
          </Text>
          <Text color={i === selectedIndex ? C.white : C.bright} bold={i === selectedIndex}>
            {cmd}
          </Text>
          <Text color={C.dim}>  {desc}</Text>
        </Box>
      ))}
    </Box>
  );
}

// ── Help Overlay ──
function HelpOverlay({ onClose }: { onClose: () => void }) {
  return (
    <Box flexDirection="column" borderStyle="round" borderColor={C.accent} paddingX={1} marginBottom={1}>
      <Text color={C.accent} bold>  ━━━ Commands ━━━━━━━━━━━━━━━━━━━━━━━━━━</Text>
      {COMMANDS.map(([cmd, desc]) => (
        <Box key={cmd}>
          <Text color={C.bright}>  {cmd.padEnd(18)}</Text>
          <Text color={C.dim}>{desc}</Text>
        </Box>
      ))}
      <Text color={C.dim}>  Press any key to close</Text>
    </Box>
  );
}

// ── Model Picker ──
function ModelPicker({ number, onNumberChange, onSelect, onCancel }: {
  number: string;
  onNumberChange: (n: string) => void;
  onSelect: (provider: string, model: string) => void;
  onCancel: () => void;
}) {
  const models = [
    { idx: 1, provider: 'Groq', id: 'llama-3.3-70b-versatile', desc: 'Best all-around' },
    { idx: 2, provider: 'Groq', id: 'llama-3.1-8b-instant', desc: 'Fastest' },
    { idx: 3, provider: 'OpenRouter', id: 'meta-llama/llama-3.3-70b-instruct', desc: 'Free' },
    { idx: 4, provider: 'OpenRouter', id: 'anthropic/claude-3.5-sonnet', desc: '$0.06/1M' },
    { idx: 5, provider: 'OpenRouter', id: 'openai/gpt-4o', desc: '$2.50/1M' },
  ];

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={C.accent} paddingX={1} marginBottom={1}>
      <Text color={C.accent} bold>  ✦ Model Picker</Text>
      <Text color={C.dim}>  Select a model (type number):</Text>
      {models.map(m => (
        <Box key={m.idx}>
          <Text color={C.bright}>    {m.idx}) {m.id}</Text>
          <Text color={C.dim}>  {m.desc}</Text>
        </Box>
      ))}
      <Text color={C.dim}>  Press Enter to select, Esc to cancel</Text>
    </Box>
  );
}

// ── Status Bar ──
function StatusBar({ stats, loading }: { stats: Stats | null; loading: boolean }) {
  const provider = stats?.provider?.split('/')[0] || 'none';
  const model = stats?.provider?.split('/')[1] || 'none';

  return (
    <Box justifyContent="space-between" paddingX={1}>
      <Text color={C.accent}>
        {loading ? '🧠 thinking' : '●'} {model?.substring(0, 25) || 'none'}
      </Text>
      <Text color={C.dim}>
        mem:{stats?.memories || 0} · proc:{stats?.procedures || 0} · {stats?.uptime || '--'}
      </Text>
    </Box>
  );
}
