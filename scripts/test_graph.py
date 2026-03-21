from neo4j import GraphDatabase
import os

uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
user = os.getenv("NEO4J_USER", "neo4j")
password = os.environ["NEO4J_PASS"]  # required — no default
driver = GraphDatabase.driver(uri, auth=(user, password))

query = """
MATCH (d:Document)
OPTIONAL MATCH (d)-[r]->(target:Document)
OPTIONAL MATCH (source:Document)-[r2]->(d)
RETURN d.id as id, type(r) as out_rel, target.id as target, type(r2) as in_rel, source.id as source
LIMIT 5
"""

with driver.session() as session:
    result = session.run("MATCH (n:Document) RETURN COUNT(n) as count")
    print(f"Total Documents: {result.single()['count']}")
    
    result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
    print(f"Total Relationships: {result.single()['count']}")

    print("\nSample Data:")
    result = session.run(query)
    for rec in result:
        print(dict(rec))
