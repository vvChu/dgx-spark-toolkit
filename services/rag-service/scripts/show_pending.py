"""Show what the 14 PENDING (previously FAILED) docs are."""
import sys
sys.path.insert(0, '/app')
from sqlalchemy import create_engine, text
import os

db_url = os.environ['DATABASE_URL']
engine = create_engine(db_url, pool_pre_ping=True)

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT file_path, retry_count
        FROM ingestion_state
        WHERE status = 'PENDING'
        ORDER BY file_path
    """))
    rows = result.fetchall()
    print(f"14 PENDING docs (prev FAILED):")
    for i, row in enumerate(rows, 1):
        name = row[0].split('/')[-1][:70]
        print(f"  {i:2d}. {name}")

print(f"\nTotal PENDING: {len(rows)}")
