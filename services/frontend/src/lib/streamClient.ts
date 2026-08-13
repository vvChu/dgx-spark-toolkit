/**
 * Deep StreamClient module for Server-Sent Events (SSE) chat streaming.
 */
import { API_BASE, sendChat, type ContextItem, type ChatResponse } from './api';

export interface StreamContextEvent {
  type: 'context';
  data: ContextItem[];
}

export interface StreamTokenEvent {
  type: 'token';
  data: string;
}

export interface StreamThoughtEvent {
  type: 'thought';
  data: string;
}

export interface StreamErrorEvent {
  type: 'error';
  data: string;
}

export type StreamEvent = StreamContextEvent | StreamTokenEvent | StreamThoughtEvent | StreamErrorEvent;

export interface StreamChatOptions {
  query: string;
  language: string;
  onContext?: (items: ContextItem[]) => void;
  onToken?: (token: string) => void;
  onThought?: (thought: string) => void;
  onError?: (error: string) => void;
  signal?: AbortSignal;
  maxRetries?: number;
  retryDelayMs?: number;
}

export interface StreamResult {
  fallbackUsed: boolean;
  tokensReceived: number;
  thoughtsReceived: number;
  contextCount: number;
}

export class StreamClient {
  /**
   * Execute SSE streaming chat with automatic event parsing, exponential backoff reconnection,
   * Last-Event-ID header tracking, and REST fallback.
   * Returns execution statistics (fallback status, token counts, context items).
   */
  static async streamChat(options: StreamChatOptions): Promise<StreamResult> {
    const { query, language, onContext, onToken, onThought, onError, signal } = options;
    const maxRetries = options.maxRetries ?? 3;
    const initialDelay = options.retryDelayMs ?? 500;

    let tokensReceived = 0;
    let thoughtsReceived = 0;
    let contextCount = 0;
    let fallbackUsed = false;
    let lastEventId: string | null = null;
    let attempt = 0;

    while (attempt < maxRetries) {
      try {
        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        if (lastEventId) {
          headers['Last-Event-ID'] = lastEventId;
        }

        const response = await fetch(`${API_BASE}/chat/stream`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ query, language }),
          signal,
        });

        if (!response.ok) {
          throw new Error(`Stream request failed with status: ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) throw new Error('ReadableStream not supported by browser environment.');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const events = buffer.split('\n\n');
          buffer = events.pop() || '';

          for (const eventStr of events) {
            const lines = eventStr.split('\n');
            let dataStr = '';
            for (const line of lines) {
              if (line.startsWith('id: ')) {
                lastEventId = line.slice(4).trim();
              } else if (line.startsWith('data: ')) {
                dataStr = line.slice(6).trim();
              }
            }

            if (!dataStr) continue;

            if (dataStr === '[DONE]') {
              return { fallbackUsed, tokensReceived, thoughtsReceived, contextCount };
            }

            try {
              const parsed = JSON.parse(dataStr) as StreamEvent;
              if (parsed.type === 'context' && onContext) {
                const items = parsed.data as ContextItem[];
                contextCount = items.length;
                onContext(items);
              } else if (parsed.type === 'token' && onToken) {
                tokensReceived++;
                onToken(parsed.data as string);
              } else if (parsed.type === 'thought' && onThought) {
                thoughtsReceived++;
                onThought(parsed.data as string);
              } else if (parsed.type === 'error' && onError) {
                onError(parsed.data as string);
              }
            } catch {
              // Ignore malformed JSON chunks
            }
          }
        }
        return { fallbackUsed, tokensReceived, thoughtsReceived, contextCount };
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          throw err;
        }
        attempt++;
        if (attempt < maxRetries) {
          const delay = initialDelay * Math.pow(2, attempt - 1);
          console.warn(`SSE stream connection attempt ${attempt}/${maxRetries} failed. Retrying in ${delay}ms...`, err);
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      }
    }

    // Transparent REST fallback after retries exhausted
    try {
      fallbackUsed = true;
      console.warn('SSE stream connection retries exhausted, executing transparent REST fallback.');
      const restData: ChatResponse = await sendChat(query, language);
      if (restData.context && onContext) {
        contextCount = restData.context.length;
        onContext(restData.context);
      }
      if (restData.thought && onThought) {
        thoughtsReceived++;
        onThought(restData.thought);
      }
      if (restData.answer && onToken) {
        tokensReceived++;
        onToken(restData.answer);
      }
      return { fallbackUsed, tokensReceived, thoughtsReceived, contextCount };
    } catch (restErr) {
      if (onError) {
        onError(`Chat request failed: ${(restErr as Error).message}`);
      }
      return { fallbackUsed, tokensReceived, thoughtsReceived, contextCount };
    }
  }
}
