import logging
import json
import httpx
from typing import List, Dict, Any
from config import get_settings

settings = get_settings()
logger = logging.getLogger("evaluator")

EVAL_SYSTEM_PROMPT = """You are an expert RAG Evaluator specialized in Vietnamese Construction Law and BIM (Building Information Modeling) standards (ISO 19650, Decree 15/2021/ND-CP, etc.).

Your goal is to judge the quality of a generated answer based on the provided context and the original query.

### Evaluation Criteria:
1. **Faithfulness** (0.0 - 1.0): 
   - Is the answer derived solely from the provided context?
   - 1.0: Every claim is supported by the context.
   - 0.5: Mix of context and general knowledge/hallucination.
   - 0.0: The answer contradicts the context or is entirely hallucinated.
   - *Special Rule*: If the answer quotes a Decree number or Article not in the context, faithfulness must be < 0.5.

2. **Answer Relevancy** (0.0 - 1.0):
   - Does the answer directly address the user's query?
   - 1.0: Perfect, comprehensive answer.
   - 0.5: Partially answers the query but misses key details.
   - 0.0: Irrelevant or answers a different question.

Return your response in JSON format:
{
    "faithfulness": float,
    "faithfulness_reason": str,
    "relevancy": float,
    "relevancy_reason": str,
    "suggestions": [str]
}
"""

async def evaluate_rag_response(query: str, answer: str, context: List[str]) -> Dict[str, Any]:
    """
    Evaluates a RAG response using a high-quality 'Judge' model from the AI Gateway.
    Implements retry logic and fallback to local Qwen model if cloud models fail.
    """
    if not settings.EVAL_ENABLED:
        logger.warning("RAG Evaluation is disabled in settings.")
        return {"error": "Evaluation disabled"}

    combined_context = "\n---\n".join(context)
    user_prompt = f"""### User Query:
{query}

### Retrieved Context:
{combined_context}

### Generated Answer:
{answer}

Please evaluate the answer.
"""

    models_to_try = [settings.EVAL_MODEL, "qwen3.5-35b"]
    
    for model in models_to_try:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": EVAL_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        # Try up to 2 times for each model
        for attempt in range(2):
            try:
                gateway_url = "http://ai-gateway:4000/v1/chat/completions"
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        gateway_url, 
                        json=payload,
                        headers={"Authorization": f"Bearer {settings.LITELLM_MASTER_KEY}"},
                        timeout=90.0 # Increased timeout for heavy reasoning
                    )
                    resp.raise_for_status()
                    result = resp.json()
                    
                    content = result["choices"][0]["message"].get("content", "")
                    
                    # Clean up markdown JSON block if present
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                        
                    if not content:
                        raise ValueError("Empty content from judge.")
                        
                    eval_results = json.loads(content)
                    logger.info(f"Evaluation success with model: {model} (Attempt {attempt+1})")
                    return eval_results

            except Exception as e:
                logger.warning(f"Evaluation attempt {attempt+1} failed for model {model}: {e}")
                if attempt < 1:
                    await asyncio.sleep(2 * (attempt + 1)) # Simple backoff
                continue
    
    # If all fails
    logger.error("All evaluation attempts and models failed.")
    return {
        "error": "All evaluation models failed",
        "faithfulness": 0.0,
        "relevancy": 0.0,
        "faithfulness_reason": "Service continuity failure",
        "relevancy_reason": "Service continuity failure",
        "suggestions": ["Check AI Gateway health and account credits."]
    }
