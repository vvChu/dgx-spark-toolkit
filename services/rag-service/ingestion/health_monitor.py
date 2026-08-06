import os
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from datetime import datetime, timedelta


def monitor():
    conn_str = os.getenv("POSTGRES_URL")
    if not conn_str:
        raise RuntimeError(
            "POSTGRES_URL environment variable is required. "
            "Example: postgresql://user:password@host:5432/dbname"
        )

    conn = None
    try:
        conn = psycopg2.connect(conn_str)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        while True:
            cur.execute("SELECT status, count(*) FROM ingestion_state GROUP BY status;")
            stats = {row['status']: row['count'] for row in cur.fetchall()}

            total = sum(stats.values())
            completed = stats.get('COMPLETED', 0)
            pending = stats.get('PENDING', 0)
            failed = stats.get('FAILED', 0)
            claimed = stats.get('CLAIMED', 0)

            progress = (completed / total * 100) if total > 0 else 0

            # Estimate completion time
            # We assume 5 workers are active.
            # Let's get the number of COMPLETED in the last 5 minutes to estimate rate.
            cur.execute("SELECT count(*) FROM ingestion_state WHERE status = 'COMPLETED' AND updated_at > NOW() - INTERVAL '5 minutes';")
            recent_completed = cur.fetchone()['count']

            rate_per_min = recent_completed / 5
            remaining_mins = (pending + claimed) / rate_per_min if rate_per_min > 0 else 0
            etc = datetime.now() + timedelta(minutes=remaining_mins) if remaining_mins > 0 else "Unknown"

            os.system('clear')
            print("="*60)
            print(f" RAG INGESTION HEALTH MONITOR | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
            print(f" TOTAL DOCUMENTS : {total}")
            print(f" COMPLETED       : {completed} ({progress:.2f}%)")
            print(f" PENDING         : {pending}")
            print(f" CLAIMED         : {claimed} (Workers active)")
            print(f" FAILED          : {failed}")
            print("-" * 60)
            print(f" RATE (Last 5m)  : {rate_per_min:.2f} docs/min")
            print(f" EST. COMPLETION : {etc}")
            print("="*60)
            print("\nLatest Completed Files (Namespaced IDs):")
            cur.execute("SELECT doc_id, file_path FROM ingestion_state WHERE status = 'COMPLETED' ORDER BY updated_at DESC LIMIT 5;")
            for row in cur.fetchall():
                print(f" - [{row['doc_id']}] {os.path.basename(row['file_path'])}")

            time.sleep(30)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    monitor()
