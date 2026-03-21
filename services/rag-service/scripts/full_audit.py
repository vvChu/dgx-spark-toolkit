import os
import json
from pymilvus import connections,Collection
from neo4j import GraphDatabase
from core.config import get_settings

_settings = get_settings()
MILVUS_HOST = os.getenv("MILVUS_HOST", _settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", str(_settings.MILVUS_PORT))
COLLECTION_NAME = _settings.MILVUS_COLLECTION
NEO4J_URI = _settings.NEO4J_URI
NEO4J_USER = _settings.NEO4J_USER
NEO4J_PASS = _settings.NEO4J_PASSWORD.get_secret_value()
STATE_FILE = "ingestion_state.json"

print("--- Milvus Audit ---")
try:
    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
    col = Collection(COLLECTION_NAME)
    col.load()
    print(f"Total entities in Milvus: {col.num_entities}")
except Exception as e:
    print(f"Milvus Error: {e}")

print("\\n--- Neo4j Audit ---")
try:
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session() as session:
        doc_count = session.run("MATCH (n:Document) RETURN sum(1)").single()[0]
        summary_count = session.run("MATCH (n:Document) WHERE n.summary IS NULL OR n.summary = '' RETURN sum(1)").single()[0]
        unknown_type_count = session.run("MATCH (n:Document) WHERE n.doc_type = 'unknown' RETURN sum(1)").single()[0]
        edge_count = session.run("MATCH ()-[r]->() RETURN sum(1)").single()[0]
        print(f"Total Document Nodes: {doc_count}")
        print(f"Nodes missing summaries: {summary_count}")
        print(f"Nodes with 'unknown' type: {unknown_type_count}")
        print(f"Total Edges: {edge_count}")
except Exception as e:
    print(f"Neo4j Error: {e}")

print("\\n--- Ingestion State ---")
if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
        processed = len(state.get("processed_files", {}))
        print(f"Processed files count in state file: {processed}")
else:
    print("Ingestion state file not found.")

