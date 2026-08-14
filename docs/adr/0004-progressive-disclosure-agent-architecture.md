# 0004. Progressive Disclosure Agent Architecture

Adopted a progressive disclosure documentation architecture for AI coding agents, replacing the monolithic 166-line root `CLAUDE.md` with a minimal `<30` line `AGENTS.md` (symlinked from `CLAUDE.md`) that references modular topic files in `docs/` and delegates operational procedures to Agent Skills and Workflows.

## Status
Accepted

## Context
As the repository grew, `CLAUDE.md` accumulated detailed instructions across multiple domains (9-stage ingestion pipeline, architecture diagrams, CI jobs, linting rules, database schema, and common pitfalls). This monolithic file consumed a significant portion of the LLM's instruction budget on every conversation turn, increasing prompt latency, token costs, and the risk of instruction drift or confusion during unrelated tasks.

## Decision
1. Established root `AGENTS.md` as the canonical entrypoint containing only the project scope description, essential quick commands, and progressive markdown links to detailed documentation.
2. Created a symlink `CLAUDE.md -> AGENTS.md` to maintain full compatibility across Claude Code, Antigravity, and other agent tools.
3. Decomposed detailed documentation into modular files under `docs/`: `ARCHITECTURE.md`, `DEVELOPMENT.md`, `CONVENTIONS.md`, and `PITFALLS.md`.
4. Enforced strict domain boundaries: `CONTEXT.md` serves strictly as the ubiquitous language glossary, `docs/adr/` captures irreversible architectural decisions, and operational runbooks are delegated to Agent Skills (`.agents/skills/`) and Workflows (`.agents/workflows/`).

## Consequences
- **Instruction Budget Optimization**: Every agent interaction begins with a lightweight context (<200 tokens) rather than 8KB+ of static guidance.
- **Maintainability**: Domain-specific guidance can be updated independently without risking regressions or noise in unrelated agent sessions.
- **Discoverability**: Agents follow standard markdown file links just-in-time when executing domain-specific tasks.
