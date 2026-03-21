#!/bin/bash
# Utility to check RAG Ingestion State
docker compose exec -T rag-service python3 -c "
from ingestion.state_manager import PostgresStateManager
from sqlalchemy import text
s = PostgresStateManager()
with s.engine.connect() as conn:
    res = conn.execute(text('SELECT status, count(*) FROM ingestion_state GROUP BY status ORDER BY count DESC'))
    print('\n🚀 RAG Ingestion State Summary:')
    print('='*30)
    for row in res:
        print(f' {row[0]:<12}: {row[1]}')
    
    print('\n🕒 Recent Activity (CLAIMED):')
    print('-'*30)
    recent = conn.execute(text(\"SELECT file_path, claim_timestamp, retry_count FROM ingestion_state WHERE status = 'CLAIMED' ORDER BY claim_timestamp DESC LIMIT 5\"))
    for r in recent:
        print(f' Path: {r[0][:50]}...')
        print(f' Time: {r[1]} | Retries: {r[2]}')
        print('-'*15)
"
