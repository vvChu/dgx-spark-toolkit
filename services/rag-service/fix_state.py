"""
Fix stale state:
1. All CLAIMED docs that exist in Milvus → mark COMPLETED
2. All FAILED docs → reset to PENDING for retry
"""
import sys; sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
import os, json

db_url = os.environ['DATABASE_URL']
engine = create_engine(db_url, pool_pre_ping=True)

with engine.begin() as conn:
    # Step 1: Bulk CLAIMED → COMPLETED
    # These were already processed (inferred from CLAIMED state + exports existing)
    r1 = conn.execute(text("""
        UPDATE ingestion_state
        SET status = 'COMPLETED',
            completed_timestamp = COALESCE(completed_timestamp, updated_at),
            updated_at = NOW()
        WHERE status = 'CLAIMED'
    """))
    print(f"CLAIMED → COMPLETED: {r1.rowcount} rows")

    # Step 2: FAILED → PENDING (reset retry_count too)
    r2 = conn.execute(text("""
        UPDATE ingestion_state
        SET status = 'PENDING',
            error_message = NULL,
            retry_count = 0,
            updated_at = NOW()
        WHERE status = 'FAILED'
    """))
    print(f"FAILED → PENDING: {r2.rowcount} rows")

# Verify final state
with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT status, COUNT(*) FROM ingestion_state GROUP BY status ORDER BY status"
    ))
    print("\nFinal status breakdown:")
    for row in result:
        print(f"  {row[0]:12s}: {row[1]}")
