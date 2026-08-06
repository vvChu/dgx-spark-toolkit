# Technical Spec: Frontend Stream Client & State Refactoring

## 1. Overview & Goal

Consolidate manual SSE buffer decoding and stream error handling from `services/frontend/src/lib/streamApi.ts` and `services/frontend/src/hooks/useChat.ts` into a deep `StreamClient` module at `services/frontend/src/lib/streamClient.ts`.

## 2. Architecture & Seams

### Discriminated Union Event Types (`services/frontend/src/lib/streamClient.ts`)

```typescript
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
```

### `StreamClient` Class Seam

```typescript
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
  static async streamChat(options: StreamChatOptions): Promise<void>;
}
```

## 3. Tickets & Execution Plan

1. **`T-01`**: Create `StreamClient` in `services/frontend/src/lib/streamClient.ts` with typed SSE event handlers and automatic REST fallback support. Update `streamApi.ts` for backward compatibility.
2. **`T-02`**: Refactor `services/frontend/src/hooks/useChat.ts` to delegate streaming and reasoning path updates to `StreamClient`.
3. **`T-03`**: Update `services/frontend/src/components/ChatPanel.tsx` to render streaming thoughts and reasoning path indicators cleanly. Verify frontend build passes with `npm run build`.
