import os
import argparse
import fitz  # PyMuPDF
import docx  # python-docx
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
from pymilvus import connections, FieldSchema, CollectionSchema, DataType, Collection, utility
from core.config import get_settings
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

def setup_collection(collection_name, drop_existing=False):
    if utility.has_collection(collection_name):
        if drop_existing:
            utility.drop_collection(collection_name)
            logger.info(f"Dropped existing collection: {collection_name}")
        else:
            logger.info(f"Collection {collection_name} already exists.")
            return Collection(collection_name)
            
    # Define schema mapping to production_ingest.py
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=15000),
        FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
        FieldSchema(name="page", dtype=DataType.INT64),
        FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=2048),
        FieldSchema(name="doc_date", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="authority", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="file_hash", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="is_table", dtype=DataType.BOOL),
        FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=16),
        FieldSchema(name="parent_id", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="doc_number", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="bbox", dtype=DataType.VARCHAR, max_length=128),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema(name="sparse_vector", dtype=DataType.SPARSE_FLOAT_VECTOR)
    ]
    schema = CollectionSchema(fields, "Production Legal Documents v7 - Grounded Citations")
    
    collection = Collection(collection_name, schema)
    
    # Create indexes
    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 500}
    }
    collection.create_index(field_name="vector", index_params=index_params)
    
    sparse_index_params = {
        "metric_type": "IP",
        "index_type": "SPARSE_INVERTED_INDEX",
        "params": {"drop_ratio_build": 0.2}
    }
    collection.create_index(field_name="sparse_vector", index_params=sparse_index_params)
    logger.info(f"Created collection and indexes for {collection_name}")
    
    return collection

def extract_text(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    chunks = []
    
    if ext == '.pdf':
        logger.info(f"Extracting PDF: {file_path}")
        try:
            doc = fitz.open(file_path)
            for i, page in enumerate(doc):
                text = page.get_text()
                if text and len(text.strip()) > 50:
                    chunks.append({"text": text.replace('\0', ''), "source": os.path.basename(file_path), "page": i + 1})
            doc.close()
        except Exception as e:
            logger.error(f"PDF error {file_path}: {e}")
            
    elif ext == '.docx':
        logger.info(f"Extracting DOCX: {file_path}")
        try:
            doc = docx.Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                if para.text.strip():
                    full_text.append(para.text)
            
            # Combine and split into manageable chunks
            text = "\n".join(full_text).replace('\0', '')
            if len(text) > 2000:
                parts = [text[j:j+2000] for j in range(0, len(text), 1500)]
                for k, part in enumerate(parts):
                    chunks.append({"text": part, "source": os.path.basename(file_path), "page": k + 1})
            elif text:
                chunks.append({"text": text, "source": os.path.basename(file_path), "page": 1})
        except Exception as e:
            logger.error(f"DOCX error {file_path}: {e}")
            
    return chunks

def main():
    parser = argparse.ArgumentParser(description="Index legal documents into Milvus")
    parser.add_argument("--dir", type=str, default="data/legal_test", help="Directory containing files")
    parser.add_argument("--collection", type=str, default=settings.MILVUS_COLLECTION, help="Milvus collection name")
    parser.add_argument("--drop", action="store_true", help="Drop existing collection before indexing")
    parser.add_argument("--reindex-all", action="store_true", help="Synonym for --drop: clear and re-index all")
    args = parser.parse_args()

    if not connect_milvus():
        return

    collection = setup_collection(args.collection, drop_existing=args.drop or args.reindex_all)
    
    logger.info("Loading pseudo embedding model using qwen3.5-9b-rag...")
    from rag_api import get_embedding_model
    model = get_embedding_model()
    
    all_chunks = []
    for root, _, filenames in os.walk(args.dir):
        for filename in filenames:
            if filename.lower().endswith(('.pdf', '.docx')):
                file_path = os.path.join(root, filename)
                chunks = extract_text(file_path)
                all_chunks.extend(chunks)
        
    if not all_chunks:
        logger.warning("No text extracted. Exiting.")
        return

    logger.info(f"Total chunks: {len(all_chunks)}")
    
    logger.info("Generating embeddings on GPU...")
    texts = [c["text"] for c in all_chunks]
    embeddings = model.encode(texts, normalize_embeddings=True)
    
    logger.info(f"Inserting {len(all_chunks)} entities into Milvus...")
    
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch_items = all_chunks[i:i+batch_size]
        batch_embeddings = embeddings[i:i+batch_size]
        
        import re
        sparse_vectors = []
        for text in [c["text"] for c in batch_items]:
            words = re.findall(r'\w+', text.lower())
            sv = {}
            for w in words:
                sv[hash(w) % 32768] = sv.get(hash(w) % 32768, 0) + 1.0
            sparse_vectors.append(sv)

        data = [
            [c["text"] for c in batch_items],
            [c["source"] for c in batch_items],
            [c["page"] for c in batch_items],
            ["" for _ in batch_items],  # summary
            ["" for _ in batch_items],  # doc_date
            ["" for _ in batch_items],  # doc_type
            ["" for _ in batch_items],  # authority
            ["dummy_hash" for _ in batch_items],  # file_hash
            [False for _ in batch_items],  # is_table
            ["parent" for _ in batch_items],  # chunk_type
            ["" for _ in batch_items],  # parent_id
            ["" for _ in batch_items],  # doc_number
            ["[0,0,100,100]" for _ in batch_items], # bbox
            [v.tolist() for v in batch_embeddings],
            sparse_vectors
        ]
        collection.insert(data)
        
    collection.flush()
    logger.info(f"Indexing complete! Total entities in {args.collection}: {collection.num_entities}")

if __name__ == "__main__":
    main()
