---
name: audit
description: Runs linters, tests, and security checks on the RAG service, then reports findings with suggested fixes.
---

# Audit Skill

Comprehensive code quality and security audit for the RAG service.

## Steps

### 1. Python Linting
```bash
flake8 services/rag-service/ --max-line-length=150 --exclude=venv,__pycache__,surya_src --statistics
```
Record any violations by category (E, W, F).

### 2. Backend Tests
```bash
cd services/rag-service && pytest tests/ -v --timeout=60 --tb=short
```
Record pass/fail counts and any failures.

### 3. Frontend Lint + Build
```bash
cd services/frontend && npm run lint 2>&1
cd services/frontend && npm run build 2>&1
```
Record any ESLint errors or build failures.

### 4. Security Scan
Search for common security issues in the RAG service:

```
grep -rn "password\s*=" services/rag-service/ --include="*.py" | grep -v "test" | grep -v "__pycache__" | grep -v ".pyc"
grep -rn "secret.*=.*['\"]" services/rag-service/ --include="*.py" | grep -v "test" | grep -v "__pycache__"
grep -rn "get_secret_value()" services/rag-service/ --include="*.py" | grep -v "__pycache__"
```
Flag any hardcoded credentials or leaked secret values (calls to `get_secret_value()` in log/print statements).

### 5. Report
Output a structured report:
```
=== Audit Report ===
Linting:   X violations (E: _, W: _, F: _)
Tests:     X passed, Y failed
Frontend:  lint OK/FAIL, build OK/FAIL
Security:  X findings

[Details of any failures or security findings]
[Suggested fixes for each issue]
```
