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

export class StreamClient {
  /**
   * Execute SSE streaming chat with automatic event parsing and REST fallback.
   */
  static async streamChat(options: StreamChatOptions): Promise<void> {
    const { query, language, onContext, onToken, onThought, onError, signal } = options;

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

          if (dataStr === '[DONE]') return;

          try {
            const parsed = JSON.parse(dataStr) as StreamEvent;
            if (parsed.type === 'context' && onContext) {
              onContext(parsed.data as ContextItem[]);
            } else if (parsed.type === 'token' && onToken) {
              onToken(parsed.data as string);
            } else if (parsed.type === 'thought' && onThought) {
              onThought(parsed.data as string);
            } else if (parsed.type === 'error' && onError) {
              onError(parsed.data as string);
            }
          } catch {
            // Ignore malformed JSON chunks
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        throw err;
      }
      // Execute fallback REST chat call
      console.warn('SSE stream connection failed, executing REST fallback:', err);
      const restData: ChatResponse = await sendChat(query, language);
      if (restData.context && onContext) {
        onContext(restData.context);
      }
      if (restData.thought && onThought) {
        onThought(restData.thought);
      }
      if (restData.answer && onToken) {
        onToken(restData.answer);
      }
    }
  }
}
