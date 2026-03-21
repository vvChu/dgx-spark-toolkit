import os
import logging
import psycopg2
from pymilvus import connections, Collection
from neo4j import GraphDatabase
from core.config import get_settings

_settings = get_settings()

# Config
DB_URL = "postgresql://litellm:litellm_pwd@litellm-postgres:5432/litellm"
MILVUS_HOST = _settings.MILVUS_HOST
MILVUS_PORT = str(_settings.MILVUS_PORT)
MILVUS_COLLECTION = _settings.MILVUS_COLLECTION
NEO4J_URI = _settings.NEO4J_URI
NEO4J_USER = _settings.NEO4J_USER
NEO4J_PASS = _settings.NEO4J_PASSWORD.get_secret_value()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup():
    # 1. Connect to DB and find bad files
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    
    # Identify files with weak or hallucinated IDs
    cur.execute("""
        SELECT file_path, doc_id 
        FROM ingestion_state 
        WHERE status = 'COMPLETED' 
        AND (length(doc_id) < 5 OR doc_id ~ '^\\d+$' OR doc_id LIKE '%franklin%')
    """)
    bad_files = cur.fetchall()
    
    if not bad_files:
        logger.info("No contaminated files found.")
        return

    logger.info(f"Found {len(bad_files)} contaminated files. Starting cleanup...")

    # 2. Connect to Milvus
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    collection = Collection(MILVUS_COLLECTION)
    
    # 3. Connect to Neo4j
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    
    source_dir = "/app/data/legal_docs_source"

    import hashlib
    def get_file_hash(path):
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    for file_path, doc_id in bad_files:
        logger.info(f"Cleaning up: {file_path} (ID: {doc_id})")
        
        # A. Delete from Neo4j (using doc_id)
        if doc_id:
            with neo4j_driver.session() as session:
                session.run("MATCH (d:Document {id: $id}) DETACH DELETE d", id=doc_id)
                logger.info(f"  - Deleted Neo4j node {doc_id}")
        
        # B. Delete from Milvus (using calculated file_hash)
        full_path = os.path.join(source_dir, file_path)
        if os.path.exists(full_path):
            file_hash = get_file_hash(full_path)
            collection.delete(expr=f"file_hash == '{file_hash}'")
            logger.info(f"  - Deleted Milvus chunks for hash {file_hash}")
        else:
            logger.warning(f"  - File not found: {full_path}. Skipping Milvus cleanup for this item.")
        
        # C. Reset Postgres Status
        cur.execute("""
            UPDATE ingestion_state 
            SET status = 'PENDING', doc_id = NULL, error_message = 'Reset for re-indexing (Legal ID Refinement)'
            WHERE file_path = %s
        """, (file_path,))
        logger.info("  - Reset status to PENDING in Postgres")

    conn.commit()
    cur.close()
    conn.close()
    neo4j_driver.close()
    logger.info("Cleanup completed successfully.")

if __name__ == "__main__":
    cleanup()
