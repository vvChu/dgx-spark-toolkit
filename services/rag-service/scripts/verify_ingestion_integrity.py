import os
from pymilvus import connections, Collection
from config import get_settings

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Config
settings = get_settings()
MILVUS_HOST = os.getenv("MILVUS_HOST", settings.MILVUS_HOST)
MILVUS_PORT = os.getenv("MILVUS_PORT", settings.MILVUS_PORT)
COLLECTION_NAME = settings.MILVUS_COLLECTION

def verify_integrity():
    try:
        connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
        if not Collection(COLLECTION_NAME):
            logger.error(f"Collection {COLLECTION_NAME} not found.")
            return

        col = Collection(COLLECTION_NAME)
        col.load()

        # Get all unique sources
        logger.info("Fetching unique document sources from Milvus...")
        # Since Milvus doesn't support easy 'DISTINCT', we query and collect
        # Adjust limit if you have more than 10k chunks
        res = col.query(expr="id >= 0", output_fields=["source", "page"], limit=16384)
        
        docs = {}
        for r in res:
            src = r['source']
            pg = r['page']
            if src not in docs:
                docs[src] = set()
            docs[src].add(pg)

        logger.info(f"Found {len(docs)} unique documents.")
        
        issues_found = 0
        for src, pages in docs.items():
            if not pages:
                continue
            
            min_pg = min(pages)
            max_pg = max(pages)
            
            # Check for gaps
            expected_pages = set(range(min_pg, max_pg + 1))
            missing_pages = expected_pages - pages
            
            if missing_pages:
                logger.warning(f"GAP DETECTED: {src} is missing pages {sorted(list(missing_pages))}")
                issues_found += 1
            
            # Note: We can't easily know if the document has more pages after max_pg 
            # without checking the original filesystem file.
            
        if issues_found == 0:
            logger.info("✅ No page gaps detected in existing documents.")
        else:
            logger.info(f"Summary: Found {issues_found} documents with missing pages.")

    except Exception as e:
        logger.error(f"Integrity check failed: {e}")

if __name__ == "__main__":
    verify_integrity()
