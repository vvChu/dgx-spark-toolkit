# T-02: Refactor useChat hook to delegate to StreamClient

## Status
Open

## Blocking
Blocked by T-01

## Objective
Refactor `services/frontend/src/hooks/useChat.ts` to delegate stream connection, token accumulation, reasoning path updates, and REST fallback to `StreamClient`.

## Verification
- `useChat` hook is concise and delegates stream operations.
