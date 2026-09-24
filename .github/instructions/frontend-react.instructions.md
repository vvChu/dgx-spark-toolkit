---
description: "Use when editing React frontend code: components, hooks, API clients, styling with Tailwind CSS."
applyTo: "services/frontend/**/*.{ts,tsx}"
---
# Frontend React Conventions

## Architecture
- **Hooks-first**: Business logic in `src/hooks/` (`useChat`, `useCompliance`, `useDashboard`, `useBenchmark`, `useEvaluation`)
- **Components** in `src/components/`, reusable atoms in `src/components/ui/`
- **API layer** in `src/lib/`: `api.ts` (REST via axios) + `streamClient.ts` (SSE streaming with auto fallback)

## Patterns

### Data fetching
- SSE streaming for chat: use `StreamClient.streamChat()` from `lib/streamClient.ts`
- HTTP POST fallback for non-streaming: use functions from `lib/api.ts`
- Base URL from `VITE_API_URL` env var — never hardcode backend URLs

### Components
- Functional components only, no class components
- Custom hooks for state + side effects — keep components as thin presentational wrappers
- `ErrorBoundary` for top-level error handling

### Styling
- **Tailwind CSS 4** utility-first — no component library (no MUI, no Ant Design)
- No CSS modules or styled-components — Tailwind only
- Animations via `framer-motion`, icons via `lucide-react`

### Visualization
- Knowledge graph: `react-force-graph-2d`
- Markdown rendering in chat: `react-markdown` + `remark-gfm`

## Stack
React 19, Vite 7, TypeScript 5.9. No test runner — validate via `npm run lint && npm run typecheck && npm run build`.
