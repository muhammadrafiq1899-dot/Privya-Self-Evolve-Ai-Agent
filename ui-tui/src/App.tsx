import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Box, Text, useInput, useApp } from 'ink';
import TextInput from 'ink-text-input';

// ── Green theme (Hermes-style) ──
const C = {
  border: '#00cc00',
  accent: '#00ff00',
  white: '#ffffff',
  dim: '#008800',
  green: '#00ff00',
  red: '#ff4040',
  yellow: '#ffff00',
};

const API = 'http://127.0.0.1:8000';

const COMMANDS: [string, string][] = [
  ['/model', 'Switch model (interactive)'],
  ['/model list', 'Fetch live models'],
  ['/model reset', 'Auto-detect from .env'],
  ['/memory', 'View long-term memories'],
  ['/procedures', 'View learned procedures'],
  ['/cron', 'View scheduled jobs'],
  ['/events', 'View event rules'],
  ['/recent_events', 'Recent system events'],
  ['/snapshots', 'Git snapshots'],
  ['/save', 'Save agent state'],
  ['/voice', 'Toggle voice mode'],
  ['/reflect', 'Toggle reflection'],
  ['/clear', 'Clear screen'],
  ['/help', 'Show all commands'],
];

interface Msg {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  time: Date;
  tools?: string[];
  dur?: number;
}

interface ModelItem {
  provider: string;
  providerName: string;
  id: string;
  name: string;
  desc: string;
}

