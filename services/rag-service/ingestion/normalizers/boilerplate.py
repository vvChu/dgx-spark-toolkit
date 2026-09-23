"""Boilerplate and noise removal for Vietnamese legal documents.

Removes government document headers, distribution lists, signer blocks,
digital signatures, date/page noise, and template dots.
"""
import re
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Boilerplate / Header Noise Removal
# ---------------------------------------------------------------------------

_BOILERPLATE_EXACT = [
    'CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM',
    'CONG HOA XA HOI CHU NGHIA VIET NAM',
    'ĐỘC LẬP - TỰ DO - HẠNH PHÚC',
    'Độc lập - Tự do - Hạnh phúc',
    'DOC LAP - TU DO - HANH PHUC',
    '---oOo---', '———', '----',
]
_BOILERPLATE_UPPER = [s.upper() for s in _BOILERPLATE_EXACT]

_BOILERPLATE_REGEX = [
    re.compile(r'(?i)^\s*Độc\s+lập\s*[-–—]\s*Tự\s+do\s*[-–—]\s*Hạnh\s+phúc\s*$'),
    re.compile(r'(?i)^\s*Số\s*:\s*\d+.*$'),
    re.compile(r'(?i)^\s*V/v\s*:.*$'),
    re.compile(r'(?i)^\s*(?:Hà Nội|Đà Nẵng|TP\.?\s*Hồ Chí Minh|Thành phố\s+\w+),?\s*ngày.*$'),
    re.compile(r'(?i)^\s*Kính gửi\s*:.*$'),
    re.compile(r'(?i)^\s*Nơi nhận\s*:.*$'),
    re.compile(r'(?i)^\s*(?:BỘ|UBND|ỦY BAN|SỞ|PHÒNG|HỘI ĐỒNG)\s+[A-ZĐÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ\s]+$'),
    re.compile(r'(?i)^\s*CHÍNH PHỦ\s*$'),
    re.compile(r'(?i)^\s*THỦ TƯỚNG CHÍNH PHỦ\s*$'),
    re.compile(r'(?i)^\s*QUỐC HỘI\s*$'),
    re.compile(r'(?i)^\s*Người ký\s*:.*$'),
    re.compile(r'(?i)^\s*Thời gian ký\s*:.*$'),
    re.compile(r'(?i)^\s*Email\s*:.*@.*$'),
    re.compile(r'(?i)^\s*Cơ quan\s*:.*$'),
    re.compile(r'^\s*-\s*(?:UBND|Văn phòng|Hội đồng|Viện|Ủy ban|Ngân hàng|Cơ quan|VPCP|Các Vụ|Cổng|Lưu).*[;,:]\\s*$'),
    re.compile(r'(?i)^.*CỔNG\s+THÔNG\s+TIN\s+ĐIỆN\s+TỬ.*$'),
    re.compile(r'(?i)^.*chinhphu\.vn.*$'),
    re.compile(r'(?i)^.*thongtinchinhphu@.*$'),
    re.compile(r'(?i)^\s*VGP\s*$'),
    re.compile(r'(?i)^.*CHINHPHU\.VN.*$'),
    re.compile(r'^\s*[A-ZĐTTBHCN]{2,8}\s*\(\s*\d+\s*\)\s*$'),
    re.compile(r'(?i)^\s*-?\s*Lưu\s*:.*$'),
    re.compile(r'(?i)^.*ngày.*(?:KT\.|TM\.|Ký thay)\s*(?:THỦ TƯỚNG|BỘ TRƯỞNG|CHỦ TỊCH).*$'),
    re.compile(r'(?i)^\s*(?:Ký bởi|Người ký)\s*:.*(?:Email|Cơ quan|Thời gian ký).*$'),
    re.compile(r'^\s*(?:QCVN|TCVN|TCCS)\s+\d+[:\-]\d{4}(?:\/[A-ZĐ]+)?\s*$'),
]


