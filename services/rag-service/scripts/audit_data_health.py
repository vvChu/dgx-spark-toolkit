import os
import time
import logging
from pymilvus import connections, Collection, utility
from neo4j import GraphDatabase
import hashlib

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants (matching production_ingest.py)
SOURCE_DIR = "/app/data/legal_docs_source"
from core.config import get_settings
settings = get_settings()
MILVUS_COLLECTION = settings.MILVUS_COLLECTION
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASS", "password123")

class RAGAuditTool:
    def __init__(self):
        self.connect_milvus()
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
    def connect_milvus(self):
        try:
            connections.connect(host='milvus-standalone', port='19530')
            if utility.has_collection(MILVUS_COLLECTION):
                self.collection = Collection(MILVUS_COLLECTION)
                self.collection.load()
            else:
                logger.error(f"Collection {MILVUS_COLLECTION} not found!")
                self.collection = None
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            self.collection = None

    def get_file_id(self, file_path):
        # Quick ID: Size + Filename Hash to avoid reading 8K+ files
        size = os.path.getsize(file_path)
        name = os.path.basename(file_path)
        return hashlib.md5(f"{name}_{size}".encode()).hexdigest()

    def run_audit(self):
        logger.info("=== Starting RAG Data Audit (QUICK MODE) ===")
        
        # 1. Scan Source Directory
        source_files = {}
        for root, _, files in os.walk(SOURCE_DIR):
            for file in files:
                if file.lower().endswith('.pdf'):
                    path = os.path.join(root, file)
                    f_id = self.get_file_id(path)
                    source_files[f_id] = file

        logger.info(f"Found {len(source_files)} files in source directory.")

        # 2. Query Neo4j
        neo4j_files = {}
        with self.neo4j_driver.session() as session:
            result = session.run("MATCH (f:File) RETURN f.id as id, f.status as status, f.path as path, f.file_name as name")
            for record in result:
                neo4j_files[record["id"]] = {"status": record["status"], "name": record["name"]}
        
        logger.info(f"Found {len(neo4j_files)} file records in Neo4j.")

        # 3. Query Milvus (Grouping by file_hash)
        milvus_stats = {}
        if self.collection:
            try:
                # Optimized way: use query to get all unique file_hashes
                # For audit, we'll fetch entries in batches if needed, but for now 
                # we assume a reasonable number of chunks (< 100k)
                res = self.collection.query(expr="id >= 0", output_fields=["file_hash"], limit=16384)
                for entry in res:
                    f_hash = entry["file_hash"]
                    milvus_stats[f_hash] = milvus_stats.get(f_hash, 0) + 1
            except Exception as e:
                logger.error(f"Error querying Milvus: {e}")

        logger.info(f"Found {len(milvus_stats)} files with data in Milvus.")

        # 4. Analysis
        print("\n--- AUDIT REPORT ---")
        print(f"{'File Name':<50} | {'Hashes':<32} | {'Neo4j':<10} | {'Milvus':<8}")
        print("-" * 110)
        
        missing_in_neo4j = []
        missing_in_milvus = []
        stuck_files = []
        consistent_count = 0

        for f_hash, name in source_files.items():
            n4j = neo4j_files.get(f_hash, {}).get("status", "MISSING")
            m_count = milvus_stats.get(f_hash, 0)
            
            print(f"{name[:50]:<50} | {f_hash} | {n4j:<10} | {m_count:<8}")
            
            if n4j == "MISSING":
                missing_in_neo4j.append(name)
            elif n4j != "DONE":
                stuck_files.append((name, n4j))
            
            if m_count == 0:
                missing_in_milvus.append(name)
            else:
                if n4j == "DONE":
                    consistent_count += 1

        print("\n--- SUMMARY ---")
        print(f"Total Source Files:    {len(source_files)}")
        print(f"Consistent (Synced):   {consistent_count}")
        print(f"Missing in Neo4j:      {len(missing_in_neo4j)}")
        print(f"Missing in Milvus:     {len(missing_in_milvus)}")
        print(f"Stuck/Error Status:    {len(stuck_files)}")
        
        if missing_in_milvus:
            print("\nWARNING: Files with NO vector data:")
            for m in missing_in_milvus:
                print(f" - {m}")

        if stuck_files:
            print("\nSTUCK/INCOMPLETE Files:")
            for name, status in stuck_files:
                print(f" - {name}: {status}")

    def close(self):
        self.neo4j_driver.close()

if __name__ == "__main__":
    audit = RAGAuditTool()
    try:
        audit.run_audit()
    finally:
        audit.close()
