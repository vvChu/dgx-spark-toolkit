---
description: "Run smoke test and RAG quality audit against running services, then summarize results"
agent: "agent"
---
Run the smoke test and comprehensive RAG audit against the running service stack.

## Steps
1. Run smoke test:
   ```
   python3 services/rag-service/scripts/smoke_test.py
   ```
2. If smoke test passes, run the quality audit:
   ```
   python3 services/rag-service/scripts/comprehensive_audit.py
   ```
3. Summarize findings:
   - Service health status (which services are up/down)
   - Audit scores and any P1/P2 issues
   - Suggested remediation for failures

**Note**: Requires the full Docker Compose stack to be running (`./scripts/start-all.sh`).
