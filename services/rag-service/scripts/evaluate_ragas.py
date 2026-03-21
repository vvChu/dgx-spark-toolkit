import httpx
import json
import logging
import pandas as pd
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
import os

# Configuration
RAG_BASE = os.getenv("RAG_BASE", "http://127.0.0.1:8000")
LITELLM_API_BASE = os.getenv("LITELLM_API_BASE", "http://100.83.192.30:8090/v1")
MODEL_NAME = os.getenv("VLLM_MODEL", "qwen3.5-35b")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sample Golden Dataset (extracted from evaluate_rag.py)
GOLD_DATASET = [
    {
        "question": "EIR (Exchange Information Requirements) là gì và vai trò của nó trong dự án BIM?",
        "ground_truth": "EIR là yêu cầu trao đổi thông tin của chủ đầu tư, quy định các thông tin cần thiết trong dự án BIM.",
    },
    {
        "question": "Nghị định 59/2015/NĐ-CP về quản lý dự án đầu tư xây dựng hiện tại còn hiệu lực không?",
        "ground_truth": "Nghị định 59/2015/NĐ-CP đã hết hiệu lực và được thay thế bởi Nghị định 15/2021/NĐ-CP.",
    }
]

def fetch_rag_response(question):
    try:
        resp = httpx.post(
            f"{RAG_BASE}/chat",
            json={"query": question, "context_limit": 5},
            timeout=60.0
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": data.get("answer", ""),
            "contexts": [c.get("text", "") for c in data.get("context", [])]
        }
    except Exception as e:
        logger.error(f"Error fetching RAG response: {e}")
        return {"answer": "", "contexts": []}

def run_ragas_eval():
    logger.info("Building evaluation dataset...")
    data = []
    for item in GOLD_DATASET:
        logger.info(f"Querying: {item['question']}")
        rag_res = fetch_rag_response(item['question'])
        data.append({
            "question": item['question'],
            "answer": rag_res['answer'],
            "contexts": rag_res['contexts'],
            "ground_truth": item['ground_truth']
        })
    
    dataset = Dataset.from_list(data)
    
    logger.info("Running Ragas evaluation...")
    # Using local LiteLLM proxy for evaluation models
    # Ragas uses langchain under the hood, so we can configure it to use our gateway
    from langchain_openai import ChatOpenAI
    
    eval_llm = ChatOpenAI(
        model=MODEL_NAME,
        base_url=LITELLM_API_BASE,
        api_key="sk-1234", # Dummy key for proxy
    )
    
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=eval_llm
    )
    
    df = result.to_pandas()
    logger.info("Evaluation results:")
    print(df)
    
    output_path = "/tmp/ragas_detailed_results.json"
    df.to_json(output_path, orient="records", force_ascii=False, indent=2)
    logger.info(f"Detailed results saved to {output_path}")
    
    return result

if __name__ == "__main__":
    run_ragas_eval()
