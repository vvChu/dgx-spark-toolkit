/**
 * Backward compatibility wrapper delegating to StreamClient.
 */
import { StreamClient, type StreamEvent } from './streamClient';

export type { StreamEvent };

export async function sendStreamChat(
  query: string,
  language: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await StreamClient.streamChat({
    query,
    language,
    onContext: (context) => onEvent({ type: 'context', data: context }),
    onToken: (token) => onEvent({ type: 'token', data: token }),
    onThought: (thought) => onEvent({ type: 'thought', data: thought }),
    onError: (error) => onEvent({ type: 'error', data: error }),
    signal,
  });
}