def strip_document_boilerplate(text: str) -> str:
    """Remove Vietnamese government document header boilerplate from text.

    Only processes the first ~600 chars to avoid stripping legitimate content.
    """
    if not text or len(text) < 20:
        return text

    lines = text.split('\n')
    cleaned_lines = []
    chars_seen = 0
    boilerplate_zone = True

    for line in lines:
        stripped = line.strip()
        chars_seen += len(line) + 1

        if chars_seen > 600:
            boilerplate_zone = False

        if boilerplate_zone and stripped:
            upper = stripped.upper()
            if any(bp in upper for bp in _BOILERPLATE_UPPER):
                continue
            if any(rx.match(stripped) for rx in _BOILERPLATE_REGEX):
                continue
            if len(stripped) < 60 and stripped == stripped.upper() and not any(c.isdigit() for c in stripped):
                if not re.match(r'^[ĐÐ]iều|^Chương|^Mục|^Phần', stripped):
                    continue

        if not stripped and boilerplate_zone:
            continue

        cleaned_lines.append(line)

    result = '\n'.join(cleaned_lines).strip()
    return result if result else text


def strip_noi_nhan_block(text: str) -> str:
    """Remove 'Nơi nhận:' distribution list block from anywhere in text."""
    if not text or 'Nơi nhận' not in text and 'nơi nhận' not in text.lower():
        return text

    lines = text.split('\n')
    result = []
    in_noi_nhan = False

    for line in lines:
        stripped = line.strip()
        if re.match(r'(?i)^\s*Nơi nhận\s*:', stripped):
            in_noi_nhan = True
            continue
        if in_noi_nhan:
            if re.match(r'^\s*-\s+', stripped) and (stripped.endswith(';') or stripped.endswith(',') or stripped.endswith('.') or 'Lưu' in stripped):
                continue
            if len(stripped) < 80 and stripped.endswith(';'):
                continue
            if len(stripped) < 80 and re.match(r'^\s*-\s+', stripped):
                continue
            in_noi_nhan = False
        result.append(line)

    return '\n'.join(result)


def strip_signer_block(text: str) -> str:
    """Remove signer block (KT./TM./PHÓ THỦ TƯỚNG + name) from end of text.

    SAFETY: Only operates on the LAST 500 chars.
    """
    if not text or len(text) < 100:
        return text

    TAIL_SIZE = 500
    if len(text) <= TAIL_SIZE:
        head = ''
        tail = text
    else:
        split_pos = text.rfind('\n', len(text) - TAIL_SIZE, len(text) - 200)
        if split_pos == -1:
            split_pos = len(text) - TAIL_SIZE
        head = text[:split_pos]
        tail = text[split_pos:]

    _SIGNER_START = re.compile(
        r'^\s*(?:KT\.|TM\.|Ký thay\.?|Q\.)\s*'
        r'(?:TH\s*Ủ\s*T\s*Ư\s*Ớ\s*NG|CH\s*Ủ\s*T\s*Ị\s*CH|B\s*Ộ\s*TR\s*Ư\s*Ở\s*NG|CH\s*Í\s*NH\s*PH\s*Ủ|'
        r'THỦ TƯỚNG|CHỦ TỊCH|BỘ TRƯỞNG|CHÍNH PHỦ)',
        re.MULTILINE | re.IGNORECASE
    )

    match = _SIGNER_START.search(tail)
    if match:
        tail = tail[:match.start()].rstrip()
        logger.info(f"  Stripped signer block from end of text ({len(text) - len(head) - len(tail)} chars removed)")

    return (head + tail).strip()


_DIGITAL_SIGNATURE_RE = re.compile(
    r'(?:Ký bởi|Người ký)\s*:.+?(?:\d{2}\.\d{2}\.\d{4}\s+\d{2}:\d{2}:\d{2}\s*[+\-]\d{2}:\d{2})',
    re.IGNORECASE | re.DOTALL
)


def strip_digital_signature(text: str) -> str:
    """Strip combined digital signature metadata from anywhere in text."""
    if not text:
        return text
    cleaned = _DIGITAL_SIGNATURE_RE.sub('', text)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip() if cleaned.strip() else text


# ---------------------------------------------------------------------------
# Date/Page Metadata Noise
# ---------------------------------------------------------------------------

