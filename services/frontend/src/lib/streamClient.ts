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
}

export interface StreamResult {
  fallbackUsed: boolean;
  tokensReceived: number;
  thoughtsReceived: number;
  contextCount: number;
}

export class StreamClient {
  /**
   * Execute SSE streaming chat with automatic event parsing and REST fallback.
   * Returns execution statistics (fallback status, token counts, context items).
   */
  static async streamChat(options: StreamChatOptions): Promise<StreamResult> {
    const { query, language, onContext, onToken, onThought, onError, signal } = options;
    let tokensReceived = 0;
    let thoughtsReceived = 0;
    let contextCount = 0;
    let fallbackUsed = false;

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
          if (!eventStr.startsWith('data: ')) continue;
          const dataStr = eventStr.slice(6).trim();

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
      fallbackUsed = true;
      console.warn('SSE stream connection failed, executing transparent REST fallback:', err);
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
    }
  }
}
