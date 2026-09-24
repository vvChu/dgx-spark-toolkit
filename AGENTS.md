# dgx-spark-toolkit

Vietnamese legal document RAG system running on NVIDIA DGX Spark (GB10 Blackwell, 128GB unified memory) with unified AI Gateway, FastAPI backend, and React 19 frontend.

## Quick Commands
- **Backend Tests**: `cd services/rag-service && pytest tests/` (see [DEVELOPMENT.md](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/DEVELOPMENT.md))
- **Frontend**: `cd services/frontend && npm run lint && npm run typecheck && npm run build`
- **Lint**: `flake8 services/rag-service/ --config=services/rag-service/.flake8`
- **Ops Workflows**: Use agent slash commands (`/start-all`, `/health`, `/vllm-32k`, `/track-ingestion`)

## Progressive Documentation
- [Architecture & Services](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/ARCHITECTURE.md) — Topology, 9-stage ingestion, databases, Docker profiles
- [Code Conventions](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/CONVENTIONS.md) — Python style, identity model (`doc_id`, `chunk_id`), API patterns
- [Development & CI](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/DEVELOPMENT.md) — Test setup, environment variables, GitHub Actions
- [Common Pitfalls](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/PITFALLS.md) — Critical gotchas, Redis DB split, CI constraints
- [Domain Model](file:///home/vvc/Codebase/dgx-spark-toolkit/CONTEXT.md) — Ubiquitous language & entity definitions
- [Architectural Decisions](file:///home/vvc/Codebase/dgx-spark-toolkit/docs/adr/) — ADR records
