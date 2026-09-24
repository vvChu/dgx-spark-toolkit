#!/usr/bin/env python3
"""Clean contaminated synthetic_queries in JSON exports and update Milvus legal_docs_v11.

Usage:
    python3 services/rag-service/scripts/clean_synthetic_queries.py
"""

import os
import sys
import json
import re
import logging
from pathlib import Path

# Add rag-service to path
_RAG_ROOT = str(Path(__file__).resolve().parent.parent)
if _RAG_ROOT not in sys.path:
    sys.path.insert(0, _RAG_ROOT)

from pymilvus import MilvusClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_VN_DIACRITICS = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđĐ]",
    re.IGNORECASE,
)

_ENG_QUESTION_START = re.compile(
    r"^(?:What|Who|When|Where|Why|How|Which|Is|Are|Can|Could|Do|Does|Did|Will|Would|Should|Shall)\b",
    re.IGNORECASE,
)

_METADATA_PREFIXES = re.compile(
    r"^(?:Text|Input|Source|Topic|Note|Subject|Action|Condition|Requirement|"
    r"Document ID|Appendices|Key Point|Table|Image|Specific|Draft|Analyze|Language|Task|Constraint|"
    r"Content|Content Segment \d*|Section \d*|Segment \d*|Answers?|Defines?|Wait)\b",
    re.IGNORECASE,
)

_QUESTION_PREFIX = re.compile(
    r"^(?:Question|Câu)\s*\d*[:.-]\s*|^(?:Question|Câu)\s+\d+\s*[:.-]?\s*|^Q\s*\d+[:.*#-]*\s*",
    re.IGNORECASE,
)

_VIETNAMESE_PREFIX = re.compile(
    r"^(?:Vietnamese|Tiếng Việt)\s*[:.-]\s*",
    re.IGNORECASE,
)


