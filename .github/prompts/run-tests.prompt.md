---
description: "Run backend pytest for the file being edited or a specific test module"
agent: "agent"
argument-hint: "test file or module name (optional — auto-detects from active file)"
---
Run backend tests for the RAG service.

## Steps
1. Determine the test target:
   - If the user specifies a file, use it directly
   - If the active file is in `services/rag-service/tests/`, run that file
   - If the active file is `services/rag-service/X.py`, look for `tests/test_X.py`
   - Otherwise, run all tests
2. Run from the `services/rag-service/` directory:
   ```
   cd services/rag-service && pytest {target} -v --timeout=60
   ```
3. Summarize results: passes, failures, and any error details
4. If tests fail, suggest fixes based on the failure output
