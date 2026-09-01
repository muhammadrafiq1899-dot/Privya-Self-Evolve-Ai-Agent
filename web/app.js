/**
 * AI Agent Dashboard - Frontend Logic
 * Handles chat, stats, activity, and real-time updates via WebSocket
 */

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const API_BASE = window.location.origin + '/api';
const WS_URL = `ws://${window.location.host}/ws`;

let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;

// ---------------------------------------------------------------------------
// WebSocket Connection
// ---------------------------------------------------------------------------

function connectWebSocket() {
    try {
        ws = new WebSocket(WS_URL);
        
        ws.onopen = () => {
            console.log('WebSocket connected');
            updateStatus('online', 'Connected');
            reconnectAttempts = 0;
        };
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketMessage(data);
            } catch (e) {
                console.error('Failed to parse WS message:', e);
            }
        };
        
        ws.onclose = () => {
            console.log('WebSocket disconnected');
            updateStatus('offline', 'Disconnected');
            attemptReconnect();
        };
        
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    } catch (e) {
        console.error('Failed to create WebSocket:', e);
        attemptReconnect();
    }
}

function attemptReconnect() {
    if (reconnectAttempts < MAX_RECONNECT) {
        reconnectAttempts++;
        setTimeout(connectWebSocket, 2000 * reconnectAttempts);
    }
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'chat_response':
            addMessage('assistant', data.content);
            hideTypingIndicator();
            break;
        case 'tool_call':
            addMessage('tool', `🔧 ${data.tool}: ${data.preview || '...'}`);
            break;
        case 'activity':
            addActivity(data.time, data.text);
            break;
        case 'stats':
            updateStats(data);
            break;
        default:
            console.log('Unknown WS message type:', data.type);
    }
}

// ---------------------------------------------------------------------------
// Chat Functions
// ---------------------------------------------------------------------------

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;
    
    addMessage('user', text);
    input.value = '';
    showTypingIndicator();
    
    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text }),
        });
        
        if (!response.ok) throw new Error('Chat request failed');
        
        const data = await response.json();
        hideTypingIndicator();
        
        if (data.response) {
            addMessage('assistant', data.response);
        }
        if (data.tools_used && data.tools_used.length > 0) {
            data.tools_used.forEach(tool => {
                addMessage('tool', `🔧 Used: ${tool}`);
            });
        }
    } catch (e) {
        hideTypingIndicator();
        addMessage('system', `Error: ${e.message}`);
    }
}

function addMessage(role, content) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.textContent = content;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function clearChat() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = '<div class="message system"><div class="message-content">Chat cleared.</div></div>';
}

function showTypingIndicator() {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.id = 'typing-indicator';
    div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function hideTypingIndicator() {
    const indicator = document.getElementById('typing-indicator');
    if (indicator) indicator.remove();
}

// ---------------------------------------------------------------------------
// Stats Functions
// ---------------------------------------------------------------------------

async function refreshStats() {
    try {
        const response = await fetch(`${API_BASE}/stats`);
        if (!response.ok) throw new Error('Stats fetch failed');
        const data = await response.json();
        updateStats(data);
    } catch (e) {
        console.error('Failed to refresh stats:', e);
    }
}

function updateStats(data) {
    document.getElementById('stat-memories').textContent = data.memories || 0;
    document.getElementById('stat-procedures').textContent = data.procedures || 0;
    document.getElementById('stat-tools').textContent = data.tools_count || 53;
    document.getElementById('stat-requests').textContent = data.requests || 0;
    document.getElementById('provider').textContent = `Provider: ${data.provider || '--'}`;
    document.getElementById('uptime').textContent = `Uptime: ${data.uptime || '--'}`;
    document.getElementById('last-update').textContent = `Last update: ${new Date().toLocaleTimeString()}`;
}

// ---------------------------------------------------------------------------
// Activity Functions
// ---------------------------------------------------------------------------

async function refreshActivity() {
    try {
        const response = await fetch(`${API_BASE}/activity`);
        if (!response.ok) throw new Error('Activity fetch failed');
        const data = await response.json();
        
        const container = document.getElementById('activity-list');
        container.innerHTML = '';
        
        if (data.activities && data.activities.length > 0) {
            data.activities.forEach(act => {
                addActivity(act.time, act.text);
            });
        } else {
            container.innerHTML = '<div class="activity-item"><span class="activity-text">No recent activity.</span></div>';
        }
    } catch (e) {
        console.error('Failed to refresh activity:', e);
    }
}

function addActivity(time, text) {
    const container = document.getElementById('activity-list');
    const div = document.createElement('div');
    div.className = 'activity-item';
    div.innerHTML = `<span class="activity-time">${time}</span><span class="activity-text">${text}</span>`;
    container.insertBefore(div, container.firstChild);
    
    // Keep only last 20 activities
    while (container.children.length > 20) {
        container.removeChild(container.lastChild);
    }
}

// ---------------------------------------------------------------------------
// Memories Functions
// ---------------------------------------------------------------------------

async function refreshMemories() {
    try {
        const response = await fetch(`${API_BASE}/memories`);
        if (!response.ok) throw new Error('Memories fetch failed');
        const data = await response.json();
        
        const container = document.getElementById('memories-list');
        container.innerHTML = '';
        
        if (data.memories && data.memories.length > 0) {
            data.memories.forEach(mem => {
                const div = document.createElement('div');
                div.className = 'memory-item';
                div.textContent = mem.text;
                container.appendChild(div);
            });
        } else {
            container.innerHTML = '<div class="memory-item">No memories yet.</div>';
        }
    } catch (e) {
        console.error('Failed to refresh memories:', e);
    }
}

// ---------------------------------------------------------------------------
// Events Functions
// ---------------------------------------------------------------------------

async function refreshEvents() {
    try {
        const response = await fetch(`${API_BASE}/events`);
        if (!response.ok) throw new Error('Events fetch failed');
        const data = await response.json();
        
        const container = document.getElementById('events-list');
        container.innerHTML = '';
        
        if (data.rules && data.rules.length > 0) {
            data.rules.forEach(rule => {
                const div = document.createElement('div');
                div.className = 'event-item';
                div.innerHTML = `
                    <span class="event-status ${rule.enabled ? '' : 'disabled'}"></span>
                    <span><strong>${rule.name}</strong>: [${rule.event_type}] ${rule.condition} → ${rule.action}</span>
                `;
                container.appendChild(div);
            });
        } else {
            container.innerHTML = '<div class="event-item">No event rules configured.</div>';
        }
    } catch (e) {
        console.error('Failed to refresh events:', e);
    }
}

// ---------------------------------------------------------------------------
// Status Functions
// ---------------------------------------------------------------------------

function updateStatus(state, text) {
    const badge = document.getElementById('status-badge');
    badge.textContent = text;
    badge.className = `status-badge ${state}`;
}

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    refreshStats();
    refreshActivity();
    refreshMemories();
    refreshEvents();
    
    // Auto-refresh every 30 seconds
    setInterval(refreshStats, 30000);
    setInterval(refreshActivity, 30000);
});
