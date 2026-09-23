import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.exists("/app") and "/app" not in sys.path:
    sys.path.insert(0, "/app")

from pymilvus import MilvusClient
from neo4j import GraphDatabase
from core.config import get_settings

_settings = get_settings()

# Config
MILVUS_URI = f"http://{_settings.MILVUS_HOST}:{_settings.MILVUS_PORT}"
COLLECTION_NAME = _settings.MILVUS_COLLECTION
NEO4J_URI = _settings.NEO4J_URI
NEO4J_USER = _settings.NEO4J_USER
NEO4J_PASSWORD = _settings.NEO4J_PASSWORD.get_secret_value()


def repair():
    print("Connecting to Milvus...")
    m_client = MilvusClient(uri=MILVUS_URI)

    print("Connecting to Neo4j...")
    n_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    print("Querying Milvus for documents with metadata...")
    # Query with a reasonable limit to avoid timeout during test
    res = m_client.query(
        collection_name=COLLECTION_NAME,
        filter='chunk_type == "parent"',
        output_fields=["source", "doc_number", "doc_id"],
        limit=2000  # Should cover the 1404 missing docs
    )

    doc_mappings = []
    for entry in res:
        source = entry.get("source")
        doc_num = entry.get("doc_number")
        doc_id = entry.get("doc_id", "")
        if "Luat_50-2014" in str(source) or "Luat_50-2014" in str(doc_id):
            doc_num = "50/2014/QH13"
        if source and doc_num:
            doc_mappings.append((source, doc_id, doc_num))

    print(f"Found {len(doc_mappings)} document entries in Milvus.")

    if not doc_mappings:
        print("No documents found in Milvus with doc_numbers. Setting defaults.")

    updated_count = 0
    with n_driver.session() as session:
        # Explicit normalization for Luật Xây dựng 2014
        session.run(
            """
            MATCH (d:Document)
            WHERE d.id CONTAINS 'Luat_50-2014' OR d.file_name CONTAINS 'Luat_50-2014' OR d.doc_number CONTAINS '50-2014'
            SET d.doc_number = '50/2014/QH13'
            RETURN d.id as id
            """
        )

        for source_id, doc_id, doc_num in doc_mappings:
            # Update Neo4j node matching file_name, id, or ROOT/ prefix
            result = session.run(
                """
                MATCH (d:Document)
                WHERE d.file_name = $source
                   OR d.id = $source
                   OR d.id = $doc_id
                   OR d.id = 'ROOT/' + $doc_id
                   OR d.id = replace($doc_id, 'ROOT/', '')
                SET d.doc_number = $doc_num
                RETURN d.id as id
                """,
                source=source_id, doc_id=doc_id, doc_num=doc_num
            )
            if result.single():
                updated_count += 1
                if updated_count % 100 == 0:
                    print(f"  Updated {updated_count} documents...")

    print(f"Successfully repaired {updated_count} documents in Neo4j.")
    n_driver.close()


if __name__ == "__main__":
    repair()
