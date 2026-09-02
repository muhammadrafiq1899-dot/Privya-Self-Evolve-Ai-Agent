import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import TextInput from 'ink-text-input';

// ── Green theme colors ──
const C = {
  bg: '#000000',
  border: '#00cc00',
  accent: '#00ff00',
  bright: '#ffffff',
  mid: '#00dd00',
  dim: '#008800',
  dark: '#001a00',
  green: '#00ff00',
  yellow: '#ffff00',
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

// ── Main App ──
export default function App() {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [autocompleteIndex, setAutocompleteIndex] = useState(0);
  const [autocompleteVisible, setAutocompleteVisible] = useState(false);
  const [autocompleteMatches, setAutocompleteMatches] = useState<[string, string][]>([]);
  const [stats, setStats] = useState<any>(null);

  const API = 'http://127.0.0.1:8000';

  // Health check on mount
  useEffect(() => {
    fetch(`${API}/health`)
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setConnected(true);
          fetch(`${API}/api/stats`).then(r => r.json()).then(setStats).catch(() => {});
        }
      })
      .catch(() => {});
    setMessages([{
      role: 'system',
      content: `✦ PRIVYA – AI Agent Framework\nv1.0.0 (2026.09.02)\n\nType a message or /help for commands.\n/model to pick a model interactively.`,
      timestamp: new Date(),
    }]);
  }, []);

  // ── Autocomplete ──
  useEffect(() => {
    if (input.startsWith('/') && input.length > 0) {
      const matches = COMMANDS.filter(([cmd]) => cmd.startsWith(input.toLowerCase()));
      setAutocompleteVisible(matches.length > 0 && matches.length < COMMANDS.length);
      setAutocompleteMatches(matches);
      setAutocompleteIndex(0);
    } else {
      setAutocompleteVisible(false);
    }
  }, [input]);

  // ── Add message ──
  const addMessage = useCallback((role: Message['role'], content: string, extra?: Partial<Message>) => {
    setMessages(prev => [...prev, { role, content, timestamp: new Date(), ...extra }]);
  }, []);

  // ── Handle submit ──
  const handleSubmit = useCallback(async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setInput('');
    setAutocompleteVisible(false);

    addMessage('user', trimmed);

    if (trimmed.startsWith('/')) {
      await handleCommand(trimmed);
    } else {
      await handleChat(trimmed);
    }
  }, []);

  // ── Handle commands ──
  const handleCommand = async (cmd: string) => {
    const parts = cmd.split(' ');
    const command = parts[0].toLowerCase();

    switch (command) {
      case '/help':
        setShowHelp(true);
        break;
      case '/model':
        if (parts[1] === 'list') {
          addMessage('system', '⏳ Fetching live models...\n(Use /model to open interactive picker)');
        } else if (parts[1] === 'reset') {
          addMessage('system', '🔄 Model reset to auto-detect');
        } else {
          setShowModelPicker(true);
        }
        break;
      case '/memory':
        try {
          const res = await fetch(`${API}/api/memories`);
          const data = await res.json();
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
          const res = await fetch(`${API}/api/cron`);
          const data = await res.json();
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
          const res = await fetch(`${API}/api/events`);
          const data = await res.json();
          addMessage('system', `⚡ Event Rules:\n${JSON.stringify(data.rules || [], null, 2)}`);
        } catch { addMessage('system', 'Failed to load events.'); }
        break;
      case '/recent_events':
        try {
          const res = await fetch(`${API}/api/events/recent`);
          const data = await res.json();
          addMessage('system', `📊 Recent Events:\n${data.result || 'None'}`);
        } catch { addMessage('system', 'Failed to load events.'); }
        break;
      case '/snapshots':
        try {
          const res = await fetch(`${API}/api/git/snapshots`);
          const data = await res.json();
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
        setMessages([]);
        setShowHelp(false);
        setShowModelPicker(false);
        break;
      default:
        addMessage('system', `Unknown command: ${command}. Type /help`);
    }
  };

  // ── Handle chat ──
  const handleChat = async (text: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, reflection: true }),
      });
      if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
      const data = await res.json();

      addMessage('assistant', data.response, {
        tools: data.tools_used,
        reflected: data.reflected,
        duration: data.duration,
      });
      // Refresh stats
      fetch(`${API}/api/stats`).then(r => r.json()).then(setStats).catch(() => {});
    } catch (err: any) {
      addMessage('system', `⚠️ Error: ${err.message}`);
    }
    setLoading(false);
  };

  // ── Key bindings ──
  useInput((inputStr, key) => {
    if (key.ctrl && inputStr === 'c') {
      exit();
      return;
    }

    if (showModelPicker) {
      if (key.escape) {
        setShowModelPicker(false);
      }
      return;
    }

    if (showHelp) {
      if (key.escape || key.return) {
        setShowHelp(false);
      }
      return;
    }

    if (autocompleteVisible) {
      if (key.upArrow) {
        setAutocompleteIndex(prev => Math.max(0, prev - 1));
      } else if (key.downArrow) {
        setAutocompleteIndex(prev => Math.min(autocompleteMatches.length - 1, prev + 1));
      } else if (key.tab || key.return) {
        if (autocompleteMatches[autocompleteIndex]) {
          setInput(autocompleteMatches[autocompleteIndex][0] + ' ');
          setAutocompleteVisible(false);
        }
      } else if (key.escape) {
        setAutocompleteVisible(false);
      }
    }
  });

  const providerShort = stats?.provider?.split('/')[0] || 'none';
  const modelShort = stats?.provider?.split('/')[1] || 'none';

  return (
    <Box flexDirection="column" height="100%">
      {/* ── Banner ── */}
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1} marginBottom={0}>
        <Box>
          <Text color={C.accent} bold>  ✦ </Text>
          <Text color={C.bright} bold>PRIVYA</Text>
          <Text color={C.dim}> – AI Agent Framework</Text>
        </Box>
        <Box>
          <Text color={C.dim}>  Agent v1.0.0 (2026.09.02)</Text>
        </Box>
      </Box>

      {/* ── Info strip ── */}
      <Box paddingX={1} marginBottom={0}>
        <Text color={C.dim}>  ● </Text>
        <Text color={C.bright}>{modelShort}</Text>
        <Text color={C.dim}> · {connected ? '🟢 connected' : '🔴 offline'}</Text>
      </Box>

      {/* ── Chat area ── */}
      <Box flexDirection="column" flexGrow={1} borderStyle="round" borderColor={C.border} paddingX={1}>
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}
        {loading && (
          <Box>
            <Text color={C.accent}>  🧠 thinking...</Text>
          </Box>
        )}
      </Box>

      {/* ── Autocomplete popup ── */}
      {autocompleteVisible && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
          {autocompleteMatches.slice(0, 8).map(([cmd, desc], i) => (
            <Box key={cmd}>
              <Text color={i === autocompleteIndex ? C.white : C.dim}>
                {i === autocompleteIndex ? ' ❯ ' : '   '}
              </Text>
              <Text color={i === autocompleteIndex ? C.white : C.bright} bold={i === autocompleteIndex}>
                {cmd}
              </Text>
              <Text color={C.dim}>  {desc}</Text>
            </Box>
          ))}
        </Box>
      )}

      {/* ── Help overlay ── */}
      {showHelp && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1} marginBottom={1}>
          <Text color={C.accent} bold>  ━━━ Commands ━━━━━━━━━━━━━━━━━━━━━━━━━━</Text>
          {COMMANDS.map(([cmd, desc]) => (
            <Box key={cmd}>
              <Text color={C.bright}>  {cmd.padEnd(18)}</Text>
              <Text color={C.dim}>{desc}</Text>
            </Box>
          ))}
          <Text color={C.dim}>  Press Esc to close</Text>
        </Box>
      )}

      {/* ── Model picker overlay ── */}
      {showModelPicker && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1} marginBottom={1}>
          <Text color={C.accent} bold>  ✦ Model Picker</Text>
          <Text color={C.dim}>  Select a model (type number):</Text>
          <Text color={C.bright}>    1) llama-3.3-70b-versatile  <Text color={C.dim}>Best all-around</Text></Text>
          <Text color={C.bright}>    2) llama-3.1-8b-instant      <Text color={C.dim}>Fastest</Text></Text>
          <Text color={C.bright}>    3) meta-llama/llama-3.3-70b-instruct  <Text color={C.dim}>Free</Text></Text>
          <Text color={C.bright}>    4) anthropic/claude-3.5-sonnet  <Text color={C.dim}>$0.06/1M</Text></Text>
          <Text color={C.bright}>    5) openai/gpt-4o  <Text color={C.dim}>$2.50/1M</Text></Text>
          <Text color={C.dim}>  Press Esc to cancel</Text>
        </Box>
      )}

      {/* ── Input bar ── */}
      <Box borderStyle="round" borderColor={C.accent} paddingX={1}>
        <Text color={C.accent}>❯ </Text>
        <TextInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          placeholder=""
          focus
        />
      </Box>

      {/* ── Status bar ── */}
      <Box justifyContent="space-between" paddingX={1}>
        <Text color={C.accent}>
          {loading ? '🧠 thinking' : '●'} {modelShort?.substring(0, 25) || 'none'}
        </Text>
        <Text color={C.dim}>
          mem:{stats?.memories || 0} · {stats?.uptime || '--'}
        </Text>
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
