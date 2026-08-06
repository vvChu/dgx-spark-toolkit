#!/bin/bash
# Lint only staged Python files in rag-service
STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep '^services/rag-service/.*\.py$')
if [ -z "$STAGED" ]; then
  exit 0
fi
flake8 $STAGED --max-line-length=150 --exclude=venv,__pycache__,surya_src 2>&1