def clean_single_query(text: str) -> str:
    """Clean synthetic_queries text block by removing all prompt echo and English scratchpads."""
    if not text or not isinstance(text, str):
        return ""

    lines = text.splitlines()
    questions = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # Strip bullet points, numbering, asterisks
        line = re.sub(r'^(?:[-*•]|\d+[\.)]|\*\s*[-*•]?)\s*', '', line).strip()
        # Strip Question 1: / Câu 1: / Q1: prefixes without stripping Q from Vietnamese words
        line = _QUESTION_PREFIX.sub('', line).strip()
        line = _VIETNAMESE_PREFIX.sub('', line).strip()
        line = re.sub(r'^(?:[-*•]|\d+[\.)])\s*', '', line).strip()

        # 1. Strip topic prefix labels: e.g. Scope):* , Definition):* , Focus on height):* , Focus on 2.3.2.6):
        line = re.sub(r'^.*?\):\*\s*', '', line).strip()
        line = re.sub(
            r'^(?:Focus on|Topic|Scope|Definition|Location|About|Difference|Components|Regulation|Regarding|Combined|Interconnection|Activation|Spacing|Operations|Storage|Placement)[^:."()\n]*\)?[:.)"]+\*?\s*',
            '',
            line,
            flags=re.IGNORECASE,
        ).strip()

        # Drop lines starting with metadata keywords or prompt reflection prefixes
        if _METADATA_PREFIXES.match(line):
            continue

        # 2. Extract Vietnamese part from English / Vietnamese combinations
        # Pattern 2a: English question? / Câu hỏi tiếng Việt? (use space-separated slash to preserve citations like 52/2019/TT-BCA)
        if re.search(r'\s+/\s+', line):
            parts = re.split(r'\s+/\s+', line)
            cand = parts[-1].strip()
            first_part = parts[0].strip()
            if _VN_DIACRITICS.search(cand) and len(cand) > 10:
                if (_ENG_QUESTION_START.match(first_part)
                    or not _VN_DIACRITICS.search(first_part)
                    or re.search(r'\b(?:what|who|where|how|which|when|why|can|is|are)\b', first_part, re.I)):
                    line = cand

        # Pattern 2b: English question? (Câu hỏi tiếng Việt?) or English question (Câu hỏi tiếng Việt?
        if '(' in line:
            m = re.search(r'\(([^)]+)\)?\s*$', line)
            if m:
                cand = m.group(1).strip()
                first_part = line[:m.start()].strip()
                if _VN_DIACRITICS.search(cand) and len(cand) > 10:
                    if (_ENG_QUESTION_START.match(first_part)
                        or not _VN_DIACRITICS.search(first_part)
                        or re.search(r'\b(?:what|who|where|how|which|when|why|can|is|are)\b', first_part, re.I)):
                        line = cand

        # Pattern 2c: If line contains '->', the Vietnamese question is typically after '->'
        if '->' in line:
            candidate = line.split('->')[-1].strip()
            if _VN_DIACRITICS.search(candidate) and len(candidate) > 10:
                line = candidate

        # Clean enclosing quotes, asterisks, backticks
        line = line.strip('"\'*`# \t')

        # 3. Remove lines containing AI reflection notes like (Text says ...)?
        if re.search(r'\(?\s*text says\b', line, re.I):
            continue
        if any(marker in line.lower() for marker in [
            'key elements:', 'key elements', "doesn't specify", "does not specify",
            'for moving equipment and maintenance', 'foam generating containers'
        ]):
            continue

        # Drop questions starting with English interrogatives
        if _ENG_QUESTION_START.match(line):
            continue

        # Strip trailing unclosed parenthesis fragment like ' (?' or ' (what...'
        line = re.sub(r'\s*\([^)]*$', '', line).strip()

        # Drop lines with unmatched parentheses
        if line.count('(') != line.count(')'):
            continue

        # 4. Strip parentheses before checking _VN_DIACRITICS
        text_without_parens = re.sub(r'\(.*?\)', '', line)
        if not _VN_DIACRITICS.search(text_without_parens):
            continue

        # If framing text (outside quotes/backticks/parens) has NO Vietnamese diacritics and length > 8,
        # it is an English question quoting a Vietnamese term
        outside_parens_and_quotes = re.sub(r'\(.*?\)|\"[^\"]*\"|\'[^\']*\'|`[^`]*`', '', line)
        if not _VN_DIACRITICS.search(outside_parens_and_quotes) and len(outside_parens_and_quotes.strip()) > 8:
            continue

        lower = line.lower()
        # Drop scratchpads, prompts, English notes
        if any(marker in lower for marker in [
            'input text:', 'input text', 'source: [', 'source:', 'topic:', 'subject:', 'action:', 'condition:',
            'requirement:', 'document id:', 'appendices:', 'key point', 'what should', 'when is',
            'which standard', 'how many', 'according to', 'who is', 'likely a regulation',
            'table 2:', 'image mention:', 'specific parameter:', 'specific risk:',
            'analyze the request', 'thinking process', 'select and refine', 'tư duy suy luận',
            'general market', 'is no longer available',
        ]):
            continue
        if lower.startswith(('draft ', 'step ', 'note: ', 'wait, ')):
            continue

        # Drop lines with English interrogatives anywhere in query
        if re.search(r'\b(?:what|who|where|how|which)\b', line, re.I):
            continue

        if len(line) < 15:
            continue

        # Must start with an uppercase letter
        clean_first = line.lstrip('"\'“‘#*` \t')
        if not clean_first or not clean_first[0].isupper():
            continue

        # Must have question characteristics
        has_question_word = any(qw in lower for qw in [
            'là gì', 'như thế nào', 'ở đâu', 'khi nào', 'ai', 'bao nhiêu', 'được không',
            'mục đích gì', 'tại sao', 'cần làm gì', 'phải làm gì', 'phải không', 'hay không', 'nào',
            'yêu cầu gì', 'áp dụng để làm gì', 'hãy liệt kê', 'quy định gì', 'bao gồm những',
            'thế nào', 'điều gì', 'ra sao'
        ])
        if not (line.endswith('?') or has_question_word):
            continue

        # Skip truncated cutoffs
        if not line.endswith('?') and line.endswith(
            (' các', ' những', ' và', ' của', ' có', ' là', ' cho', ' tại', ' trong', ' về', ' được', ' quy', ' xác', ' hợp')
        ):
            continue

        line = line.rstrip(' :,;."”\'’')
        if not line.endswith('?'):
            line += '?'

        line = re.sub(r'\?+', '?', line)
        questions.append(line)

    seen = set()
    deduped = []
    for q in questions:
        if q not in seen:
            seen.add(q)
            deduped.append(q)

    return '\n'.join(deduped)


