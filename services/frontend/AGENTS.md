# Frontend (services/frontend)

Single-Page Application (SPA) built with React 19, Vite 7, and Tailwind CSS 4 for legal document search, interactive chat, and graph visualization.

## Quick Commands
- **Lint**: `cd services/frontend && npm run lint`
- **Typecheck**: `npm run typecheck`
- **Build**: `NODE_OPTIONS="--max-old-space-size=4096" npm run build`
- **Dev Server**: `npm run dev` (runs on `:5173`)

## Directory Structure & Seams
- `src/components/`: Modular UI widgets (Chat, DocumentViewer, KnowledgeGraph, Stats, SearchBar).
- `src/lib/api.ts`: Typed REST client interfacing with RAG Service (`:8005`).
- `src/lib/streamClient.ts`: Resilient SSE client for real-time streaming LLM responses.
- `src/hooks/`: Custom hooks for state management, query caching, and hotkeys.

## Build & Code Quality Invariants
- **Vite Manual Chunks**: Vendor packages (`react`, `react-dom`, `lucide-react`, `react-force-graph-2d`) are separated into discrete chunks to keep bundles < 300 kB.
- **AnimatePresence Keying**: Every child element inside `<AnimatePresence mode="wait">` must define a unique `key`.
- **Node Memory Ceiling**: Production builds require `--max-old-space-size=4096` to prevent OOM during compilation.
