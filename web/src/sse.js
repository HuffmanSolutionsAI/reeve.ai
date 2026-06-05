// POST /api/chat returns Server-Sent Events. EventSource can't POST, so we
// fetch the stream and parse the SSE framing by hand. `handlers` is keyed by
// event type; a '*' handler (if provided) receives every event.
export async function streamChat(body, handlers) {
  const resp = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
  });
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
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = 'message';
      let data = '';
      for (const line of raw.split('\n')) {
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
