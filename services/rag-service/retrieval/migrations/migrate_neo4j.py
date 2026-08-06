import asyncio
import os
from neo4j import AsyncGraphDatabase


async def migrate_neo4j():
    uri = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASS", "bim_secure_pass_2026")

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    queries = [
        "MATCH (d:Document) WHERE d.effective_date IS NULL SET d.effective_date = coalesce(d.date, 'unknown')",
        "CREATE INDEX idx_document_status IF NOT EXISTS FOR (d:Document) ON (d.status)",
        "CREATE INDEX idx_document_doc_num IF NOT EXISTS FOR (d:Document) ON (d.doc_number)",
        "CREATE INDEX idx_relation_type IF NOT EXISTS FOR ()-[r:AMENDS|REPLACES|REFERENCES]-() ON (r.type)"
    ]

    async with driver.session() as session:
        for q in queries:
            print(f"Running Cypher: {q}")
            try:
                await session.run(q)
            except Exception as e:
                print(f"Index/Update failed (might already exist): {e}")

    await driver.close()

if __name__ == "__main__":
    asyncio.run(migrate_neo4j())
