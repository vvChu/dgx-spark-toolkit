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
        output_fields=["source", "doc_number"],
        limit=2000 # Should cover the 1404 missing docs
    )
    
    source_to_doc = {}
    for entry in res:
        source = entry.get("source")
        doc_num = entry.get("doc_number")
        if source and doc_num:
            source_to_doc[source] = doc_num
            
    print(f"Found {len(source_to_doc)} document mappings in Milvus.")
    
    if not source_to_doc:
        print("No documents found in Milvus with doc_numbers. Aborting.")
        return

    updated_count = 0
    with n_driver.session() as session:
        for source_id, doc_num in source_to_doc.items():
            # Update Neo4j node if it exists and doc_number is missing or different
            result = session.run(
                """
                MATCH (d:Document {id: $id})
                WHERE d.doc_number IS NULL OR d.doc_number = ''
                SET d.doc_number = $doc_num
                RETURN d.id as id
                """,
                id=source_id, doc_num=doc_num
            )
            if result.single():
                updated_count += 1
                if updated_count % 100 == 0:
                    print(f"  Updated {updated_count} documents...")

    print(f"Successfully repaired {updated_count} documents in Neo4j.")
    n_driver.close()

if __name__ == "__main__":
    repair()
