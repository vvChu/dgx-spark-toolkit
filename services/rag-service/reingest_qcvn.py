"""
Targeted re-ingest: reset only QCVN + technical standard docs to PENDING.
These are the docs that benefit most from table reconstruction fix.
Only reset docs that contain 'QCVN', 'TCVN', 'TCXDVN', 'QTKD', 'QC_' in path.
"""
import sys; sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
import os

db_url = os.environ['DATABASE_URL']
engine = create_engine(db_url, pool_pre_ping=True)

TECHNICAL_PATTERNS = ['QCVN', 'TCVN', 'TCXDVN', 'QTKD', 'Quy chuan']

with engine.begin() as conn:
    # Find COMPLETED technical docs
    result = conn.execute(text("""
        SELECT file_path FROM ingestion_state
        WHERE status = 'COMPLETED'
    """))
    all_completed = [row[0] for row in result.fetchall()]

    technical = [p for p in all_completed
                 if any(pat.lower() in p.lower() for pat in TECHNICAL_PATTERNS)]

    print(f"Total COMPLETED: {len(all_completed)}")
    print(f"Technical docs to re-ingest: {len(technical)}")

    # Show sample
    print("\nSample (first 10):")
    for p in technical[:10]:
        print(f"  {p.split('/')[-1][:70]}")

    # Reset them to PENDING
    for path in technical:
        conn.execute(text("""
            UPDATE ingestion_state
            SET status = 'PENDING', updated_at = NOW()
            WHERE file_path = :fp
        """), {"fp": path})

    print(f"\nReset {len(technical)} technical docs to PENDING.")

# Final count
with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT status, COUNT(*) FROM ingestion_state GROUP BY status ORDER BY status"
    ))
    print("\nFinal status:")
    for row in result:
        print(f"  {row[0]:12s}: {row[1]}")