// ══════════════════════════════════════════════════════════════════
// Main App
// ══════════════════════════════════════════════════════════════════
export default function App() {
  const { exit } = useApp();

  // ── State ──
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [connected, setConnected] = useState(false);
  const [stats, setStats] = useState<any>(null);
  const [scrollOffset, setScrollOffset] = useState(0);

  // Overlays
  const [showHelp, setShowHelp] = useState(false);
  const [showPicker, setShowPicker] = useState(false);
  const [pickerModels, setPickerModels] = useState<ModelItem[]>([]);
  const [pickerIdx, setPickerIdx] = useState(0);
  const [pickerLoading, setPickerLoading] = useState(false);

  // Autocomplete
  const [acVisible, setAcVisible] = useState(false);
  const [acMatches, setAcMatches] = useState<[string, string][]>([]);
  const [acIdx, setAcIdx] = useState(0);

  // ── Refs ──
  const chatRef = useRef<Box>(null);

  // ── Init ──
  useEffect(() => {
    fetch(`${API}/health`).then(r => r.ok ? r.json() : null).then(d => {
      if (d) {
        setConnected(true);
        fetchStats();
      }
    }).catch(() => {});
    setMsgs([{
      role: 'system',
      content: '✦ PRIVYA – AI Agent Framework\nv1.0.0 (2026.09.02)\n\nType a message or /help for commands.\n/model to pick a model interactively.\nArrow keys ↑↓ to scroll.',
      time: new Date(),
    }]);
  }, []);

  const fetchStats = () => {
    fetch(`${API}/api/stats`).then(r => r.json()).then(setStats).catch(() => {});
  };

  // ── Autocomplete ──
  useEffect(() => {
    if (input.startsWith('/') && input.length > 0) {
      const matches = COMMANDS.filter(([cmd]) => cmd.startsWith(input.toLowerCase()));
      setAcVisible(matches.length > 0 && matches.length < COMMANDS.length);
      setAcMatches(matches);
      setAcIdx(0);
    } else {
      setAcVisible(false);
    }
  }, [input]);

  // ── Add message ──
  const addMsg = useCallback((role: Msg['role'], content: string, extra?: Partial<Msg>) => {
    setMsgs(prev => [...prev, { role, content, time: new Date(), ...extra }]);
    setScrollOffset(0); // auto-scroll to bottom
  }, []);

  // ── Handle submit ──
  const handleSubmit = useCallback(async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setInput('');
    setAcVisible(false);
    addMsg('user', trimmed);
    if (trimmed.startsWith('/')) {
      await handleCommand(trimmed);
    } else {
      await handleChat(trimmed);
    }
  }, [addMsg]);

  // ── Commands ──
  const handleCommand = async (cmd: string) => {
    const parts = cmd.split(' ');
    const command = parts[0].toLowerCase();

    switch (command) {
      case '/help': setShowHelp(true); break;
      case '/clear': setMsgs([]); break;
      case '/save': addMsg('system', '✅ Agent state saved.'); break;
      case '/voice': addMsg('system', '🎤 Voice mode toggled.'); break;
      case '/reflect': addMsg('system', '🔍 Reflection toggled.'); break;
      case '/procedures': addMsg('system', 'No procedures learned yet.'); break;

      case '/model': {
        if (parts[1] === 'list') {
          // Fetch live models and show in chat
          addMsg('system', '⏳ Fetching live models from providers...');
          try {
            const res = await fetch(`${API}/api/models`);
            const data = await res.json();
            let list = '';
            for (const p of data.providers || []) {
              list += `\n━━━ ${p.display_name} (${p.models.length} models) ━━━\n`;
              for (const m of p.models.slice(0, 20)) {
                list += `  • ${m.id}`;
                if (m.description) list += `  ${m.description.substring(0, 50)}`;
                list += '\n';
              }
              if (p.models.length > 20) list += `  ... and ${p.models.length - 20} more\n`;
            }
            addMsg('system', list || 'No models available.');
          } catch { addMsg('system', '⚠️ Failed to fetch models.'); }
        } else if (parts[1] === 'reset') {
          try {
            await fetch(`${API}/api/models/switch?provider=&model=`);
            addMsg('system', '🔄 Model reset to auto-detect');
            fetchStats();
          } catch { addMsg('system', '⚠️ Reset failed.'); }
        } else if (parts[1] && parts[1] !== 'list' && parts[1] !== 'reset') {
          // Direct switch: /model groq llama-3.3-70b-versatile
          const provider = parts[1];
          const model = parts[2] || '';
          try {
            const res = await fetch(`${API}/api/models/switch?provider=${encodeURIComponent(provider)}&model=${encodeURIComponent(model)}`);
            const data = await res.json();
            if (data.error) addMsg('system', `❌ ${data.error}`);
            else { addMsg('system', `✅ ${data.message}`); fetchStats(); }
          } catch { addMsg('system', '⚠️ Switch failed.'); }
        } else {
          // Interactive picker
          openModelPicker();
        }
        break;
      }

      case '/memory': {
        try {
          const res = await fetch(`${API}/api/memories`);
          const data = await res.json();
          if (!data.memories?.length) { addMsg('system', 'No memories yet.'); break; }
          const list = data.memories.map((m: any, i: number) =>
            `  ${i + 1}. ${m.text?.substring(0, 120) || 'empty'}`
          ).join('\n');
          addMsg('system', `🧠 Long-term Memories:\n${list}`);
        } catch { addMsg('system', 'Failed to load memories.'); }
        break;
      }

      case '/cron': {
        try {
          const res = await fetch(`${API}/api/cron`);
          const data = await res.json();
          if (!data.jobs?.length) { addMsg('system', 'No cron jobs scheduled.'); break; }
          const list = data.jobs.map((j: any) =>
            `  ${j.enabled ? '●' : '○'} ${j.name}: ${j.cron} → ${j.command}`
          ).join('\n');
          addMsg('system', `⏰ Scheduled Jobs:\n${list}`);
        } catch { addMsg('system', 'Failed to load cron jobs.'); }
        break;
      }

      case '/events': {
        try {
          const res = await fetch(`${API}/api/events`);
          const data = await res.json();
          addMsg('system', `⚡ Event Rules:\n${JSON.stringify(data.rules || [], null, 2)}`);
        } catch { addMsg('system', 'Failed to load events.'); }
        break;
      }

      case '/recent_events': {
        try {
          const res = await fetch(`${API}/api/events/recent`);
          const data = await res.json();
          addMsg('system', `📊 Recent Events:\n${data.result || 'None'}`);
        } catch { addMsg('system', 'Failed to load events.'); }
        break;
      }

      case '/snapshots': {
        try {
          const res = await fetch(`${API}/api/git/snapshots`);
          const data = await res.json();
          addMsg('system', `📦 Git Snapshots:\n${data.result || 'None'}`);
        } catch { addMsg('system', 'Failed to load snapshots.'); }
        break;
      }

      default:
        addMsg('system', `Unknown command: ${command}. Type /help`);
    }
  };

  // ── Chat ──
  const handleChat = async (text: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, reflection: true }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      addMsg('assistant', data.response, { tools: data.tools_used, dur: data.duration });
      fetchStats();
    } catch (err: any) {
      addMsg('system', `⚠️ Error: ${err.message}`);
    }
    setLoading(false);
  };

  // ── Model Picker ──
  const openModelPicker = async () => {
    setShowPicker(true);
    setPickerLoading(true);
    setPickerIdx(0);
    try {
      const res = await fetch(`${API}/api/models`);
      const data = await res.json();
      const items: ModelItem[] = [];
      for (const p of data.providers || []) {
        for (const m of p.models) {
          items.push({
            provider: p.provider,
            providerName: p.display_name,
            id: m.id,
            name: m.name || m.id,
            desc: m.description || '',
          });
        }
      }
      setPickerModels(items);
    } catch {
      setPickerModels([]);
    }
    setPickerLoading(false);
  };

  const selectModel = async (item: ModelItem) => {
    setShowPicker(false);
    addMsg('system', `⏳ Switching to ${item.providerName} / ${item.id}...`);
    try {
      const res = await fetch(`${API}/api/models/switch?provider=${encodeURIComponent(item.provider)}&model=${encodeURIComponent(item.id)}`);
      const data = await res.json();
      if (data.error) addMsg('system', `❌ ${data.error}`);
      else { addMsg('system', `✅ Switched to ${item.providerName} / ${item.id}`); fetchStats(); }
    } catch { addMsg('system', '⚠️ Switch failed.'); }
  };

  // ── Key bindings ──
  useInput((inp, key) => {
    if (key.ctrl && inp === 'c') { exit(); return; }

    // Help overlay
    if (showHelp) { if (key.escape || key.return) setShowHelp(false); return; }

    // Model picker
    if (showPicker) {
      if (key.escape) { setShowPicker(false); return; }
      if (key.upArrow) { setPickerIdx(prev => Math.max(0, prev - 1)); return; }
      if (key.downArrow) { setPickerIdx(prev => Math.min(pickerModels.length - 1, prev + 1)); return; }
      if (key.return && pickerModels[pickerIdx]) { selectModel(pickerModels[pickerIdx]); return; }
      return;
    }

    // Scroll
    if (key.upArrow && !acVisible) { setScrollOffset(prev => prev + 1); return; }
    if (key.downArrow && !acVisible) { setScrollOffset(prev => Math.max(0, prev - 1)); return; }
    if (key.pageUp) { setScrollOffset(prev => prev + 20); return; }
    if (key.pageDown) { setScrollOffset(prev => Math.max(0, prev - 20)); return; }

    // Autocomplete
    if (acVisible) {
      if (key.upArrow) { setAcIdx(prev => Math.max(0, prev - 1)); return; }
      if (key.downArrow) { setAcIdx(prev => Math.min(acMatches.length - 1, prev + 1)); return; }
      if (key.tab || (key.return && acMatches[acIdx])) {
        setInput(acMatches[acIdx]?.[0] + ' ');
        setAcVisible(false);
        return;
      }
      if (key.escape) { setAcVisible(false); return; }
    }
  });

  const modelShort = stats?.provider?.split('/')[1] || 'none';
  const toolsCount = stats?.tools_count || 53;

  // ════════════════════════════════════════════════════════════════
  // RENDER
  // ════════════════════════════════════════════════════════════════
  return (
    <Box flexDirection="column" height="100%">
      {/* ── Header ── */}
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
        <Box>
          <Text color={C.accent} bold>  ✦ </Text>
          <Text color={C.white} bold>PRIVYA</Text>
          <Text color={C.dim}> – AI Agent Framework</Text>
        </Box>
        <Box>
          <Text color={C.dim}>  Agent v1.0.0 (2026.09.02)</Text>
        </Box>
      </Box>

      {/* ── Info strip ── */}
      <Box paddingX={1}>
        <Text color={C.dim}>  ● </Text>
        <Text color={C.white} bold>{modelShort}</Text>
        <Text color={C.dim}> · {toolsCount} tools</Text>
        <Text color={C.dim}> · {connected ? '🟢 connected' : '🔴 offline'}</Text>
      </Box>

      {/* ── Model Picker Overlay ── */}
      {showPicker && (
        <ModelPickerView
          models={pickerModels}
          loading={pickerLoading}
          selectedIdx={pickerIdx}
          onSelect={selectModel}
          onCancel={() => setShowPicker(false)}
        />
      )}

      {/* ── Help Overlay ── */}
      {showHelp && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
          <Text color={C.accent} bold>  ━━━ Commands ━━━━━━━━━━━━━━━━━━━━━━━━━━━</Text>
          {COMMANDS.map(([cmd, desc]) => (
            <Box key={cmd}>
              <Text color={C.white}>  {cmd.padEnd(18)}</Text>
              <Text color={C.dim}>{desc}</Text>
            </Box>
          ))}
          <Text color={C.dim}>  Press Esc to close</Text>
        </Box>
      )}

      {/* ── Chat (scrollable) ── */}
      {!showPicker && !showHelp && (
        <Box ref={chatRef} flexDirection="column" flexGrow={1} paddingX={1}>
          {msgs.slice(-Math.max(20, msgs.length - scrollOffset)).map((msg, i) => (
            <MsgBubble key={i} msg={msg} />
          ))}
          {loading && (
            <Box>
              <Text color={C.accent}>  🧠 thinking...</Text>
            </Box>
          )}
          {scrollOffset > 0 && (
            <Text color={C.dim}>  ↑ {scrollOffset} lines scrolled</Text>
          )}
        </Box>
      )}

      {/* ── Autocomplete ── */}
      {acVisible && (
        <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
          {acMatches.slice(0, 6).map(([cmd, desc], i) => (
            <Box key={cmd}>
              <Text color={i === acIdx ? C.white : C.dim}>{i === acIdx ? ' ❯ ' : '   '}</Text>
              <Text color={i === acIdx ? C.white : C.green} bold={i === acIdx}>{cmd}</Text>
              <Text color={C.dim}>  {desc}</Text>
            </Box>
          ))}
        </Box>
      )}

      {/* ── Input ── */}
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
          {loading ? '🧠' : '●'} {modelShort?.substring(0, 30) || 'none'}
        </Text>
        <Text color={C.dim}>
          mem:{stats?.memories || 0} · proc:{stats?.procedures || 0} · {stats?.uptime || '--'}
        </Text>
      </Box>
    </Box>
  );
}

