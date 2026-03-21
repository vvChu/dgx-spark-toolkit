from neo4j import GraphDatabase
import os

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j-graph:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.environ["NEO4J_PASS"]  # required — no default

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
with driver.session() as session:
    res = session.run("MATCH (d:Document) WHERE d.doc_type = 'unknown' RETURN d.id, d.title, d.doc_type LIMIT 20")
    for r in res:
        print(f"Node: {r.get('d.id')}, Title: {r.get('d.title')}, Type: {r.get('d.doc_type')}")

    count = session.run("MATCH (d:Document) WHERE d.doc_type = 'unknown' RETURN count(d)").single()[0]
    print(f"Total unknown doc nodes: {count}")
    
    print("Checking 09/2022")
    res2 = session.run("MATCH (d:Document) WHERE d.id CONTAINS '09/2022' RETURN d.id, d.title, d.doc_type LIMIT 20")
    for r in res2:
        print(f"Node: {r.get('d.id')}, Title: {r.get('d.title')}, Type: {r.get('d.doc_type')}")
        
    count2 = session.run("MATCH (d:Document) WHERE d.id CONTAINS '09/2022' RETURN count(d)").single()[0]
    print(f"Total 09/2022 docs: {count2}")

driver.close()
