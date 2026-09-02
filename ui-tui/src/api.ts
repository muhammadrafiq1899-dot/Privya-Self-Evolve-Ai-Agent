const API_BASE = process.env.PRIVYA_API || 'http://127.0.0.1:8000';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
}

export interface ChatResponse {
  response: string;
  tools_used: string[];
  reflected: boolean;
  duration: number;
}

export interface Stats {
  memories: number;
  procedures: number;
  tools_count: number;
  requests: number;
  provider: string;
  uptime: string;
}

export interface Provider {
  id: string;
  display_name: string;
  available: boolean;
  default_model: string;
  key_env: string;
  models: { id: string; name: string; description: string }[];
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, reflection: true }),
  });
  if (!res.ok) throw new Error(`Chat failed: ${res.status}`);
  return res.json();
}

export async function getStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/api/stats`);
  return res.json();
}

export async function getMemories(): Promise<{ memories: any[] }> {
  const res = await fetch(`${API_BASE}/api/memories`);
  return res.json();
}

export async function getProviders(): Promise<{ providers: Provider[] }> {
  // Use the Python backend's provider info
  const res = await fetch(`${API_BASE}/api/stats`);
  const stats = await res.json();
  return { providers: [] }; // Extended by model picker
}

export async function getCron(): Promise<{ jobs: any[] }> {
  const res = await fetch(`${API_BASE}/api/cron`);
  return res.json();
}

export async function getEvents(): Promise<any> {
  const res = await fetch(`${API_BASE}/api/events`);
  return res.json();
}

export async function getSnapshots(): Promise<any> {
  const res = await fetch(`${API_BASE}/api/git/snapshots`);
  return res.json();
}