def get_export_dirs():
    if os.path.exists("/app/exports/json"):
        return Path("/app/exports/json"), Path("/app/exports/markdown")
    return Path("/home/vvc/Public/exports/json"), Path("/home/vvc/Public/exports/markdown")


def clean_target_json_files(json_dir: Path):
    """Clean contaminated synthetic_queries in JSON export files."""
    target_files = [
        "ROOT_3621_QĐ-BKHCN.json",
        "ROOT_Luat_50-2014-QH13_Luat_Xay_dung_18-6-2014.json",
        "ROOT_01A_20241014_So_tay_huong_dan_cac_thu_tuc_ve_NOXH_tren_dia_ban_TPHP_bieumau.json",
        "ROOT_52_2019_TT-BCA.json",
    ]
    cleaned_chunks_by_file = {}

    for fname in target_files:
        fpath = json_dir / fname
        if not fpath.exists():
            logger.warning(f"File not found: {fpath}")
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)

        modified_count = 0
        cleaned_map = {}
        for chunk in data.get("chunks", []):
            cid = chunk.get("chunk_id")
            if not cid:
                continue
            old_sq = chunk.get("synthetic_queries", "")
            new_sq = clean_single_query(old_sq) if old_sq else ""
            if new_sq != old_sq:
                chunk["synthetic_queries"] = new_sq
                modified_count += 1
            cleaned_map[cid] = new_sq

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(f"Cleaned {modified_count} chunks in {fname}")
        cleaned_chunks_by_file[fname] = (data.get("doc_id"), cleaned_map)

    return cleaned_chunks_by_file


