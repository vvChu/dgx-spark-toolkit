"""Reset QCVN_113 status via direct psycopg2 and restart rag-watcher scan."""
import sys, os
import psycopg2

# Get DB connection from env
db_host = os.environ.get('POSTGRES_HOST', 'postgres-state')
db_port = os.environ.get('POSTGRES_PORT', '5432')
db_name = os.environ.get('POSTGRES_DB', 'ragdb')
db_user = os.environ.get('POSTGRES_USER', 'raguser')
db_pass = os.environ.get('POSTGRES_PASSWORD', '')

print(f"Connecting to {db_host}:{db_port}/{db_name}")
conn = psycopg2.connect(
    host=db_host, port=db_port, dbname=db_name,
    user=db_user, password=db_pass
)
cur = conn.cursor()

rel_path = 'VB phap quy/Linh vuc_BXD-GTVT/Quy chuan BGTVT ban hanh/QCVN 113-2023-BGTVT_Ve phuongphapthuvanhbanhmoto-ganmay.pdf'

# Check current status
cur.execute("SELECT status, updated_at FROM ingestion_state WHERE file_path = %s", (rel_path,))
row = cur.fetchone()
print(f"Current: status={row[0] if row else 'NOT FOUND'}, updated={row[1] if row else 'N/A'}")

# Reset to PENDING
cur.execute(
    "UPDATE ingestion_state SET status = 'PENDING', error_message = NULL, updated_at = NOW() WHERE file_path = %s",
    (rel_path,)
)
affected = cur.rowcount
conn.commit()
print(f"Updated {affected} row(s) — status=PENDING")
conn.close()
print("Done. rag-watcher will pick up on next scan.")
