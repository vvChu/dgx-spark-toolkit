import asyncio
import logging
import json
from typing import List, Dict, Any

import httpx

from repositories.milvus_repo import MilvusRepository
from retrieval.graph_timeline_retriever import AdvancedGraphRAG
from core.config import get_settings

logger = logging.getLogger(__name__)

class ComplianceService:
    def __init__(self, milvus_repo: MilvusRepository, graph_rag: AdvancedGraphRAG, http_client: httpx.AsyncClient | None = None):
        self.milvus_repo = milvus_repo
        self.graph_rag = graph_rag
        self._http_client = http_client

    async def check_compliance(self, project_profile: str, focus_area: str = "General") -> Dict[str, Any]:
        """
        Analyze a project profile against active regulations.
        """
        logger.info(f"Starting compliance check for focus area: {focus_area}")

        # 1. Extraction: Use LLM to identify key keywords and disciplines from the profile
        keywords = await self._extract_compliance_keywords(project_profile, focus_area)
        logger.info(f"Extracted compliance keywords: {keywords}")

        # 2. Retrieval: Search for ACTIVE mandates and regulations
        # We search specifically for prohibition/requirement keywords + project keywords
        search_query = f"Quy định, bắt buộc, nghiêm cấm về {', '.join(keywords)}"
        # Filter for ACTIVE documents only
        expr = "validity_status == 'ACTIVE'"
        
        # Get embeddings from the shard model
        from services.retrieval_service import get_embedding_model
        model = get_embedding_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, model.embed_query, search_query)
        
        retrieved_chunks = await self.milvus_repo.hybrid_search(
            query_vector=embeddings["dense"],
            sparse_vector=embeddings["sparse"],
            limit=15,
            expr=expr
        )

        context = []
        for res in retrieved_chunks[0]:
            context.append({
                "text": res.entity.get("text"),
                "source": res.entity.get("doc_number") or res.entity.get("source"),
                "page": res.entity.get("page")
            })

        # 3. LLM Analysis: Compare profile vs context
        report = await self._generate_compliance_report(project_profile, context, focus_area)
        
        return {
            "focus_area": focus_area,
            "keywords_analyzed": keywords,
            "report": report,
            "sources": list(set([c["source"] for c in context]))
        }

    async def _extract_compliance_keywords(self, profile: str, focus: str) -> List[str]:
        prompt = f"""
        Extract 5-8 key technical keywords from this project profile that relate to legal requirements, 
        standards, or safety regulations in the field of {focus}.
        Focus on structural types, materials, location constraints, or specialized equipment.
        
        Profile: {profile}
        
        Output ONLY a JSON list of strings.
        """
        try:
            # Reusing graph_rag's LLM access via its http_client and settings
            settings = get_settings()
            payload = {
                "model": settings.VLLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 100,
                "response_format": {"type": "json_object"}
            }
            client = self._http_client or await self.graph_rag._get_client()
            resp = await client.post(
                f"{settings.VLLM_API_BASE}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Clean possible markdown
            content = content.replace("```json", "").replace("```", "").strip()
            return json.loads(content).get("keywords", [])
        except Exception as e:
            logger.error(f"Keyword extraction failed: {e}")
            return [focus]

    async def _generate_compliance_report(self, profile: str, context: List[Dict], focus: str) -> Dict[str, Any]:
        context_str = "\n\n".join([f"Source: {c['source']} (Page {c['page']})\nContent: {c['text']}" for c in context])
        
        prompt = f"""
        You are a Legal Compliance Auditor. Analyze the following Project Profile against the provided Regulatory Context.
        
        PROJECT PROFILE:
        {profile}
        
        REGULATORY CONTEXT (ACTIVE LAWS):
        {context_str}
        
        TASK:
        Identify if the project aligns with or violates the rules in the context.
        Group findings into:
        1. COMPLIANT: Elements that follow the rules.
        2. RISKS: Areas that are ambiguous or need more documentation.
        3. VIOLATIONS: Direct contradictions with the law.
        
        Output a structured JSON report. Include citations to sources.
        """
        
        try:
            settings = get_settings()
            payload = {
                "model": settings.VLLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"}
            }
            client = self._http_client or await self.graph_rag._get_client()
            resp = await client.post(
                f"{settings.VLLM_API_BASE}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY.get_secret_value()}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return json.loads(data["choices"][0]["message"]["content"])
        except Exception as e:
            logger.error(f"Compliance report generation failed: {e}")
            return {
                "error": "Failed to generate detailed report",
                "summary": "Manual review required due to LLM processing error."
            }