def resolve_hidden_files(json_dir: Path, md_dir: Path):
    """Handle .._52_2019_TT-BCA files: normalize or clean duplicates."""
    # 1. Remove duplicates from OOM test
    oom_json = json_dir / ".._52_2019_TT-BCA_0a241d.json"
    oom_md = md_dir / ".._52_2019_TT-BCA_0a241d.md"
    if oom_json.exists():
        oom_json.unlink()
        logger.info(f"Removed duplicate OOM artifact: {oom_json}")
    if oom_md.exists():
        oom_md.unlink()
        logger.info(f"Removed duplicate OOM artifact: {oom_md}")

    # 2. Normalize .._52_2019_TT-BCA.json -> ROOT_52_2019_TT-BCA.json
    raw_json = json_dir / ".._52_2019_TT-BCA.json"
    raw_md = md_dir / ".._52_2019_TT-BCA.md"
    norm_json = json_dir / "ROOT_52_2019_TT-BCA.json"
    norm_md = md_dir / "ROOT_52_2019_TT-BCA.md"

    target_json = raw_json if raw_json.exists() else (norm_json if norm_json.exists() else None)
    if target_json and target_json.exists():
        with open(target_json, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["doc_id"] = "ROOT/52/2019/TT-BCA"
        if data.get("original_path", "").startswith("../"):
            data["original_path"] = data["original_path"].replace("../", "ROOT/", 1)
        cleaned_sq_count = 0
        for c in data.get("chunks", []):
            c["doc_id"] = "ROOT/52/2019/TT-BCA"
            if c.get("chunk_id", "").startswith("../52/2019/TT-BCA"):
                c["chunk_id"] = c["chunk_id"].replace("../52/2019/TT-BCA", "ROOT/52/2019/TT-BCA")
            if "../52/2019/TT-BCA" in c.get("hierarchy_path", ""):
                c["hierarchy_path"] = c["hierarchy_path"].replace("../52/2019/TT-BCA", "ROOT/52/2019/TT-BCA")
            if c.get("text", "").startswith("[../52/2019/TT-BCA]"):
                c["text"] = c["text"].replace("[../52/2019/TT-BCA]", "[ROOT/52/2019/TT-BCA]", 1)

            old_sq = c.get("synthetic_queries", "")
            if old_sq:
                new_sq = clean_single_query(old_sq)
                if new_sq != old_sq:
                    c["synthetic_queries"] = new_sq
                    cleaned_sq_count += 1

        with open(norm_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        if raw_json.exists() and raw_json != norm_json:
            raw_json.unlink()
        logger.info(f"Normalized {target_json} -> {norm_json} ({cleaned_sq_count} queries cleaned, chunk IDs aligned)")

    target_md = raw_md if raw_md.exists() else (norm_md if norm_md.exists() else None)
    if target_md and target_md.exists():
        content = target_md.read_text(encoding="utf-8")
        content = content.replace("# Document: ../52/2019/TT-BCA", "# Document: ROOT/52/2019/TT-BCA")
        content = content.replace("[../52/2019/TT-BCA]", "[ROOT/52/2019/TT-BCA]")
        content = content.replace("- **Original Path:** ../", "- **Original Path:** ROOT/")
        norm_md.write_text(content, encoding="utf-8")
        if raw_md.exists() and raw_md != norm_md:
            raw_md.unlink()
        logger.info(f"Normalized {target_md} -> {norm_md}")


def update_milvus_entities(cleaned_chunks_by_file: dict, milvus_uri: str = "http://localhost:19530"):
    """Update modified entities in Milvus legal_docs_v11 collection."""
    collection_name = "legal_docs_v11"
    client = MilvusClient(uri=milvus_uri)

    total_upserted = 0
    for fname, (doc_id, chunk_map) in cleaned_chunks_by_file.items():
        if not doc_id:
            continue
        logger.info(f"Querying Milvus entities for doc_id: {doc_id}")
        entities = client.query(
            collection_name=collection_name,
            filter=f'doc_id == "{doc_id}"',
            output_fields=["*"],
            limit=2000,
        )
        logger.info(f"Retrieved {len(entities)} entities for {doc_id}")

        modified_entities = []
        for ent in entities:
            cid = ent.get("chunk_id")
            if cid in chunk_map:
                new_sq = chunk_map[cid]
                if ent.get("synthetic_queries") != new_sq:
                    ent["synthetic_queries"] = new_sq
                    modified_entities.append(ent)

        if modified_entities:
            logger.info(f"Upserting {len(modified_entities)} modified entities for {doc_id} to Milvus")
            batch_size = 100
            for i in range(0, len(modified_entities), batch_size):
                batch = modified_entities[i:i + batch_size]
                client.upsert(collection_name=collection_name, data=batch)
            total_upserted += len(modified_entities)
            logger.info(f"Successfully upserted {len(modified_entities)} entities for {doc_id}")
        else:
            logger.info(f"No entities needed updating for {doc_id}")

    client.close()
    logger.info(f"Total entities updated in Milvus: {total_upserted}")
    return total_upserted


def main():
    json_dir, md_dir = get_export_dirs()
    logger.info(f"Target json_dir: {json_dir}")
    logger.info(f"Target md_dir: {md_dir}")

    # 1. Resolve hidden files and normalize ROOT_52_2019_TT-BCA
    resolve_hidden_files(json_dir, md_dir)

    # 2. Clean JSON files
    cleaned = clean_target_json_files(json_dir)

    # 3. Update Milvus
    milvus_uri = os.environ.get("MILVUS_URI", "http://localhost:19530")
    update_milvus_entities(cleaned, milvus_uri)

    logger.info("Cleaning and Milvus update complete!")


if __name__ == "__main__":
    main()
