"""Metadata extraction mixin — filename regex, LLM refinement, synthetic queries."""
import logging
import re
import time

from ingestion.json_parser import extract_json_from_response
from ingestion.pipeline_config import JSON_MODEL, TEXT_METADATA_MODEL, SYNTHETIC_QUERY_MODEL

logger = logging.getLogger(__name__)


class MetadataMixin:
    """Methods for extracting and refining document metadata."""

    def parse_metadata(self, filename):
        """Extract metadata from Vietnamese legal doc filenames.
        Common patterns:
          20250610_QD1111-TTg_Title.pdf
          20250404_QD08-TTg_Che do boi duong giam dinh tu phap_ththeQD01-2014.pdf
          TT01-2023-BTP_Quy dinh che do BC thi hanh PL ve XLVPHC_16-01-2023.pdf
        """
        meta = {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}

        # Anchor date extraction to start of filename
        date_match = re.match(r'(\d{8})[_\-]', filename)
        if date_match:
            d = date_match.group(1)
            meta["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"

        # Extract doc type + number + authority
        doc_match = re.search(r'([A-Z]{2,4})(\d+)[-/]([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)', filename)
        if doc_match:
            meta["type"] = doc_match.group(1)
            number = doc_match.group(2)
            authority_part = doc_match.group(3)

            auth_parts = authority_part.split('-')
            non_year = [p for p in auth_parts if not re.match(r'^\d{4}$', p)]
            if non_year:
                meta["authority"] = non_year[-1]

            year_parts = [p for p in auth_parts if re.match(r'^\d{4}$', p)]
            year = year_parts[0] if year_parts else (meta["date"][:4] if meta["date"] != "unknown" else "")

            type_vn = meta["type"]
            auth = meta["authority"]
            if year and year != "unknown":
                meta["doc_number"] = f"{number}/{year}/{type_vn}-{auth}"
            else:
                meta["doc_number"] = f"{number}/{type_vn}-{auth}"

        return meta

    def parse_metadata_from_text(self, text):
        """Use LLM to refine metadata from document text."""
        try:
            payload = {
                "model": TEXT_METADATA_MODEL,
                "messages": [
                    {"role": "system", "content": "You are a precise JSON extractor. You MUST output ONLY raw JSON. Do NOT include any 'Thinking Process', 'Analysis', 'Observation', or preamble. NO text before or after the JSON block. Start EXACTLY with '{' and end EXACTLY with '}'."},
                    {"role": "user", "content": f"Extract V9 metadata as JSON for this Vietnamese document: {text[:4000]}\n\nRequired format:\n{{\"doc_number\": \"Full official document number (e.g. 123/QD-UBND or 123/2024/TT-BTP). Do NOT extract single digits or page numbers.\", \"doc_date\": \"YYYY-MM-DD\", \"doc_type\": \"...\", \"authority\": \"...\", \"validity_status\": \"ACTIVE\", \"project_code\": \"GENERIC\", \"discipline\": \"UNKNOWN\", \"doc_status\": \"ACTIVE\", \"revision\": 0}}"}
                ],
                "max_tokens": 4096,
                "temperature": 0.0,
            }
            # Only add vLLM-specific params for local models
            if TEXT_METADATA_MODEL in ("rag-core", "qwen3.5-35b", "rag-light"):
                payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            retry_delay = 5
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        wait_time = retry_delay * (2 ** attempt)
                        logger.warning(f"Rate limited (429) in parse_metadata. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    refined = extract_json_from_response(data)
                    if not refined:
                        raise ValueError("No refined metadata extracted")

                    # Normalize keys (case-insensitive, handle common LLM key variations)
                    normalized = {}
                    for k, v in refined.items():
                        k_lower = k.lower()
                        if "number" in k_lower or "hiệu" in k_lower:
                            normalized["doc_number"] = v
                        elif "date" in k_lower or "hành" in k_lower:
                            normalized["doc_date"] = v
                        elif "type" in k_lower or "loại" in k_lower:
                            normalized["doc_type"] = v
                        elif "authority" in k_lower or "quyền" in k_lower:
                            normalized["authority"] = v
                        else:
                            normalized[k_lower] = v

                    def regularize(val, default):
                        if not val or str(val).lower() in ["unknown", "n/a", "none", "chưa rõ"]:
                            return default
                        return val

                    return {
                        "date": regularize(normalized.get("doc_date"), "2025-01-01"),
                        "type": regularize(normalized.get("doc_type"), "VAN_BAN")[:32],
                        "authority": regularize(normalized.get("authority"), "CO_QUAN_BAN_HANH")[:64],
                        "doc_number": normalized.get("doc_number", ""),
                        "validity_status": normalized.get("validity_status", "ACTIVE")[:32],
                        "project_code": normalized.get("project_code", "GENERIC")[:64],
                        "discipline": normalized.get("discipline", "UNKNOWN")[:32],
                        "doc_status": normalized.get("doc_status", "ACTIVE")[:32],
                        "revision": int(float(normalized.get("revision", 0) or 0))
                    }
                except Exception as e:
                    if attempt == max_retries - 1:
                        logging.error(f"Metadata extraction failed after {max_retries} attempts: {e}")
                        return {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}
                    time.sleep(retry_delay * (2 ** attempt))
        except Exception as e:
            logger.warning(f"Vision metadata extraction failed: {e}")
            return {"date": "unknown", "type": "unknown", "authority": "unknown", "doc_number": ""}

    def generate_synthetic_queries(self, chunk_text: str) -> str:
        """Generate synthetic queries for better vector grounding."""
        try:
            payload = {
                "model": SYNTHETIC_QUERY_MODEL,
                "messages": [
                    {"role": "system", "content": "You are an assistant that generates hypothetical user questions. Output ONLY 3-5 questions separated by newlines that the given text can answer."},
                    {"role": "user", "content": f"Generate 3-5 questions for this text:\n\n{chunk_text}\n\nQuestions:"}
                ],
                "max_tokens": 512,
                "temperature": 0.5,
            }
            # Only add vLLM-specific params for local models
            if SYNTHETIC_QUERY_MODEL in ("rag-core", "qwen3.5-35b", "rag-light"):
                payload["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
            headers = {"Authorization": f"Bearer {self.vision.api_key}"}
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    resp = self._http_client.post(self.vision.api_url, json=payload, headers=headers)
                    if resp.status_code == 429:
                        time.sleep(5 * (2 ** attempt))
                        continue
                    resp.raise_for_status()
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or ""
                    return content.strip()[:4000]
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Synthetic queries failed after {max_retries} attempts: {e}")
                        return ""
                    time.sleep(5 * (2 ** attempt))
        except Exception:
            return ""

    def extract_doc_number_regex(self, text):
        """Low-level regex fallback to find formal Vietnamese legal patterns in text."""
        pattern = r"(?i)Số[:\s]*(\d+(?:/\d+)?/[A-ZĐ]+-[A-Z\d-]+)"
        match = re.search(pattern, text[:3000])
        if match:
            return match.group(1).strip()
        fallback_pattern = r"(?i)Số[:\s]*(\d+[\w\d/-]*)"
        match = re.search(fallback_pattern, text[:2000])
        if match:
            return match.group(1).strip()
        return None
