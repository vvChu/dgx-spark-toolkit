#!/bin/bash
# Quick baseline: run comprehensive audit inside Docker
cd /home/vvc/Codebase/dgx-spark-toolkit
docker compose exec -T rag-service python3 comprehensive_audit.py 2>&1 | tee /home/vvc/Codebase/dgx-spark-toolkit/services/rag-service/audit_results/baseline.txt
