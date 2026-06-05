import { authHeaders, clearSession } from './auth.js';

// POST /api/chat returns Server-Sent Events. EventSource can't POST, so we
// fetch the stream and parse the SSE framing by hand. `handlers` is keyed by
// event type; a '*' handler (if provided) receives every event.
export async function streamChat(body, handlers) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...authHeaders(),
    },
    body: JSON.stringify(body),
  });
  if (resp.status === 401) { clearSession(); window.location.reload(); throw new Error('unauthorized'); }
  if (!resp.ok) {
    const detail = await resp.text().catch(() => '');
    throw new Error(`chat failed: ${resp.status} ${detail}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf('\n\n')) !== -1 || (idx = buffer.indexOf('\r\n\r\n')) !== -1) {
      const end = idx;
      const sep = buffer.slice(end, end + 4) === '\r\n\r\n' ? 4 : 2;
      const raw = buffer.slice(0, end);
      buffer = buffer.slice(end + sep);
      let event = 'message';
      let data = '';
      for (const line of raw.replace(/\r/g, '').split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        else if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      let parsed = {};
      try { parsed = data ? JSON.parse(data) : {}; } catch { parsed = { raw: data }; }
      if (handlers[event]) handlers[event](parsed);
      if (handlers['*']) handlers['*'](event, parsed);
      if (event === 'done') return;
    }
  }
}

// /api/activity/stream is a WebSocket; browsers can't set Authorization on
// WebSocket handshakes, so the token rides in the query string.
export function openActivityStream({ token, onEvent, onError }) {
  if (!token) return () => {};
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${window.location.host}/api/activity/stream?token=${encodeURIComponent(token)}`;
  const ws = new WebSocket(url);
  ws.onmessage = (e) => {
    try { onEvent && onEvent(JSON.parse(e.data)); } catch (err) { /* ignore */ }
  };
  ws.onerror = (e) => onError && onError(e);
  return () => {
    try { ws.close(); } catch {}
  };
}
