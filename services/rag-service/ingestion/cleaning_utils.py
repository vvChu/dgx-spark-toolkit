import re
import logging
import os

# Set up audit logger
audit_logger = logging.getLogger("ingestion_audit")
audit_logger.setLevel(logging.WARNING)
if not audit_logger.handlers:
    # Ensure logs directory exists
    os.makedirs("logs", exist_ok=True)
    fh = logging.FileHandler("logs/ingestion_audit.log")
    fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    audit_logger.addHandler(fh)

logger = logging.getLogger(__name__)

def clean_llm_text(text: str, source_id: str = "unknown", is_summary: bool = False) -> str:
    """
    Robustly clean LLM output for ingestion.
    Strips reasoning traces, markdown fences, and conversational filler.
    Includes Absolute Quality Safety Guard: character-ratio check.
    """
    if not text:
        return ""

    # ── PRE-STRIP: Remove <think>/<thought> blocks BEFORE measuring original_len ──
    # These are NEVER legal content, so removing them should not trigger the Safety Guard.
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    # Also strip orphaned closing tags (e.g. when opening tag was already stripped)
    text = re.sub(r'</think>', '', text)
    text = re.sub(r'</thought>', '', text)

    original_len = len(text)
    
    # 1. (Legacy pattern — kept for compatibility, already handled above)
    text_cleaned = text
    
    # 2. Strip "Thinking Process:" or "Reasoning:" blocks and everything after them if they contain prompts
    # Often Qwen 35B outputs a detailed "Thinking Process" tree.
    thought_patterns = [
        r'(?i)Thinking Process:.*?\n\n',
        r'(?i)Analyze the Request:.*?\n\n',
        r'(?i)Transcription:.*?\n\n',
        r'(?i)Based on the visual content.*?\n',
        r'(?i)I see a document titled.*?\n'
    ]
    for tp in thought_patterns:
        text_cleaned = re.sub(tp, '', text_cleaned, flags=re.DOTALL)

    # 3. Remove markdown code blocks (e.g. ```text ... ```)
    text_cleaned = re.sub(r'```(?:\w+)?\n?(.*?)\n?```', r'\1', text_cleaned, flags=re.DOTALL)

    # 4. Strip common conversational patterns (Giga-Aggressive anchor-less)
    # This strips the pattern and anything following it on the same line/block if appropriate
    patterns_to_nuke = [
        # Table analysis monologue patterns
        r'(?i)\d+\.\s+\*\*Analyze.*?\*\*.*',
        r'(?i).*?Analyze the visible table.*',
        r'(?i).*?There is a horizontal line.*',
        r'(?i).*?Column \d+.*?Column \d+.*',
        # English reasoning traces (found in summary outputs)
        r'(?i).*?Internal Monologue.*',
        r'(?i).*?Drafting the Summary.*',
        r'(?i).*?Task Interpretation:?.*',
        r'(?i).*?Strategy:?\s+I must.*',
        r'(?i).*?Problem:?\s+There is no.*',
        r'(?i).*?This is \*not\*.*',
        r'(?i).*?I must summarize.*',
        r'(?i).*?Need to capture.*',
        r'(?i).*?Need to state what.*',
        r'(?i).*?Therefore, a summary.*',
        r'(?i).*?However, the prompt asks.*',
        r'(?i).*?It lacks the actual substance.*',
        # General patterns
        r'(?i).*?Based on the visual content.*',
        r'(?i).*?Based on the visual input.*',
        r'(?i).*?I see a document titled.*',
        r'(?i).*?Analyze the Request:?.*',
        r'(?i).*?Transcription:?.*',
        r'(?i).*?Analyze the Input Text:?.*',
        r'(?i).*?Evaluate the Input Text:?.*',
        r'(?i).*?Refinement:?.*',
        r'(?i).*?Correction:?.*',
        r'(?i).*?Double-check the characters:?.*',
        r'(?i).*?Let\'s assume the user wants.*',
        r'(?i).*?The user wants me to.*',
        r'(?i).*?As an AI.*',
        r'(?i).*?I will format this.*',
        r'(?i).*?I need to transcribe.*',
        r'(?i).*?I will read the text.*',
        # Vision LLM monologue patterns (found in audit of exports)
        r'(?i).*?I need to look at the \*image\*.*',
        r'(?i).*?looking closely at the.*',
        r'(?i).*?I should use the image.*',
        r'(?i).*?I will replace it entirely.*',
        r'(?i).*?I will reconstruct.*',
        r'(?i).*?I will ensure the indentation.*',
        r'(?i).*?I will combine the split lines.*',
        r'(?i).*?I will respect this distinction.*',
        r'(?i).*?Wait, looking at the.*',
        r'(?i).*?Wait, looking closely.*',
        r'(?i).*?The provided OCR text is.*',
        r'(?i).*?The OCR text provided in the prompt.*',
        r'(?i).*?The prompt text provided is.*',
        r'(?i).*?The prompt asks to.*',
        r'(?i).*?The prompt says.*',
        r'(?i).*?One detail:.*',
        r'(?i).*?Final check on the text.*',
        r'(?i).*?Okay, ready to generate.*',
        r'(?i).*?Let\'s assemble the final text.*',
        r'(?i).*?Ready to generate.*',
        r'(?i)\*\*Plan:\*\*',
        r'(?i)\*\*Structure:.*?\*\*',
        r'(?i)\*\*OCR Text:\*\*.*',
        r'(?i)\*\*Reconstruct the.*?\*\*.*',
        r'(?i)Here is the corrected text:?',
        r'(?i)Nội dung đã chỉnh sửa:?',
        r'(?i)Analysis of the document:?',
        r'(?i)Thinking Process:?',
        r'(?i)Analysis:?',
        r'(?i)Tôi đã sửa lỗi OCR cho bạn:?',
        r'(?i)Tóm tắt văn bản:?',
        # Vietnamese system prompt leakage (LLM echoing instructions)
        r'(?i).*?Trích xuất TOÀN BỘ nội dung.*',
        r'(?i).*?TUYỆT ĐỐI KHÔNG thêm nhận xét.*',
        r'(?i).*?KHÔNG mô tả font.*',
        r'(?i).*?giữ nguyên thứ tự từ trên xuống.*',
        r'(?i).*?Giữ nguyên tiêu đề.*chương.*điều.*',
        r'(?i).*?KHÔNG thêm bất kỳ nội dung nào.*',
        r'(?i).*?Trả về TOÀN BỘ nội dung.*',
        r'(?i).*?Chỉ trả về nội dung văn bản.*',
    ]
    
    for pattern in patterns_to_nuke:
        text_cleaned = re.sub(pattern, '', text_cleaned)
    
    # Cleanup any leftover "Thinking Process" headers that might have been missed
    text_cleaned = re.sub(r'(?i)Thinking Process:.*?(?=\n\n|\n[A-Z]|\Z)', '', text_cleaned, flags=re.DOTALL)

    # 5. Strip LLM numbered analysis steps (e.g. "1.  **\n    *   **Header:")
    text_cleaned = re.sub(r'^\s*\d+\.\s+\*\*.*$', '', text_cleaned, flags=re.MULTILINE)
    # Strip orphaned bullet-point analysis lines
    text_cleaned = re.sub(r'^\s*\*\s+.*?(?:Header Info|Key information|Identify key|Document type|Issuing Authority|Responsibility|Recipients|Sender|Date:).*$', '', text_cleaned, flags=re.MULTILINE)
    
    # 6. Strip isolated page numbers at start or end of block
    text_cleaned = re.sub(r'^\s*\d+\s*\n', '', text_cleaned)
    text_cleaned = re.sub(r'\n\s*\d+\s*$', '', text_cleaned)
    text_cleaned = re.sub(r'(?i)^\s*Trang\s+\d+.*?\n', '', text_cleaned)

    cleaned = text_cleaned.strip()
    
    # Absolute Quality Safety Guard: Check character ratio
    # If is_summary is True, we allow more aggressive cleaning as summaries are small and often filled with junk
    ratio_threshold = 0.50 if is_summary else 0.30
    
    if original_len > 100: 
        removed_len = original_len - len(cleaned)
        ratio = removed_len / original_len
        
        if ratio > ratio_threshold:
            audit_logger.warning(
                f"HIGH_CLEANING_RATIO detected for {source_id}: {ratio:.2%} stripped ({removed_len}/{original_len} chars). "
                f"Safety Guard triggered: returning ORIGINAL text to prevent legal data loss."
            )
            # Only return original if NOT a summary. Summaries are safer to clean aggressively.
            if not is_summary:
                return text.strip()

    if len(cleaned) < original_len:
        logger.info(f"Cleaned LLM text for {source_id}: stripped {original_len - len(cleaned)} characters of AI monologue.")

    # ── QF-8: Summary Truncation Guard ──
    # If summary ends with an incomplete delimiter, trim to last complete sentence
    if is_summary and cleaned and cleaned[-1] in ('(', ',', ';', '-', '–', ':'):
        last_period = cleaned.rfind('.')
        if last_period > len(cleaned) * 0.5:
            cleaned = cleaned[:last_period + 1]
            logger.info(f"Trimmed truncated summary for {source_id} at position {last_period}")

    return cleaned
