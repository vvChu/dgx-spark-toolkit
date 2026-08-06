# T-01: Implement Deep StreamClient & Type-Safe SSE Parsing

## Status
Open

## Blocking
None

## Objective
Implement `StreamClient` in `services/frontend/src/lib/streamClient.ts` providing typed SSE event streaming (`context`, `token`, `thought`, `error`) and robust buffer handling. Update `streamApi.ts` for backward compatibility.

## Verification
- `StreamClient` exports clean `streamChat` interface.
- TypeScript compiles without errors.
