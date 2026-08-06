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

    # [Fix #5a] Strip base64 binary strings EARLY (before original_len calc)
    # so the Safety Guard doesn't block legitimate base64 removal
    # Base64 strings: 60+ chars of [A-Za-z0-9+/=] with no spaces
    text = re.sub(
        r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{60,}={0,2}(?=[^A-Za-z0-9+/]|$)',
        '[BASE64_DATA]',
        text
    )

    # [Fix #1 post-hoc] Strip prompt echo EARLY (before original_len)
    # Prevents Safety Guard from rolling back when a page is mostly prompt text
    _PROMPT_ECHO_PATTERNS = [
        r'(?im)^\s*\d+\.\s+(?:Giữ nguyên cấu trúc|BẢNG BIỂU|KHÔNG dùng markdown|Giữ nguyên số hiệu).*$',
        r'(?im)^.*CHỈ VĂN BẢN THUẦN TÚY.*$',
        r'(?im)^.*Bỏ QUA HOÀN TOÀN.*$',
        r'(?im)^(####\s*)?9\.\s+CHỈ VĂN BẢN THUẦN TÚY.*',
        r'(?im)^\s*(?:Bỏ qua hoàn toàn|KHÔNG trích xuất)\s*(?:.*)?:-?[^\n]*$',
    ]
    for _p in _PROMPT_ECHO_PATTERNS:
        text = re.sub(_p, '', text)

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

    # [P4] Strip CÔNG BÁO header/footer lines (Công báo scan artifacts)
    # Pattern: "82   CÔNG BÁO/Số 997 + 998/Ngày 27-12-2019" or standalone
    text_cleaned = re.sub(
        r'(?m)^\s*\d{0,4}\s*CÔNG BÁO\/Số\s+[\d\s+]+\/Ngày[^\n]*\n?',
        '', text_cleaned
    )
    text_cleaned = re.sub(
        r'(?m)^\s*CÔNG BÁO\s*\/[^\n]*\n?',
        '', text_cleaned
    )

    # [P3] Fix cross-line word merge: when a line ends with a lowercase char
    # and next line starts with Uppercase+lowercase without space — add a space
    # This handles OCR line-break joins like: "vềbảo" → "về bảo"
    # Negative lookahead exempts technical unit suffixes: dBm, kHz, MHz, nGy, kVp...
    _TECH_UNIT_SUFFIXES = r'(?!(Bm|Hz|Gy|Vp|Pa\b|Wb|Nm|Am|Cd|Wp|VA\b))'
    text_cleaned = re.sub(
        r'([a-zà-ỹđắặẵẳăầấẩẫậáàảãạéèẻẽẹíìỉĩịóòỏõọúùủũụýỳỷỹỵ])'
        + _TECH_UNIT_SUFFIXES +
        r'([A-ZĐẮẶẴẲĂẦẤẨẪẬÁÀẢÃẠÉÈẺẼẸÍÌỈĨỊÓÒỎÕỌÚÙỦŨỤÝỲỶỸỴ][a-zà-ỹđ])',
        r'\1 \3',
        text_cleaned
    )

    # [P1] Ensure paragraph breaks before numbered list items (1. 2. 3.)
    # When a numbered item immediately follows another line with no blank line
    text_cleaned = re.sub(
        r'(?m)([^\n])\n(\d+\.\s+[A-ZĐÀÁẢÃẠĂẮẶ])',
        r'\1\n\n\2',
        text_cleaned
    )
    # Ensure paragraph break before lettered sub-items (a. b. c.)
    text_cleaned = re.sub(
        r'(?m)([^\n])\n([a-z]\)\s+\S)',
        r'\1\n\n\2',
        text_cleaned
    )

    # [Fix #4] Vietnamese preposition/conjunction word-merge fix
    # Targeted approach for most common merge patterns found in corpus audit
    _COMMON_MERGES = [
        # Prepositions + next word start
        (r'(?<![A-Z])(của)(các|cơ|tổ|cá|đơn|bộ|nhà|nước|người|quy|nhưng)', r'\1 \2'),
        (r'(?<![A-Z])(và)(hệ|các|tổ|cơ|đơn|bộ|nhà|phục|việc|theo|quy|điều|được|chỉ|máy|cấu|khả|số)', r'\1 \2'),
        (r'(?<![A-Z])(để)(có|thực|phục|đảm|đáp|đạt|cung|kiểm|xử|thi|đoạt)', r'\1 \2'),
        (r'(?<![A-Z])(về)(mã|quy|yêu|phạm|đối|các|điều|tiêu|phương)', r'\1 \2'),
        (r'(?<![A-Z])(là)(một|cơ|số|các|chính|tổ|nhà|nguồn|khả|để|cần)', r'\1 \2'),
        (r'(?<![A-Z])(trong)(khi|các|việc|phạm|và|suốt)', r'\1 \2'),
        (r'(?<![A-Z])(có)(thể|nhiều|đầy|tối|thể|được)', r'\1 \2'),
        (r'(?<![A-Z])(được)(các|thiết|thực|xác|quy|sử|cấp|áp)', r'\1 \2'),
        (r'(?<![A-Z])(của)(quy|các|cơ)', r'\1 \2'),
        # Very common standalone merges found in corpus (top frequency)
        (r'\bcóthể\b', 'có thể'),
        (r'\blàmột\b', 'là một'),
        (r'\bvàchỉ\b', 'và chỉ'),
        (r'\bcủaquy\b', 'của quy'),
        (r'\bvàmáy\b', 'và máy'),
        (r'\bđểđáp\b', 'để đáp'),
        (r'\bcóđầy\b', 'có đầy'),
        (r'\bvàcấu\b', 'và cấu'),
        (r'\bvàkhả\b', 'và khả'),
        (r'\bvàsau\b', 'và sau'),
        (r'\bcómột\b', 'có một'),
        (r'\blàcần\b', 'là cần'),
        (r'\bđượcáp\b', 'được áp'),
        # Compound word merges common in QCVN docs
        (r'(phục vụ|phụcvụ)(kết|cho|các|đáp|được|đo)', r'phục vụ \2'),
        (r'(sai số|saisof)(tần|tốc)', r'sai số \2'),
        (r'(bao gồm|baogồm)(các|cả|một)', r'bao gồm \2'),
        (r'(?i)(một số|mộtsố)(quy|điều|vấn|hành|trường)', r'một số \2'),
        # ── BGTVT Thông tư corpus patterns (2026-03 audit) ──
        (r'\bcamáy\b', 'ca máy'),
        (r'\bnhucầu\b', 'nhu cầu'),
        (r'\bkýkết\b', 'ký kết'),
        (r'\bsốnội\b', 'số nội'),
        (r'\bđầutư\b', 'đầu tư'),
        (r'\bcơcấu\b', 'cơ cấu'),
        (r'\bkỹthuật\b', 'kỹ thuật'),
        (r'\bđảmbảo\b', 'đảm bảo'),
        # Strip extra spaces from earlier fixes (cleanup)
        (r'  +', r' '),
    ]
    for pattern, repl in _COMMON_MERGES:
        text_cleaned = re.sub(pattern, repl, text_cleaned)

    # [Fix #5a base64 already done above]
    # [Fix #1 prompt echo already done above]

    cleaned = text_cleaned.strip()

    # Absolute Quality Safety Guard: Check character ratio
    # If is_summary is True, we allow more aggressive cleaning as summaries are small and often filled with junk
    ratio_threshold = 0.50 if is_summary else 0.30

    if original_len > 100:
        removed_len = original_len - len(cleaned)
        ratio = removed_len / original_len

        if ratio > ratio_threshold:
            # ── Anchor-Based Rollback Guard ──
            # Before rolling back, check if cleaned text contains Vietnamese legal content.
            # If legal anchors are found, the stripping removed AI preamble, not real content.
            # Only rollback if NO legal content is detectable after cleaning.
            _LEGAL_ANCHORS = re.compile(
                r'(?:(?:Điều|Khoản|Chương|Mục|Phần|Tiếu mục)\s+\d+'
                r'|\d+\.\d+[\s.]'   # numbered sections like 3.1, 4.2.
                r'|QCVN|TCVN|Nghị định|Thông tư|Quyết định'
                r'|(?:ban hành|quy định|hướng dẫn))',
                re.IGNORECASE | re.UNICODE,
            )
            has_legal_content = bool(_LEGAL_ANCHORS.search(cleaned))

            if has_legal_content:
                # Stripping removed AI preamble, not legal content — keep cleaned version
                logger.info(
                    f"HIGH_CLEANING_RATIO for {source_id}: {ratio:.1%} stripped "
                    f"but legal anchors found — keeping cleaned text."
                )
            else:
                # No legal content detected → rolling back to prevent data loss
                audit_logger.warning(
                    f"HIGH_CLEANING_RATIO detected for {source_id}: {ratio:.2%} stripped ({removed_len}/{original_len} chars). "
                    f"No legal anchors in cleaned text — Safety Guard rollback to original."
                )
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