// ══════════════════════════════════════════════════════════════════
// Message Bubble
// ══════════════════════════════════════════════════════════════════
function MsgBubble({ msg }: { msg: Msg }) {
  const t = msg.time.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit' });

  if (msg.role === 'system') {
    return (
      <Box flexDirection="column">
        <Text color={C.dim}>  {msg.content}</Text>
      </Box>
    );
  }

  if (msg.role === 'user') {
    return (
      <Box flexDirection="column">
        <Text color={C.white}>  ✦ {msg.content}</Text>
      </Box>
    );
  }

  if (msg.role === 'assistant') {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
        <Box>
          <Text color={C.accent} bold>  ✦ Privya</Text>
          <Text color={C.dim}> {t}</Text>
          {msg.dur != null && <Text color={C.dim}> · {msg.dur.toFixed(1)}s</Text>}
        </Box>
        <Text color={C.white}>  {msg.content}</Text>
        {msg.tools && msg.tools.length > 0 && (
          <Text color={C.dim}>  🔧 {msg.tools.join(', ')}</Text>
        )}
      </Box>
    );
  }

  return null;
}

// ══════════════════════════════════════════════════════════════════
// Model Picker (arrow-key navigable)
// ══════════════════════════════════════════════════════════════════
function ModelPickerView({ models, loading, selectedIdx, onSelect, onCancel }: {
  models: ModelItem[];
  loading: boolean;
  selectedIdx: number;
  onSelect: (item: ModelItem) => void;
  onCancel: () => void;
}) {
  const [visibleStart, setVisibleStart] = useState(0);
  const VISIBLE = 12;

  useEffect(() => {
    if (selectedIdx < visibleStart) setVisibleStart(selectedIdx);
    else if (selectedIdx >= visibleStart + VISIBLE) setVisibleStart(selectedIdx - VISIBLE + 1);
  }, [selectedIdx]);

  if (loading) {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
        <Text color={C.accent} bold>  ✦ Model Picker</Text>
        <Text color={C.dim}>  ⏳ Loading models from providers...</Text>
      </Box>
    );
  }

  if (models.length === 0) {
    return (
      <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
        <Text color={C.accent} bold>  ✦ Model Picker</Text>
        <Text color={C.dim}>  No models available. Configure an API key in .env</Text>
        <Text color={C.dim}>  Press Esc to close</Text>
      </Box>
    );
  }

  const visible = models.slice(visibleStart, visibleStart + VISIBLE);
  let lastProvider = '';

  return (
    <Box flexDirection="column" borderStyle="round" borderColor={C.border} paddingX={1}>
      <Text color={C.accent} bold>  ✦ Model Picker – {models.length} available</Text>
      <Text color={C.dim}>  ↑↓ navigate · Enter select · Esc cancel</Text>
      {visible.map((m, vi) => {
        const idx = visibleStart + vi;
        const showHeader = m.provider !== lastProvider;
        lastProvider = m.provider;
        return (
          <React.Fragment key={idx}>
            {showHeader && (
              <Text color={C.accent}>  ── {m.providerName} ──</Text>
            )}
            <Box>
              <Text color={idx === selectedIdx ? C.white : C.dim}>
                {idx === selectedIdx ? ' ❯ ' : '   '}
              </Text>
              <Text color={idx === selectedIdx ? C.white : C.green} bold={idx === selectedIdx}>
                {m.id.substring(0, 35).padEnd(35)}
              </Text>
              <Text color={C.dim}>{m.desc.substring(0, 30)}</Text>
            </Box>
          </React.Fragment>
        );
      })}
      {models.length > VISIBLE && (
        <Text color={C.dim}>  ({selectedIdx + 1}/{models.length} · {models.length - visibleStart - VISIBLE > 0 ? `${models.length - visibleStart - VISIBLE} more below` : 'end'})</Text>
      )}
    </Box>
  );
}
