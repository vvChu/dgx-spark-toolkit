"""Full database reset script — wipes Milvus, Neo4j, PostgreSQL state, and exports."""
import sys
sys.path.insert(0, '/app')
import os
import glob
import shutil
from pymilvus import connections, utility, Collection
from neo4j import GraphDatabase
from sqlalchemy import create_engine, text
from core.config import get_settings

s = get_settings()
print("=" * 55)
print("FULL DATABASE RESET")
print("=" * 55)

# 1. Milvus — drop collection
print("\n[1] Milvus — dropping collection...")
connections.connect(host=s.MILVUS_HOST, port=str(s.MILVUS_PORT))
coll_name = s.MILVUS_COLLECTION
if utility.has_collection(coll_name):
    coll = Collection(coll_name)
    coll.drop()
    print(f"    ✓ Collection '{coll_name}' dropped")
else:
    print(f"    - Collection '{coll_name}' not found (already clean)")

# Also drop cache collection if exists
cache_name = coll_name + "_cache"
if utility.has_collection(cache_name):
    Collection(cache_name).drop()
    print(f"    ✓ Cache collection '{cache_name}' dropped")

# 2. Neo4j — delete all nodes and relationships
print("\n[2] Neo4j — deleting all nodes and relationships...")
neo4j_uri = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
neo4j_user = os.getenv("NEO4J_USER", "neo4j")
neo4j_pass = os.getenv("NEO4J_PASSWORD") or os.getenv("NEO4J_PASS", "")
try:
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    with driver.session() as session:
        result = session.run("MATCH (n) DETACH DELETE n RETURN count(n) as deleted")
        deleted = result.single()["deleted"]
        print(f"    ✓ Deleted {deleted} nodes (all relationships included)")
    driver.close()
except Exception as e:
    print(f"    ✗ Neo4j error: {e}")

# 3. PostgreSQL — reset ingestion_state to PENDING
print("\n[3] PostgreSQL — resetting ingestion_state...")
db_url = os.environ.get('DATABASE_URL')
engine = create_engine(db_url, pool_pre_ping=True)
with engine.begin() as conn:
    # Count before
    before = conn.execute(text("SELECT status, COUNT(*) FROM ingestion_state GROUP BY status ORDER BY status")).fetchall()
    print(f"    Before: {dict(before)}")

    # Reset all to PENDING
    conn.execute(text("""
        UPDATE ingestion_state
        SET status = 'PENDING',
            updated_at = NOW(),
            completed_timestamp = NULL,
            content_hash = ''
    """))

    after = conn.execute(text("SELECT status, COUNT(*) FROM ingestion_state GROUP BY status ORDER BY status")).fetchall()
    print(f"    After:  {dict(after)}")
    print(f"    ✓ All {dict(after).get('PENDING', 0)} docs reset to PENDING")

print("\n[4] Done. Restart rag-service and rag-watchers to begin fresh ingestion.")
print("    The pipeline will recreate Milvus collection automatically on first run.")
print("=" * 55)