_DATE_PAGE_NOISE_PATTERNS = [
    re.compile(r'\n\s*\d{2}\s+\d{2}\s+\d{2}\s+\d{4}\s+\d{4}\s*$'),
    re.compile(r'\n\s*\d{2}\s+\d{2}\s+\d{2}\s*$'),
    re.compile(r'^\s*\d{1,3}\s*$', re.MULTILINE),
]


def strip_date_page_noise(text: str) -> str:
    """Strip fragmented date/page number metadata from chunk text."""
    if not text:
        return text
    for pat in _DATE_PAGE_NOISE_PATTERNS:
        text = pat.sub('', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Template Dotted Line Stripping
# ---------------------------------------------------------------------------

def strip_template_dots(text: str) -> str:
    """Strip form template fill patterns (repeated dots/periods)."""
    if not text:
        return text
    text = re.sub(r'(?:\.\s*){20,}', '', text)
    text = re.sub(r'(?:\.\s){10,}', '', text)
    return text


# ---------------------------------------------------------------------------
# Vision LLM Random Emoji Stripping
# ---------------------------------------------------------------------------

_INJECTED_EMOJIS = [
    '\U0001f30b',  # 🌋
    '\U0001f525',  # 🔥
    '\U0001f4a5',  # 💥
    '\u26a1',      # ⚡
    '\U0001f30a',  # 🌊
    '\U0001f3af',  # 🎯
    '\U0001f680',  # 🚀
    '\U0001f389',  # 🎉
    '\U0001f3c6',  # 🏆
    '\U0001f31f',  # 🌟
    '\U0001f48e',  # 💎
    '\U0001f3ae',  # 🎮
    '\u2b50',      # ⭐
]


def strip_random_emojis(text: str) -> str:
    """Remove random emojis injected by Vision LLM as OCR artifacts."""
    if not text:
        return text
    for emoji in _INJECTED_EMOJIS:
        text = text.replace(emoji, '')
    return text


# ---------------------------------------------------------------------------
# AI Monologue and Reasoning Trace Stripping
# ---------------------------------------------------------------------------

_AI_PATTERNS_VN = [
    # Introductory/conversational phrases
    r"(?i)(?:^|\n)\s*Dưới đây là[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Xin lỗi[^.]*[.!]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Tôi xin[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Theo yêu cầu[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Nội dung chính[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Bảng dưới đây[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Tôi đã[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Tôi sẽ[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Tóm tắt[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Như bạn[^.]*[.:]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Chào bạn[^.]*[.!]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Dạ,[^.]*[.!]?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Vâng,[^.]*[.!]?\s*(?:\n|$)",
    # Instruction echo patterns
    r"(?i)(?:^|\n)\s*Trích xuất TOÀN BỘ[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*TUYỆT ĐỐI KHÔNG[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*KHÔNG mô tả font[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*giữ nguyên thứ tự[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*KHÔNG thêm bất kỳ[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Chỉ trả về nội dung[^\n]*(?:\n|$)",
    # Summary leakage
    r"(?i)(?:^|\n)\s*Nội dung đã chỉnh sửa:?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Tóm tắt văn bản:?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Here is the corrected text:?\s*(?:\n|$)",
]

_AI_PATTERNS_EN = [
    r"(?i)(?:^|\n)\s*Certainly[,!]?\s+(?:here|I|let)[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*I'll\s[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*As an AI[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Here is[^\n]*:\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Here's[^\n]*:\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*I cannot[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*I would[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*I will[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*I need to[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Let me[^\n]*(?:\n|$)",
    # LLM reasoning traces
    r"(?i)(?:^|\n)\s*Thinking Process:?[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Analysis:?\s*(?:\n|$)",
    r"(?i)(?:^|\n)\s*\*\*Plan:\*\*[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*\*\*Structure:[^\n]*\*\*[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*\*\*OCR Text:\*\*[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*\*\*Reconstruct the[^\n]*\*\*[^\n]*(?:\n|$)",
    r"(?i)(?:^|\n)\s*Based on the visual (?:content|input)[^\n]*(?:\n|$)",
    # OCR prompt and transcription notes leakage
    r"(?mi)^\s*(?:\d+\.\s*)?Exclude\s+[\"'].*$",
    r"(?mi)^\s*\*?\s*\*\*Header:\*\*\s*\(Exclude\s+\d+\).*$",
    r"(?mi)^\s*\*?\s*(?:\*\*)?(?:Top|Bottom)\b.*?(?:Page number|\"\d+\"|\bcorner\b).*$",
    r"(?mi)^\s*\*?\s*Page number\s+.*$",
    r"(?mi)^\s*\*?\s*(?:Transcribe|Start from item|Maintain the numbering|Ensure line breaks)\b.*$",
    r"(?mi)^\s*\*?\s*(?:Under Điều|(?:do\s+)?not use Markdown headers)\b.*$",
    r"(?mi)^\s*I will combine these into the final output.*$",
    r"(?mi)^\s*-\s*Ignore headers/footers like page numbers.*$",
    r"(?mi)^\s*\*?\s*The image shows a page from a legal document.*$",
]

OCR_PROMPT_PATTERNS = [
    r"(?mi)^\s*[-*]?\s*(?:Did I include|Is the structure|Let's assemble|Let's refine|This looks correct|KHÔNG dùng markdown).*$",
    r"(?mi)^\s*[-*]?\s*(?:The\s+)?text starts (?:mid|with item).*$",
    r"(?mi)^\s*[-*]?\s*Point \d+:.*$",
    r"(?mi)^\s*[-*]?\s*Sub-points\b.*$",
    r"(?mi)^\s*[-*]?\s*Looking at sub-points.*$",
    r"(?mi)^\s*[-*]?\s*\**\s*(?:Looking at (?:point|Arti\s*cle)|Paragraph \d+ of Arti\s*cle|Heading:\s*\"|First Paragraph:)\**.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?(?:Then\s+)?Arti\s*cle \d+.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Goal:.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Structure:.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Constraint Check:.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Drafting \(Mental\):?\*?.*$",
    r"(?mi)^\s*[-*]?\s*\d+\.\s*(?:Summarize|Identify the law).*$",
    r"(?mi)^\s*[-*]?\s*\"CHỦ TỊCHQUỐCHỘI\"\s*->.*$",
    r"(?mi)^\s*[-*]?\s*Let\'s look\b.*$",
    r"(?mi)^\s*[-*]?\s*IfI?\s+remove the signature blocks.*$",
    r"(?mi)^\s*[-*]?\s*(?:\*\*)?(?:Article \d+|Text Block \d*|Sub-points?|Points? [0-9a-đA-Đ]+|There are|It contains|Line breaks for|No signatures|Ensure line breaks)\b.*$",
    r"(?mi)^\s*[-*]?\s*\*?Point [0-9a-đA-Đ]+:\*?.*$",
    r"(?mi)^\s*\d+\.\s*(?:Extract the main|Extract the \").*$",
    r"(?mi)^\s*[-*]?\s*(?:Points a\), b\)|Point \d+ content|Sub-point [a-z] content)\.?\s*$",
    r"(?mi)^\s*[-*]?\s*Check\s+(?:for\s+typos|specific\s+phrases|\"[^\"]+\").*$",
    r"(?mi)^\s*[-*]?\s*\*?The\s+sub-points\b.*$",
    r"(?mi)^\s*[-*]?\s*\*?The\s+text\s+looks\s+clean.*$",
    r"(?mi)^\s*[-*]?\s*\*?Checking\s+specific\s+phrases:?\*?.*$",
    r"(?mi)^\s*[-*]\s*\"(?:Điều|\bCơ sở|\bCụm|\bKhu|\bmạng lưới|\bkhởi sự)[^\"]+\"\s*$",
    r"(?mi)^\s*[-*]?\s*Top paragraph:.*$",
    r"(?mi)^\s*[-*]?\s*Ignore\b.*$",
    r"(?mi)^\s*[-*]?\s*.*?\bignore\s+(?:the\s+)?page\s+number.*$",
    r"(?mi)^\s*[-*]?\s*\"?\d+\"?\s+(?:at the top,\s*ignore|is at the top,\s*ignore).*$",
    r"(?mi)^\s*[-*]?\s*\d+\s*\((?:Page number - )?ignore\b.*?\)\s*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Draft \d+.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Character [Cc]ount(?: [Cc]heck)?:?.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?(?:Revised Draft|Final Polish|Refined Plan|Mental Outline|Attempt \d+|Review against constraints|Check Constraints|Refining for).*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Rule \d+.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?Exclusion Rules?.*$",
    r"(?mi)^\s*[-*]?\s*\*?\s*\*?(?:Main Text Block|Middle Section|Signature Block|Bottom Left|Bottom Right|Stamp)\b.*$",
    r"(?mi)(?:^|(?<=:::\s))[-*]?\s*(?:Exclude|Extract the main|Extract the \").*$",
    r"(?mi)^\s*[-*]?\s*If I remove the signature blocks.*$",
    r"(?mi)^\s*[-*]?\s*(?:Language:\s*Vietnamese|No markdown:|Vietnamese only\?|Max \d+ characters\?|No \?\s*Yes).*$",
    r"(?mi)^\s*[-*]?\s*The text \"Luật này được.*$",
    r"(?mi)^\s*[-*]?\s*The text at the top is the end.*$",
    r"(?mi)^\s*[-*]?\s*The rest is administrative metadata.*$",
    r"(?mi)^\s*[-*]?\s*The exclusion list is quite specific:.*$",
    r"(?mi)^\s*[-*]?\s*So, the output should primarily be.*$",
    r"(?mi)^\s*[-*]?\s*\*?Let's check the text again\.\*?.*$",
    r"(?mi)^\s*[-*]?\s*Let's look at the specific exclusion:.*$",
    r"(?mi)^\s*[-*]?\s*BUT, the text.*$",
    r"(?mi)^\s*[-*]?\s*Let's look at the bottom block.*$",
    r"(?mi)^\s*[-*]?\s*Let's try to interpret.*$",
    r"(?mi)^\s*[-*]?\s*Actually, usually, for these tasks.*$",
    r"(?mi)^\s*[-*]?\s*The signature line itself.*$",
    r"(?mi)^\s*[-*]?\s*Let's look at the instruction:.*$",
    r"(?mi)^\s*[-*]?\s*So, \"CHỦ TỊCH.*$",
    r"(?mi)^\s*[-*]?\s*\"VĂNPHÒNGCHỦ TỊCHNƯỚC\" is an organization.*$",
    r"(?mi)^\s*[-*]?\s*\"SAOYBẢNCHÍNH\" is the document type.*$",
    r"(?mi)^\s*[-*]?\s*\"Số: 01 /SY-VPCTN\" is the number.*$",
    r"(?mi)^\s*[-*]?\s*\"Hà Nội, ngày.*$",
    r"(?mi)^\s*[-*]?\s*\"KT\. CHỦ NHIỆM.*$",
    r"(?mi)^\s*[-*]?\s*Wait, let's re-read the exclusion rule.*$",
    r"(?mi)^\s*[-*]?\s*However, \"VĂNPHÒNGCHỦ.*$",
    r"(?mi)^\s*[-*]?\s*The top signature block.*$",
    r"(?mi)^\s*[-*]?\s*\"Logo, watermark, header điện tử.*$",
    r"(?mi)^\s*[-*]?\s*\"Chữ viết tay, ghi chú tay.*$",
    r"(?mi)^\s*[-*]?\s*\"Con dấu điện tử, con dấu đỏ.*$",
    r"(?mi)^\s*\"Khối 'Nơi nhận:'.*$",
    r"(?mi)^\s*\"Tên/chức danh người ký.*$",
    r"(?mi)^\s*\"CHỦ TỊCHQUỐCHỘI\" -> This is a title.*$",
    r"(?mi)^\s*\"VĂNPHÒNGCHỦ TỊCHNƯỚC\" -> This is the issuing body.*$",
    r"(?mi)^\s*\"Số: 01 /SY-VPCTN\" -> Document number.*$",
    r"(?mi)^\s*\"Hà Nội, ngày 06 tháng 02 năm 2024\" -> Date.*$",
    r"(?mi)^\s*\*\*\[\s*[↓↑]?\s*OCR gán nhầm.*?\*\*.*$",
    r"(?mi)^\s*[-*]?\s*(?:Start with item|Let's draft|Preserve indentation|No markdown headers|No bold/italic|No bolding|Pure text|Correct numbering|Looks complete|I need to|Ensure no|Actually, looking at|Ensure [\"']|Image check:|Check specific text:|The text looks complete|Structure preserved)\b.*$",
    r"(?mi)^\s*[-*]?\s*\**(?:Item|Clause|Sub-clause)\s+[0-9a-đA-Đ]+:\**\s*[\"'].*?$",
    r"(?mi)^\s*[-*]?\s*\**(?:Start|Content|Text check|Page Nu?\s*mber):\**\s+.*$",
    r"(?mi)^\s*[-*]?\s*(?:preserve the numbering|I need to be careful|Ensure \"[^\"]+\"|Check specific text|Image check:).*$",
    r"(?mi)^\s*[-*]?\s*\"(?:Điều|\d+\.)[^\"]+\"\s*$",
    r"(?mi)^\s*[-*]?\s*\"[a-đ]\)[^\"]+\"\s*$",
    r"(?mi)^\s*[-*]?\s*No \"Nơi nhận\".*$",
    r"(?mi)^\s*[-*]?\s*No page number.*$",
    r"(?mi)^\s*[-*]?\s*\"01 tháng 7 năm 2014\" is written out.*$",
    r"(?mi)^\s*[-*]?\s*(?:So:|So\b).*$",
    r"(?mi)^\s*[-*]?\s*.*?\b(?:Looks complete and accurate|No \"Nơi nhận\" or signatures|No page number \"\d+\").*$",
    r"(?mi)^\s*[-*]?\s*The text looks complete and accurate.*$",
    r"(?mi)^\s*[-*]?\s*(?:a|b|c|d|đ|e|g|h|i|k)\)\s*$",
    r"(?mi)^\s*[-*]?\s*(?:5\.|6\.|7\.)\s+Text\.\.\..*$",
    r"(?mi)^\s*[-*]?\s*[a-b]\)\s+Text\.\.\..*$",
    r"(?mi)^\s*[-*]\s*(?:5\.|6\.|7\.|[a-đ]\)|Điều 217|\d+\.).*$",
    r"(?mi)^\s*[-*]?\s*\*Header:\*\s*\(Skip\s+\"\d+\"\).*$",
    r"(?mi)^\s*[-*]?\s*\*Text:\*\s*$",
    r"(?mi)^\s*[-*]\s*\**Điều \d+.*$",
]

_AI_COMPILED = [re.compile(p) for p in _AI_PATTERNS_VN + _AI_PATTERNS_EN + OCR_PROMPT_PATTERNS]


def strip_ai_monologue(text: str) -> str:
    """Strip AI monologue phrases, <think> blocks, and reasoning traces from text."""
    if not text:
        return text

    # Strip think / thought blocks first
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<thought>.*?</thought>', '', text, flags=re.DOTALL)
    text = re.sub(r'</think>', '', text)
    text = re.sub(r'</thought>', '', text)

    # Strip multiline reasoning traces (e.g. Thinking Process:... up to questions)
    text = re.sub(
        r"(?is)(?:^|\n)\s*(?:Thinking Process|Tư duy suy luận):?.*?(?=\n\s*(?:\b(?:Câu hỏi|Questions?)\b|\Z))",
        "\n",
        text,
    )

    # Strip multiline attempt/mental outline blocks (bounded to not consume substantive content)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Attempt \d+.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Mental Outline.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Check Constraints.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Review against constraints.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Refining for.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Revised Draft.*?(?=\n## Content|\Z)', '', text)
    text = re.sub(r'(?is)(?:^|\n)\s*\*?\s*\*?Final Polish.*?(?=\n## Content|\Z)', '', text)

    # Strip OCR artifact labels inline
    text = re.sub(r'\*\*\[\s*[↓↑]?\s*OCR gán nhầm\s*\]\s*\*\*', '', text)
    text = re.sub(r'\[\s*[↓↑]?\s*OCR gán nhầm\s*\]', '', text)

    for pat in _AI_COMPILED:
        text = pat.sub("\n", text)

    # Collapse excessive blank lines and trim whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

