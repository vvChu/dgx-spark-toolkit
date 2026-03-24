/**
 * SSE streaming chat API for real-time token delivery.
 *
 * Connects to POST /chat/stream and yields SSE events:
 * - type: "context" → search results
 * - type: "token"   → incremental text tokens
 * - type: "error"   → error message
 */
import { API_BASE, type ContextItem } from './api';

export interface StreamEvent {
  type: 'context' | 'token' | 'error';
  data: unknown;
}

/**
 * Send a streaming chat request via SSE.
 *
 * @param query - User query
 * @param language - Response language (vi/en)
 * @param onEvent - Callback for each SSE event
 * @param signal - Optional AbortSignal for cancellation
 */
export async function sendStreamChat(
  query: string,
  language: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, language }),
    signal,
  });

  if (!response.ok) {
    throw new Error(`Stream request failed: ${response.status}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('ReadableStream not supported');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Process complete SSE events (separated by \n\n)
    const events = buffer.split('\n\n');
    buffer = events.pop() || ''; // Keep incomplete last chunk

    for (const eventStr of events) {
      if (!eventStr.startsWith('data: ')) continue;
      const dataStr = eventStr.slice(6).trim();

      if (dataStr === '[DONE]') return;

      try {
        const parsed = JSON.parse(dataStr) as StreamEvent;
        onEvent(parsed);
      } catch {
        // Skip malformed events
      }
    }
  }
}
