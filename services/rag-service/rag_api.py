from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sentence_transformers import SentenceTransformer
import httpx
import logging
from pymilvus import connections, Collection
from config import get_settings
from prometheus_fastapi_instrumentator import Instrumentator
from reranker import get_reranker

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


tags_metadata = [
    {"name": "General", "description": "General service information"},
    {"name": "Retrieval", "description": "Vector search and reranking operations"},
    {"name": "Generation", "description": "LLM interaction and RAG"},
]

app = FastAPI(
    title="BIM RAG Service", 
    description="""
    Retrieval Augmented Generation service for BIM applications.
    
    ## Features
    * **Vector Search**: Milvus-based semantic search.
    * **Reranking**: Cross-encoder reranking for high precision.
    * **LLM Integration**: Seamless connection to vLLM (OpenAI-compatible).
    """,
    version="2.0.0",
    openapi_tags=tags_metadata
)

# Instrument Prometheus
Instrumentator().instrument(app).expose(app)

embedding_model = None

class SearchRequest(BaseModel):
    query: str
    limit: int = 3
    use_reranker: bool = True

class ChatRequest(BaseModel):
    query: str
    context_limit: int = 3
    history: Optional[List[dict]] = None

@app.on_event("startup")
async def startup_event():
    global embedding_model
    logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}...")
    embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
    
    # Connect to Milvus
    try:
        logger.info(f"Connecting to Milvus at {settings.MILVUS_HOST}:{settings.MILVUS_PORT}")
        connections.connect(
            alias="default", 
            host=settings.MILVUS_HOST, 
            port=settings.MILVUS_PORT
        )
        logger.info("Connected to Milvus")
    except Exception as e:
        logger.error(f"Failed to connect to Milvus: {e}")
        # We don't raise here to allow the service to start even if DB is down temporarily, 
        # but API calls will fail.

    logger.info("Service ready.")

@app.get("/", tags=["General"])
async def root():
    return {"message": "BIM RAG Service is running", "docs": "/docs", "health": "/health"}

@app.post("/search", tags=["Retrieval"])
async def search(request: SearchRequest):
    """
    Perform semantic search with optional reranking.
    """
    try:
        # Generate embedding
        # sentence-transformers is CPU bound, run in threadpool if high load, but ok for now
        vector = embedding_model.encode([request.query], normalize_embeddings=True)[0].tolist()
        
        # Search Milvus
        collection = Collection(settings.MILVUS_COLLECTION)
        collection.load()
        
        search_params = {
            "metric_type": "IP", 
            "params": {"nprobe": 10}
        }
        
        # Retrieve more candidates for reranking
        initial_limit = request.limit * 3 if request.use_reranker else request.limit
        
        results = collection.search(
            data=[vector], 
            anns_field="vector", 
            param=search_params, 
            limit=initial_limit, 
            output_fields=["text", "source"]
        )
        
        top_results = []
        # Flatten results (single query)
        if results:
            raw_hits = results[0]
            
            if request.use_reranker:
                # Extract texts for reranking
                docs = [hit.entity.get("text") for hit in raw_hits]
                reranker = get_reranker()
                reranked = reranker.rerank(request.query, docs, top_k=request.limit)
                
                # Map back to full objects (simplified mapping, might lose source if text is duplicate but acceptable for now)
                # Better way: reranker returns indices or we map scores back
                
                # Let's map scores back to hits for simplicity, preserving source
                # Create a map of text -> hit
                hit_map = {hit.entity.get("text"): hit for hit in raw_hits}
                
                for doc_text, score in reranked:
                    original_hit = hit_map.get(doc_text)
                    top_results.append({
                        "text": doc_text,
                        "source": original_hit.entity.get("source"),
                        "score": float(score) # Reranker score
                    })
            else:
                for hit in raw_hits:
                    top_results.append({
                        "text": hit.entity.get("text"),
                        "source": hit.entity.get("source"),
                        "score": hit.score
                    })

        return {"results": top_results}
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", tags=["Generation"])
async def chat(request: ChatRequest):
    """
    Full RAG pipeline: Retrieval -> Reranking (optional) -> LLM Generation.
    """
    try:
        # 1. Retrieval
        search_res = await search(SearchRequest(query=request.query, limit=request.context_limit))
        context_text = "\n\n".join([f"[{r['source']}]: {r['text']}" for r in search_res["results"]])
        
        # 2. Augmentation
        system_prompt = f"""You are a BIM Expert Assistant specialized in ISO 19650.
Use the following context to answer the user's question. 
If the answer is not in the context, say so, but try to be helpful with general BIM knowledge.
        
Context:
{context_text}
"""
        
        messages = [{"role": "system", "content": system_prompt}]
        if request.history:
            messages.extend(request.history)
        messages.append({"role": "user", "content": request.query})
        
        # 3. Generation (Call vLLM — OpenAI Chat Completions)
        payload = {
            "model": settings.VLLM_MODEL,
            "messages": messages,
            "stream": False,
            "temperature": 0.7,
            "max_tokens": 2048
        }
        
        vllm_chat_url = f"{settings.VLLM_API_BASE}/chat/completions"
        async with httpx.AsyncClient() as client:
            response = await client.post(
                vllm_chat_url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}"},
                timeout=120.0
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "answer": result["choices"][0]["message"]["content"],
            "context": search_res["results"]
        }
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health", tags=["General"])
async def health():
    return {"status": "ok", "embedding_model": settings.EMBEDDING_MODEL}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
