import os
import argparse
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
from config import get_settings
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

def connect_milvus():
    try:
        connections.connect(
            alias="default", 
            host=settings.MILVUS_HOST, 
            port=settings.MILVUS_PORT
        )
        logger.info(f"Connected to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        return True
    except Exception as e:
        logger.error(f"Failed to connect to Milvus: {e}")
        return False

def setup_collection(drop_existing=False):
    collection_name = settings.MILVUS_COLLECTION
    
    if utility.has_collection(collection_name):
        if drop_existing:
            utility.drop_collection(collection_name)
            logger.info(f"Dropped existing collection: {collection_name}")
        else:
            logger.info(f"Collection {collection_name} already exists.")
            return Collection(collection_name)
            
    # Define schema
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024)
    ]
    schema = CollectionSchema(fields, "ISO 19650 Documents")
    
    collection = Collection(collection_name, schema)
    
    # Create index
    index_params = {
        "metric_type": "IP",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128}
    }
    collection.create_index(field_name="vector", index_params=index_params)
    logger.info(f"Created collection and index for {collection_name}")
    
    return collection

def load_documents(path):
    logger.info(f"Loading documents from {path}...")
    documents = []
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        chunk_size = 500
        overlap = 50
        lines = content.split('\n')
        current_chunk = []
        current_length = 0
        
        for line in lines:
            line = line.strip()
            if not line: continue
            current_chunk.append(line)
            current_length += len(line)
            if current_length >= chunk_size:
                text = "\n".join(current_chunk)
                documents.append({"text": text, "source": os.path.basename(path)})
                
                # Simple overlap logic
                overlap_len = 0
                new_chunk = []
                for l in reversed(current_chunk):
                    if overlap_len < overlap:
                        new_chunk.insert(0, l)
                        overlap_len += len(l)
                    else:
                        break
                current_chunk = new_chunk
                current_length = overlap_len
                
        if current_chunk:
            documents.append({"text": "\n".join(current_chunk), "source": os.path.basename(path)})
            
    logger.info(f"Created {len(documents)} chunks")
    return documents

def main():
    parser = argparse.ArgumentParser(description="Index documents into Milvus")
    parser.add_argument("--path", type=str, required=True, help="Path to the document file")
    parser.add_argument("--drop", action="store_true", help="Drop existing collection before indexing")
    args = parser.parse_args()

    if not connect_milvus():
        return

    collection = setup_collection(drop_existing=args.drop)
    
    logger.info("Loading pseudo embedding model using qwen3.5-9b-rag...")
    from rag_api import get_embedding_model
    model = get_embedding_model()
    
    chunks = load_documents(args.path)
    if not chunks:
        logger.warning("No chunks created. Exiting.")
        return

    logger.info("Generating embeddings...")
    texts = [doc["text"] for doc in chunks]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    
    logger.info("Inserting data...")
    
    # Batch insert
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch_chunks = chunks[i:i+batch_size]
        batch_embeddings = embeddings[i:i+batch_size]
        
        data = [
            [c["text"] for c in batch_chunks],
            [c["source"] for c in batch_chunks],
            [v.tolist() for v in batch_embeddings]
        ]
        
        collection.insert(data)
        logger.info(f"Inserted batch {i//batch_size + 1}")
        
    collection.flush()
    logger.info(f"Indexing complete! Total rows: {collection.num_entities}")

if __name__ == "__main__":
    main()
