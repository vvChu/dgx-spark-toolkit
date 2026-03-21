import asyncio
import logging
import sys
import os

# Adjust path to import from app
sys.path.append("/app")

from services.compliance_service import ComplianceService
from core.database import get_milvus_repo, get_neo4j_repo
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
import httpx

logging.basicConfig(level=logging.INFO)

async def test_compliance():
    print("Initializing repos...")
    # Mocking a minimal app state or using real dependencies
    from core.database import lifespan
    from fastapi import FastAPI
    
    app = FastAPI()
    async with lifespan(app):
        milvus = app.state.milvus_client
        # We need the repo wrappers
        from repositories.milvus_repo import MilvusRepository
        from repositories.neo4j_repo import Neo4jRepository
        
        milvus_repo = MilvusRepository(milvus)
        neo4j_repo = Neo4jRepository(app.state.neo4j_driver)
        http_client = app.state.http_client
        
        graph_rag = AdvancedGraphRAG(neo4j_repo._driver, http_client)
        service = ComplianceService(milvus_repo, graph_rag)
        
        print("Running check_compliance...")
        profile = "Dự án xây dựng nhà kho quy mô nhỏ tại Hà Nội, yêu cầu tuân thủ PCCC."
        result = await service.check_compliance(profile, "PCCC")
        print("RESULT:")
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_compliance())
